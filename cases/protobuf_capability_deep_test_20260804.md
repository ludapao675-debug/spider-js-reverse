# Protobuf 模块能力深度验证与增强（2026-08-04）

> 类型：工具能力验证 + 模块增强（非站点逆向）
> 目标：`server/protobuf_*.py` 的 Protobuf 解析能力
> 日期：2026-08-04
> 归档依据：对 protobuf 模块做 P0 风险复核、方案 B（.proto 文本解析）、嵌套 unknown 汇总、真实案例深度测试后，固化结论与回归测试。

---

## 0. 核心结论（实证）

crypto-hunter-lite 的 Protobuf 处理能力已具备**完整的闭环**：无 schema 的 wire 解析、多样本差分、gzip/zlib/gRPC 自动剥壳、`.proto` 文本直接编译（方案 B）、`FileDescriptorSet` 动态语义解码、嵌套 unknown 字段递归汇总、gRPC service/method 暴露。全部由 **40 个 pytest 用例**（默认 `pytest -m unit`）覆盖，且用**真实协议数据**驱动验证。

在 JS 加密参数/协议逆向定位下，它已是项目完成度最高的模块之一。

---

## 1. 能力清单（实测确认）

| 能力 | 入口 | 真实验证 |
|------|------|----------|
| 无 schema wire 解析 | `protobuf_wire.decode_protobuf` | 字段号/offset/raw_hex/utf8/packed/嵌套/group 候选；100KB 字段受 `max_preview_bytes`/`max_fields` 截断（**实测无膨胀**） |
| 多样本 wire 差分 | `protobuf_diff.compare_protobuf_samples` | changed/constant/optional/single_observation |
| gzip/zlib/gRPC 自动剥壳 | `protobuf_analyzer._maybe_unwrap` | 真实 gzip/zlib/gRPC+gzip 帧自动剥离；裸 protobuf 不误剥 |
| `.proto` 文本直接编译（方案 B） | `protobuf_schema._compile_proto_sources`（protoxy） | 单体 / 标准库 import / 多文件互 import / map / oneof / service + option |
| `FileDescriptorSet` 动态解码 | `protobuf_schema.decode_protobuf_with_descriptor` | 字段名/嵌套/repeated 还原 |
| 嵌套 unknown 字段递归汇总 | `protobuf_schema._collect_unknown_fields` | 路径式汇总（如 `2.99`），不依赖已移除的 `message.UnknownFields()` |
| gRPC service/method 暴露 | `protobuf_schema._list_services` | 四种 RPC 模式流式标记 + input/output 类型 |

---

## 2. 真实案例深度测试

### 2.1 案例来源（项目内）
- **`cases/kuaishou_live_danmu`**：快手 PC 直播弹幕，**protobuf over WebSocket 两层包装**（`SocketMessage{payloadType,payload}` + 内层 `CSWebEnterRoom`/`WebCommentFeed`），README 实证推送 payload 是**应用层 gzip 压缩**。真实字段号由浏览器二进制证实。
- **`cases/douyin_web_im_send`**：抖音 IM 私信，`POST imapi.douyin.com/v1/message/send` body=`application/x-protobuf`（`f1=conversation_id` 等）；`.bin` 模板未归档，仅 README 描述结构。

### 2.2 案例来源（网上公开）
- **gRPC 官方 `route_guide.proto`**（grpc/grpc，Apache 2.0）：含 `service` + 四种 RPC 模式 + 文件级 `option`。此前完全未覆盖的 service 路径。
- 公开复杂结构（map/oneof/标准库 import/多文件互 import）：模拟 protobuf 官方 addressbook 形态。

### 2.3 验证证据（关键实测输出）
- 快手 gzip 真实帧 → `analyze_protobuf_input` 自动剥壳，`unwrapped="raw+gzip"`，解出 `payloadType=200`。
- 快手 `WebCommentUser` 嵌套里注入未知字段 99 → `unknown_fields` 含 `2.99`（递归路径正确）。
- 快手进房帧用 `.proto` 文本动态解码 → 还原 token/liveStreamId/pageId。
- route_guide 含 service 的 `.proto` 编译成功，5 个 message 不丢失；`RouteGuide` service + 4 method（含 stream 标记）被暴露；真实 `Feature` 字节（嵌套 `Point`，负数经纬度 `-987654321`）正确解码。

---

## 3. 本次增强 / 修复

### 3.1 方案 B：引入 `protoxy` 直接解析 `.proto` 文本
- `pyproject.toml` 新增 `protoxy>=0.7,<1`（纯 Python 绑定 + 内建 well-known types 解析）。
- `protobuf_schema.py`：`_load_descriptor_pool` 新增 `proto_text` / `proto_files` 分支，新增 `_compile_proto_sources`（文本写临时目录编译后清理，文件名防路径注入）。
- **修复的多文件 import bug**：原实现把所有文件重命名为 `file_{i}.proto`，导致 `import "common.proto"` 找不到。改为支持 **dict 形式 `{name, content}`** 保留真实文件名；字符串列表仍映射到 `file_{i}.proto`（用于 import 语句也用该名的简单场景）。

### 3.2 嵌套 unknown 字段递归汇总
- 新增 `_collect_unknown_fields` + `_nested_wire_fields`，基于描述符递归比对 wire 字段，路径式汇总（如 `3.77`）。保留 `unknown_top_level_field_numbers` 向后兼容。
- 关键适配：protobuf 5.x upb **移除了 `message.UnknownFields()` 访问器**（实测抛 `NotImplementedError`），故完全基于 wire 层事实独立递归，不受 proto3 丢弃 unknown 影响。

### 3.3 gRPC service/method 暴露
- 新增 `_list_services`，在 `inspect_protobuf_descriptor` 的 manifest 输出 `services` 键（含 method 的 input/output 类型、client/server streaming 标记）。原 `inspect` 完全忽略 service 定义。

---

## 4. 测试覆盖（40 passed）

| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `test_protobuf_wire.py` | 7 | wire 解析/截断/畸形拒绝 |
| `test_protobuf_compare.py` | 3 | 多样本差分 |
| `test_protobuf_descriptor.py` | 13 | descriptor 解码/方案 B/复杂结构/dict 多文件/service |
| `test_protobuf_api.py` | 8 | API 路由/剥壳/response_base64 透传 |
| `test_protobuf_cases.py` | 5 | **真实案例**（快手 gzip/两层/嵌套 unknown） |
| `test_protobuf_grpc.py` | 4 | **route_guide service/四种 RPC/真实字节** |

注：测试文件均已加模块级 `pytestmark = pytest.mark.unit`，否则被 `pyproject` 的 `addopts = "-m unit"` 全部 deselect（这是 P0.5 阶段发现的真实根因——测试存在但未纳入默认套件）。

---

## 5. 踩坑记录

- **误判（P0 内存膨胀）** → **真实原因**：报告称 utf8/packed 不受 `max_preview_bytes` 限制会膨胀；实测 `_try_utf8` 已用 `raw[:max_preview_bytes]` 截断，且有回归用例。**识别信号**：构造 100KB 字段实测输出仅 15 字节。**修复方式**：不改代码，补防御性回归用例固化不变量。**可复用规则**：结构性结论先用最小脚本实测，勿盲信二手报告。

- **误判（pytest 没跑成功）** → **真实原因**：不是缺包（venv 已装 protobuf+pytest），而是缺 `unit` marker 被 `-m unit` 跳过。**识别信号**：`collected 22 / 22 deselected`。**修复方式**：补 `pytestmark = pytest.mark.unit`。

- **多文件 import 失败** → **真实原因**：防路径注入重命名文件，破坏 import 匹配。**识别信号**：`ProtoxyError: import 'common.proto' not found`。**修复方式**：dict 形式保留真实文件名。**可复用规则**：安全重命名与跨文件引用需求冲突时，用显式 name 字段而非隐式索引名。

- **upb 移除 UnknownFields()** → **真实原因**：protobuf 5.x upb 实现不再支持该访问器。**识别信号**：`NotImplementedError: unknown field accessor`。**修复方式**：基于 wire 层事实 + 描述符独立递归。**可复用规则**：不要依赖 message 对象的 unknown 访问器，从 wire + descriptor 反向比对更稳。

---

## 6. 遗留 / 下一步（按性价比排序）

1. **POGOProtos 压力测试（本地，不外传 `.proto`）**：几百文件/深层嵌套/大量 enum，验证多文件 import 在规模下的稳健性。⚠️ 许可敏感，仅本地压力测试，不归档其 `.proto` 内容。
2. **交叉验证（pbtk / protobuf-inspector）**：同一真实字节喂本实现与独立工具对比字段结构，分歧点即埋雷处。建议与 ① 合并（POGO 复杂字节是好素材）。
3. **Google conformance 套件**：2000+ wire 边界用例，价值最高但需写子进程协议适配层，单独立项。

### 已知能力边界（仍非"顶级"）
- 不认 protobufjs / JSON 描述符入口（只认 `.proto` 文本 + `FileDescriptorSet`）。
- 无双向重编码回路（能解不能改完编码回去）。
- 剥壳只认 gzip/zlib/gRPC，不认 brotli/snappy/自定义压缩。

---

## 7. 基本信息

- 目标：crypto-hunter-lite Protobuf 解析模块
- 类型：工具能力验证 + 模块增强
- 日期：2026-08-04
- 依赖：`protobuf>=5,<8`、`protoxy>=0.7,<1`（方案 B 新增）
- 测试：`pytest tests/test_protobuf_*.py`（默认 `-m unit`，40 passed）
