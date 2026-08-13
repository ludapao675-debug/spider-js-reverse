# 抖音 webmssdk（byted_acrawler）解码器 + X-Bogus 入口逆向案例

## 基本信息

- 目标：抖音 PC Web 端 `byted_acrawler` SDK（`webmssdk.es5.js`，定位版本 `1.0.0.53`）
- 类型：acrawler 体系 JS 入口，**负责 X-Bogus 签名**（`frontierSign`），与 a_bogus（bdms WASM/VM）是**两套独立体系**
- 日期：2026-08-04
- 环境：Edge 9222 attach（`browser_id=7963b87c-938b-49cc-85d1-21ad0ed7e71c`），抖音直播间 `live.douyin.com/133298724351`
- 工具链：crypto-hunter-lite MCP + Node 离线等价性验证

## 核心结论

### 1. webmssdk 字符串数组解码器 `w_0x5c3140`（已纯静态还原 + 语义等价闭环）

- `webmssdk.es5.js` 是重度混淆（控制流平坦化 `while(!![])` + 字符串数组间接调用 `_0xNNNN(0x...)`）的 SDK。
- 核心解密函数 `w_0x5c3140` 是一个**确定性纯函数**：输入一条 hex 配置串，按魔数头（`1213091658` / `1077891651`）、长度前缀、变长 UTF-8 风格解码，产出字符串数组 `_0x408609`（webmssdk 内部所有可读字符串常量都靠它还原）。
- 纯静态解混淆（`ch_deobfuscate_auto` / webcrack worker 引擎）已还原出干净版 `w_0x5c3140`（`cases/drafts/deob_test/w5c_deob_short.js`，49 行，零 `_0xNNNN` 间接调用）。

**语义等价验证（闭环证据）**：
- 在 Node 中同时运行 `raw_short.js`（live 抽取、保留 `w_0x25f3` 间接调用）与 `w5c_deob_short.js`（静态还原纯解码），共享**同一份 live 真实 `_0x458f30` 数组**，对**同一条 live 配置串**解码：
  ```
  errA: null
  errB: null
  aLen: 12  bLen: 12
  same: true      ← 两版解码数组逐元素相等
  ```
- 验证脚本：`cases/drafts/deob_test/equivalence_node_test.js`；回归测试：`tests/server/test_deobfuscate_pipeline.py::test_semantic_equivalence_raw_vs_deobfuscated_decoder`（断言 `same:true`，全部通过）。
- 结论：纯静态解混淆在解码器层与原始运行时**语义等价**，且全程未向页面注入执行 JS（符合"解混淆禁止运行时"规则）。

### 2. X-Bogus 生成入口 `frontierSign`（live 验证可用）

在当前直播间页面运行时探测：

```js
window.byted_acrawler.frontierSign(query, ua)
// → {"X-Bogus": "fQPi5Z3PkjlsVEGj"}  (16 字符标准格式)
```

- `frontierSign` 是同步函数，输入 `query` 字符串 + `ua`（navigator.userAgent），UA 参与签名（不同 UA 结果不同）。
- 探测结果（`ch_page_run_js`）：
  ```json
  {"acrawler":true,"frontierSign":"function","init":"function",
   "keys":["frontierSign","getReferer","init","isWebmssdk","report","setConfig","setTTWebid","setTTWebidV2","setTTWid","setUserMode"],
   "xbogus_sample":"fQPi5Z3PkjlsVEGj","xbogus_len":16}
  ```
- `byted_acrawler` 是压缩后的对象字面量（webpack 模块导出 / minify 闭包），`w_0x5c3140` 定义在 webmssdk 顶层 script scope，**不暴露**在 `byted_acrawler.toString()` 里（已实测 `toString()` 长度仅 15，正则抽不到）——它通过闭包被 `frontierSign` 调用。

### 3. 与 a_bogus 的体系分界（重要，避免混淆）

| 参数 | 生成方 | 入口 | 算法载体 |
|------|--------|------|----------|
| `X-Bogus` | `byted_acrawler`（webmssdk，`isWebmssdk=true`） | `window.byted_acrawler.frontierSign(query, ua)` 同步返回 `{X-Bogus}` | 纯 JS（本案例解码器） |
| `a_bogus` / `msToken` | `bdms`（自定义 JS VM + SM3 + 自定义 Base64） | XHR.send 钩子内拼 query，无全局可调函数 | bdms VM 字节码（见 `cases/a_bogus/`） |
| `uifid` / `timestamp` / `x-secsdk-web-signature` | secsdk `window.use('webSignUrl')` | 改写 URL/headers | secsdk 策略引擎 |

- 抖音直播间实际请求常**只带 a_bogus + msToken + x-secsdk-web-signature，不带 query X-Bogus**（与旧"双签同挂"印象不同）。
- 抖音 web 为 RSC 架构，降级页 DOM 零 `<a>`/`<input>`，不能直接 DOM 交互触发签名；需真实登录态 + CSR 路由或运行时 hook。
- 更完整背景见 `cases/douyin_a_bogus_20260714.md`、`cases/a_bogus/README.md`。

## 证据

- 定位：`ch_search_loaded_scripts(pattern="webmssdk|acrawler|byted_acrawler")` → `runtime:ext:27` = `https://lf-c-flwb.bytetos.com/obj/rc-client-security/c-webmssdk/1.0.0.53/webmssdk.es5.js`（322568B，Content-MD5 `PBbBGiasmSJpn/xJ64n6hQ==`），`match_count=14`，定位门禁自动解除。
- 离线样本：`cases/drafts/deob_test/webmssdk.es5.js`（322568B，与 CDN 1.0.0.53 字节一致）。
- 解混淆产物：`cases/drafts/deob_test/webmssdk_worker_out.js`（webcrack worker 输出）、`w5c_deob_short.js`（纯解码器）。
- live 运行时：`frontierSign` 调用产出 16 字符 X-Bogus（样本 `fQPi5Z3PkjlsVEGj`）。
- 等价性：`equivalence_node_test.js` → `same:true`（解码器语义闭环）。

## 纯本地协议复现（X-Bogus 离线生成）

### 方法

webmssdk 比 bdms 简单得多（无 VM/WASM），可直接在 Node `vm` 中加载**原始混淆样本** `webmssdk.es5.js`，补最小浏览器垫片（`window`/`document`/`navigator`/`location`/`localStorage`/`setTimeout`/`crypto` 等），调用 `window.byted_acrawler.frontierSign(query, ua)` 即可本地生成 X-Bogus。

- 复现脚本：`repro_offline_xbogus.js`（加载 + 调用 + 多 query 产出验证）
- 算法同质验证：`verify_xbogus_structure.js`（长度/字符集/状态字段隔离/输入驱动四维验证）

### 关键实现注意

1. **挂载位置**：webmssdk 在 vm 沙箱里把 `byted_acrawler` 挂到了**全局（ctx 顶层）**，而非 `ctx.window` 上（与真实浏览器不同）——取用时需用 `ctx.byted_acrawler || ctx.window.byted_acrawler`。
2. **`frontierSign` 形参只有 1 个（query）**：UA 在 webmssdk 初始化时已写入全局环境（`navigator.userAgent` 垫进 `win.navigator`），传 UA 参数不影响签名（live 页传 UA 是冗余）。
3. **X-Bogus 是有状态签名**：含 `Math.random()` 与 `_0x6caf.bogusIndex++`（每次调用自增计数器），离线产出与 live **不逐字节一致**（随机盐 + 调用计数）——这是设计上的防御性签名。

### 验证结果（`verify_xbogus_structure.js`）

```
LENGTH_16_AND_CHARSET_OK: true          # 长度恒 16，字符集完全落在 webmssdk 字母表
DECODED_LEN: 12                          # 解码出 12 字节（9 字节 payload 块 + 校验）
CHANGING_BYTE_INDICES: [2, 11]           # 固定随机后仅 2 字节随调用变化（bogusIndex 状态 + 随机尾）
STATE_FIELD_ISOLATED: true               # 状态字段隔离 => 是真算法结构，非随机乱码
INPUT_DRIVEN_DISTINCT: true              # 不同 query 产出不同签名
STRUCTURE_OK: true
```

- X-Bogus 字母表（webmssdk 自定义 base64）：`Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe`（与公开 X-Bogus 字母表一致）。
- 编码结构（来自 `_0x1633f2`/`_0x4145f8` 逆向）：9 字节 payload（`_0x1ffaa7`：头部 `kHttp<<6|initialized<<5|randBit<<4` + envcode + ubcode + 解码后的 query/盐哈希片段）+ 1 校验字节（异或和）+ 1 随机字节 → 11 字节源 → 自定义 base64 → 16 字符。

### 诚实边界

- 离线复现跑的是**官方 webmssdk 原始代码**，算法正确性由"官方代码本身"保证，无需重新逆向算法——本验证聚焦"能在无浏览器环境加载并产出合法 X-Bogus"。
- X-Bogus 当前在抖音 web 为**弱校验**（带/不带签名响应一致），离线产出格式合法即满足协议复现需求；强校验验证需登录态。
- 离线产出与 live 逐字节不同（随机盐 + bogusIndex 状态），**不可**直接拿离线值冒充 live 实时签名——但同一算法家族，格式/结构完全等价。

## 工具链复盘

- `ch_cdp_start(mode="attach", attach_mode=true, port=9222)` 接管已开 Edge；外部脚本 `ch_script_get_source` 返空（CDP 索引空洞），改用 `ch_fetch_url` 服务端直连抓源码绕过。
- 外部脚本内存搜索：`ch_search_loaded_scripts` 用 `pattern` 参数（非 `q`），返回 `script_id`/`script_url`。
- 解混淆：`ch_deobfuscate_auto`（`ch_deobfuscate_js` 默认）对 322KB 文件受后端 worker 引擎 ~300s 硬封顶约束；超大文件建议 `engine=super_obio` deep 档。MCP 层 `timeout_ms` 已放宽到 300000 默认（HTTP 窗口 330s）。

## 已知边界（诚实记录）

- `live_arr.js`（早期抓取）索引 5 的 hex 串与 CDN 1.0.0.53 索引 5 不同（长度前缀 `0122` vs `01f3`）——说明抖音可能按页面类型下发不同 SDK 构建（数组顺序/内容有差异）。等价性验证基于"同一份数组喂两份解码器"，结论不受影响；但**离线解混淆产物严格对齐的输入是 CDN 1.0.0.53 样本**，live 页若下发不同 minor 构建，解码器主体（纯函数逻辑）通常不变，仅 `_0x458f30` 数组内容不同。
- X-Bogus 在抖音 web 当前为**弱校验**（search/item API 带/不带签名响应一致，均为"请先登录"）——格式合法即算法层有效，强校验验证需已登录态。详见 `cases/douyin_a_bogus_20260714.md` §X-Bogus 端到端验证。
- `ch_deobfuscate_js` 在 322KB 上的真实跑通需 MCP 进程 `--timeout` ≥300s（代码/配置已改 600s，但运行中的 stdio 进程仍可能显示旧值，需用户重启 MCP 生效）。

## 可复用规则

1. 抖音/头条系优先怀疑**双签名**：X-Bogus（`frontierSign`，纯 JS 易复现）vs a_bogus（bdms VM/WASM，需突破环境降级）。
2. `byted_acrawler` 的 `toString()` 抽不到内部函数（`w_0x5c3140` 在顶层 script scope），不要指望从对象上反查解码器源码；外部脚本源码用 `ch_fetch_url` 服务端直连抓。
3. 解混淆验证不要只看"结构干净"，必须用 **live 真实数组做语义等价**（raw vs deob 解码输出逐元素比对）才算闭环。
4. 降级态识别：`getSign/calcSign/genSign` 若 `Object.keys(window)` 可见但调用为 undefined，是 secsdk `defineProperty` 占位 getter（降级标志），不要当函数调。
