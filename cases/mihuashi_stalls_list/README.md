# 米画师 stalls 橱窗列表分页复现

## 基本信息

- 目标名称：米画师（mihuashi.com）橱窗列表分页 API
- 目标类型：WASM 签名（wasm-bindgen / Rust）+ 请求头签名参数
- 目标接口：`GET https://www.mihuashi.com/api/v1/stalls`
- 签名头：`M-S`（签名串）、`M-T`（unix 秒）、`Web-Version: frontend`
- 日期：2026-07-28

## 问题描述

- 现象：本地 Python 复现（每次 spawn 一个 node 子进程签名）拉取分页，**间歇性 403**，成功率约 37%。
- 失败表现：403 响应体明确为 `{"error":"signature invalid","msg":"签名错误"}`（是签名问题，不是 WAF/风控）。
- 早期误判：曾观察到「时间戳奇偶性 100% 相关」，实为采样巧合。

## 真正原因（已闭环验证）

`M-S` 由 WASM 内部对**含 Rust `HashMap` 的载荷**序列化生成，其 key 迭代顺序受 `getrandom`（WebCrypto 随机）影响：

- 每次签名约 **38%** 落入服务端认可的规范顺序（记为「**有效族**」），其余 **62%** 是**确定性无效**签名。
- **无效签名同串重发 0/18 通过**——重发同一 M-S 徒劳，**必须重新签名**（重新掷随机）。
- 有效签名另有约 **17%** 被服务端集群随机 403（同一有效 M-S 重放 7/10）。
- **进程级偏置（关键）**：getrandom 种子在 WASM 实例初始化时定一次，同一 node 进程内多次签名**高度同命运**（实测进程可 8/8 全无效）。因此每次重试必须 **spawn 全新 node 进程**才能得到独立种子；**单进程批量签名会把独立试验退化为批数试验**，大幅降低成功率（实测 batch=8 方案端到端仅 80%）。

### 识别信号

同一被签 URL `/api/v1/stalls` 下，M-S 中间段落可分两族（26 样本零反例）：

| 族 | 特征子串 | 有效性 |
|----|---------|--------|
| B  | `MGarRj` | 100% 有效（返回 200） |
| A  | `MGarFz` | 100% 无效（返回 403） |

> 注：该特征子串**依赖具体被签 URL**，换接口会变，仅作诊断识别用，**不可硬编码进复现逻辑**。

## 修复方式

见 [repro.py](./repro.py)：

1. **403 即重新签名重试**（而非重发同一 M-S），每次都重新掷「有效族」硬币；
2. **每次重试都 spawn 全新 node 进程**（`make_sign_headers` 内部单次调 node），保证每次试验拿到独立的 WASM 初始化种子；
3. **不硬编码 `MGarRj`**，对任意接口通用；
4. `max_retries=25`：每次新进程约 38% 命中，理论失败率 ≈ 0.62²⁵ ≈ 4e-6。

> ⚠️ **反面教训**：`sign_tool.mjs` 保留了 `--batch=N`（单进程批量签），但**严禁用于抓取**——同进程签名共享种子、高度同命运，会把 25 次独立重试退化为约 3 批同命运试验，实测成功率从 100% 掉到 80%。批量仅可用于诊断（如观察族分布）。

## 关键实现细节

- 签名输入是 axios `config.url = "/api/v1/stalls"`（**不含 query**），非真实请求 URL。
- 前端调用：`sign(encodeURI(url), Math.floor(Date.now()/1000))`，M-T 为纯 10 位 unix 秒。
- 未登录态即可请求：`Authorization: Bearer null`。
- query 需按字母序：`category & only_fast & order & page & per & state`（注意 `only_fast` 蛇形，值小写字符串）。
- `sign_tool.mjs` 补环境：mock `document.querySelector`、`navigator.webdriver=false`、`crypto=webcrypto`；并短路 getrandom 的 Node 检测（`__wbg_node/process/versions` 返回 0）强制走 WebCrypto。
- 环境变量 `MHS_SIGN_FIXED_RNG=<byte>` 可固定 getRandomValues 返回单字节，用于对照实验。

## 本地复现方式

```powershell
cd cases\mihuashi_stalls_list
D:\python_work\venv\Scripts\python.exe repro.py --page 2
# 可选参数：--page --per --category --order --state --only-fast
```

## 验证结果

- 修复后端到端实测 **25/25 页全成功**（两轮 10 页 + 15 页），平均约 2.6s/页（node spawn + 重试开销）。
- 命中分布符合预期：约 62% 无效族，典型需 2~10 次重试命中。
- 负向验证：无效族签名（`MGarFz`）18/18 全 403；nonce=0 生成的签名重放 0/10。
- 反面对照：`batch=8` 单进程方案端到端仅 8/10（80%），印证进程级种子偏置。

## 可复用规则

1. **WASM/Rust 签名间歇性失败先怀疑 `HashMap` 迭代顺序非确定性**（getrandom 种子驱动），别急着归因时间戳/Cookie/WAF。
2. **消歧「确定性无效」vs「服务端随机拒」**：同一签名串重放——全 403=我方签名无效；时而 200/403=服务端随机（重试可解）。
3. **无效签名重发无意义，必须重新生成**；有效率固定时，重试次数 n 的失败率 = (1-p)ⁿ。
4. 用**单进程批量签名**摊薄 node 启动开销，而非每次 spawn。

## 诊断方法论回顾（控制变量法）

逐一排除：时间戳单位/奇偶（零相关）→ node 启动延迟（无差异）→ Cookie/阿里云 WAF（A/B 组一致）→ nonce 取值（决定成功）→ 同串重放消歧（分离确定性 vs 服务端随机）→ 因素分离量化（38% 有效族）→ 族 vs 有效性关联（100% 对应）。

## 方法论纪律（本案返工教训）

本案曾因三个失误返工，记录以免重蹈：

1. **诊断脚本应合并为单个参数化工具**：本案曾散出 8+ 个 `_diag_*` 一次性脚本，它们共用同一 `sign→send→统计` 骨架，应合并为一个带参数（nonce/重放次数/分组）的诊断入口。注：“发签→打活体服务端→按变量统计成功率”这类受控 A/B 统计诊断无现成 MCP 工具，确需自制（`ch_reverse_crypto_fuzz` 是断点期黑盒差分、`ch_sdenv_verify_code` 是沙箱期望值验证，均不适用）；但产签环节可复用沙箱执行工具而非反复手搭 node 子进程。
2. **早期异常信号不得忽视**：族分布诊断早就暴露“某进程 8/8 全无效”的进程级偏置信号，当时未识别就推进批量方案，埋下回归。
3. **优化前先验证假设**：未验证“重试独立性”就改成单进程批量，直接导致成功率从 100% 跌到 80%。任何以“独立重试”为前提的稳定性设计，改架构前必须先证伪试验相关性。

## 回归说明

- **容易变的点**：WASM 版本升级后 `M(x,A)` 解码逻辑、getrandom 接线、被签 URL 拼法；`MGarRj/MGarFz` 特征子串随接口变化。
- **下次升级先检查**：`sign_tool.mjs` 的补环境是否仍能加载新 wasm；有效族比例是否变化（据此调 `max_retries`）；真实请求头是否新增字段。
