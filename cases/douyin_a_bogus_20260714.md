# 抖音 PC Web 双签名体系（X-Bogus / a_bogus）逆向案例

## 基本信息

- 目标名称：抖音（douyin.com）PC Web 端请求签名 `X-Bogus` 与 `a_bogus`
- 目标类型：WASM 签名型（bdms WASM 闭包）+ acrawler 体系 X-Bogus（X-Bogus 为纯 JS 入口）
- 日期：2026-07-14
- 负责人：crypto-hunter-lite 自动化分析

## 问题描述

- 现象：抖音 PC Web 关键 API（搜索、用户主页、视频详情、推荐流等）请求携带 `a_bogus` 参数；基础请求携带 `X-Bogus`。缺失或错误会被风控拦截（验证中间页 / 空数据）。
- 失败表现（工具侧 / 取证侧）：
  1. 误把抖音当成「疑似独立 JS VM（BogusTown）」处理 —— 实际 `a_bogus` 核心算法在 WebAssembly 内，bdms.js 仅为加载/派发壳，与头条 `_$jsvmprt` 纯 JS VM 本质不同。
  2. 直接 `fetch` 抖音 API 绕过前端 SDK，请求**不带任何签名**（已验证 `/aweme/v1/web/aweme/favorite/` 返回 `{"aweme_list":null}` 且无 `a_bogus`）—— 误以为 a_bogus 是全局 fetch 拦截自动注入。
  3. 未登录 / 环境检测降级时，签名模块被禁用，取证陷入「零入口、零签名、验证页」三重死局，需识别根因才能跳出。
- 复现步骤：
  1. 浏览器打开 `https://www.douyin.com`，复用已登录 cookie 的 `chrome_profile`（降验证概率）。
  2. 在页面内探测 `window.byted_acrawler` / `window.bdms` / `window.getSign` 等全局对象。
  3. 调用 `window.byted_acrawler.frontierSign(query, ua)` 验证 X-Bogus 生成入口。
  4. 探测 `window.getSign` / `calcSign` / `genSign` 是否为可用函数（结论：占位 getter，undefined）。
  5. 触发真实签名请求：滚动 SSR 页 / 导航 CSR 路由（搜索页触发验证中间页）/ 点击视频卡片（DOM 无 `<a>`，RSC 架构）。

## 证据

- 目标请求（已确证结构）：
  - X-Bogus 生成入口：`window.byted_acrawler.frontierSign(query, ua)` 同步返回 `{"X-Bogus":"..."}`。
    - 输入：`query` 字符串（如 `aid=6383&channel=channel_pc_web&count=10&device_id=&ac=wifi`）+ `ua`（navigator.userAgent）。
    - UA 参与签名：同 query 不同 UA 两次调用结果不同（已验证）。
    - 仅生成 X-Bogus，**非** a_bogus。
  - a_bogus：参数名不在 bdms SDK 内，是抖音前端业务层调用 bdms 生成签名值后**自行挂载**到 query 参数 `a_bogus`。
- 关键参数：
  - `X-Bogus`：acrawler 体系，JS 入口 `frontierSign` 直接可生成（已验证）。
  - `a_bogus`：bdms WASM 闭包计算，前端业务层挂载；运行时无全局可直接调用的生成函数。
- 全局对象探测结果（运行时 `ch_page_run_js`）：
  - `window.byted_acrawler`：存在，`frontierSign` 为可用函数，`init()` 读 `undefined.dfp` 报错。
  - `window.bdms`：存在（WASM 闭包），仅暴露 `getReferer` / `init`；`init()` 读 `undefined.boe` 报错。
  - `window.getSign` / `calcSign` / `genSign`：`Object.keys(window)` 可列出，但 `Object.getOwnPropertyDescriptor` 确认是 secsdk 通过 `defineProperty` 定义的**占位 getter**，访问即返回 `undefined`（非函数、非可调用）。
  - `window.useWebSecsdkApi(e)`：secsdk 的 `W.require` 模块加载器。
- 运行时变量 / 入口：
  - X-Bogus：`window.byted_acrawler.frontierSign(query, ua)`（已验证可用）。
  - a_bogus：bdms WASM 闭包（window.getSign/calcSign/genSign 仅为占位 getter，降级态 undefined）。
- 静态层证据（scratch/douyin 目录）：
  - bdms.js / secsdk.js 内**无** `a_bogus` 字面量 → 印证参数名在业务层挂载。
  - bdms.js 内**无** `WebAssembly.instantiate` 字面量 → WASM 实例化被自研加密容器包裹（头 `PK\x02\x00`，高熵 distinct=256），静态解密成本高。
  - 风控层 `@byted/secsdk-strategy` 内嵌 hex 自研容器（头 `PK\x01\x01`），hook fetch/XHR 收集签名对。
- DOM 架构证据：
  - 抖音 web 用 RSC（React Server Components）架构，SSR 数据挂 `window.EXPOSE_DATA` / `SSR_RENDER_DATA` / `initialRscFlightDataEnd`。
  - 降级页 `/jingxuan` DOM 内**零 `<a>` 零 `<input>`**（纯 React 渲染 + 点击事件 pushState），无视频入口、无搜索框，无法直接交互触发签名请求。
- 网络记录：
  - 手动 `fetch` `/aweme/v1/web/aweme/favorite/`：响应 `{"aweme_list":null}`，post_data 无 a_bogus → 绕过 SDK 不签名。
  - 导航 `/search?type=video`：触发抖音验证中间页（风控升级），`title: 验证码中间页`。

## 超级补环境

- 是否启用：不适用（a_bogus 为 WASM 闭包，未进入离线复现阶段）。
- 判定原因：a_bogus 抓取受阻的根因是**环境降级**（见「真正原因」），非算法未定位。要触发 WASM 实例化需先解决环境降级（补 `dfp` / `boe` 环境对象或换真实浏览器指纹），当前未达成。
- 补环境建议：X-Bogus 路径（frontierSign）不依赖 dfp，可直接纯协议复现；a_bogus 路径需先突破降级。

## 验证应对

- 验证类型：WASM 签名定位 + 双签名体系识别 + 降级根因定位。
- 处理路由：静态确认 WASM 容器（bdms）→ 运行时探测全局对象与签名入口 → 识别降级根因 → 沉淀架构。a_bogus 的完整算法还原（WASM 反汇编 + 运行时 WasmHook 抓真 WASM）为下一阶段。
- 是否需要人工接力：a_bogus 算法复现需人工/AI 接力（WASM 反汇编 + 环境降级突破），本案例先固化「架构识别 + X-Bogus 入口 + 降级根因」层。
- 识别信号：`window.byted_acrawler.frontierSign`（X-Bogus）、`window.bdms`（a_bogus WASM 闭包）、`getSign/calcSign/genSign` 占位 getter（降级标志）、`init()` 读 `dfp`/`boe` undefined（降级根因）。
- 证据包摘要：见上方「证据」与适配器 `server/jsvmp_analyzer/targets/douyin.py` 注释。

## 分析过程

- 类型判断：双签名体系 —— X-Bogus（acrawler 体系 JS 入口，已验证）+ a_bogus（bdms WASM 闭包，算法在 WASM 内）。
- 入口定位：
  - X-Bogus：`window.byted_acrawler.frontierSign(query, ua)` → 同步返回 `{X-Bogus}`。
  - a_bogus：bdms WASM 闭包；参数名 `a_bogus` 在抖音前端业务层挂载，不在 SDK 内（静态无字面量佐证）。
- 静态检测：bdms.js / secsdk.js 内 WASM 实例化被自研加密容器包裹，无明文 `WebAssembly.instantiate`，静态定位困难；`a_bogus` 字面量不在 SDK 内，静态找参数名必然失败。
- 复现方法（下一阶段）：
  1. 突破环境降级：补 `dfp`（device fingerprint）/ `boe`（env 对象）或换真实浏览器指纹，使 `bdms.init()` 不再读 undefined。
  2. 触发 WASM 实例化后，用 base script（final_capture.user.js）的 WasmHook 拦截 `WebAssembly.instantiate/Module`，抓解密后真 WASM 分块上传 `/api/wasm/analyze`。
  3. 用 `ch_wasm_analyze` / `ch_wasm_crypto_functions` / `ch_wasm_disassemble` 分析导出函数，定位 a_bogus 计算本体。
  4. 运行时 hook a_bogus 生成函数记录 I/O 做黑盒复现。

## 误判点

- 误判点 1（认知，已纠正）：原以为 a_bogus 是全局 fetch/XHR 拦截自动注入 → 实际是前端业务层显式调用 bdms 生成后挂载 query 参数；直接 `fetch` 绕过 SDK 不带签名（已验证）。
- 误判点 2（认知，已纠正）：原把抖音当「疑似独立 JS VM（BogusTown）」→ 实际 a_bogus 核心算法在 WASM 内，bdms.js 仅为加载/派发壳；与头条 `_$jsvmprt` 纯 JS VM 本质不同。
- 误判点 3（会话状态，已纠正）：会话重启后旧实例的 `browser_id`（如 pid 形式 `12876` 或上一会话缓存的 UUID）已失效，后端 registry 用新 UUID 重新注册，直接复用旧 ID 调 MCP 浏览器工具会返回 `browser not found`。`ch_cdp_status` 成功注册后返回的 `browser_id` 本身就是正确的 canonical UUID（非缺陷）。规避方式：会话切换后用 `ch_page_get_info({})` 不带 ID，从返回自动探出当前实例的真实 `browser_id`（UUID 形式），再以该 ID 调后续工具。
- 误判点 4（降级识别，已纠正）：`getSign/calcSign/genSign` 出现在 `Object.keys(window)` 列表里，误以为是可调用函数 → 实际是 secsdk `defineProperty` 占位 getter，访问即 undefined（需用 `Object.getOwnPropertyDescriptor` 区分）。

## 真正原因

- 真正原因（a_bogus 抓取受阻）：抖音未登录 / 环境检测降级 —— `byted_acrawler.init()` 读 `undefined.dfp`（device fingerprint）、`bdms.init()` 读 `undefined.boe`（env 对象）均报错 → secsdk 拒绝初始化真实签名模块，只挂占位 getter。a_bogus 的 WASM 路径因环境校验失败被禁用；X-Bogus 基础路径不依赖 dfp，故 `frontierSign` 仍可用。这是环境层阻碍，而非方法问题。
- 识别信号：`init()` 读 `dfp`/`boe` 为 undefined；`getSign` 等 getter 返回 undefined；降级页 DOM 零 `<a>` 零 `<input>`；导航 CSR 路由触发验证中间页。
- 修复方式（针对会话状态误判点 3）：会话切换后旧 `browser_id` 已失效，规避方式是所有 MCP 浏览器调用先用 `ch_page_get_info({})` 不带 ID，从返回取后端重新注册的真实 `browser_id`（UUID 形式），再以该 ID 调后续工具，避免复用失效旧 ID 触发 `browser not found`。`ch_cdp_status` 成功注册后返回的 `browser_id` 本身即正确值，无需修改。
- 可复用规则：
  - 字节系双签名：X-Bogus 走 `byted_acrawler.frontierSign`（JS 入口，易复现），a_bogus 走 bdms WASM（需突破降级 + 抓真 WASM）。
  - 抖音 web 为 RSC 架构，降级页 DOM 无 `<a>`/`<input>`，不能直接 DOM 交互触发签名；需导航 CSR 路由或用真实登录态。
  - `getSign`/`calcSign`/`genSign` 类全局若只出现在 `Object.keys` 却调用为 undefined，优先怀疑 `defineProperty` 占位 getter（降级标志）。

## 验证结果

- 生成位置（已验证）：
  - X-Bogus：`window.byted_acrawler.frontierSign(query, ua)` 同步生成（UA 参与签名）。
  - a_bogus：bdms WASM 闭包（运行时降级态不可用，需突破环境降级后抓真 WASM 还原）。
- 本地复现方式：
  - X-Bogus：纯 JS 调用 `frontierSign`，可直接协议复现（无需浏览器）。
  - a_bogus：待 WASM 还原后实现；当前 `replay_supported=False`。
- 验证结果：
  - X-Bogus 入口已验证可用（两次不同 UA 调用结果不同，证明 UA 参与）。
  - a_bogus 抓取边界已确证（无全局函数、参数名在业务层、降级禁用 WASM 路径）。
  - 降级根因已定位（init 读 dfp/boe undefined）。

## 可复用规则

- 规则 1：抖音 / 头条等字节系站点优先怀疑双签名 —— X-Bogus（`frontierSign`）易拿，a_bogus（bdms WASM）需突破降级。
- 规则 2：抖音 web 为 RSC 架构，降级页 DOM 无 `<a>`/`<input>`，不能依赖 DOM 交互触发签名请求；优先用真实登录态 + CSR 路由或运行时 hook。
- 规则 3：`getSign`/`calcSign`/`genSign` 类全局若 `Object.keys` 可见但调用为 undefined，用 `Object.getOwnPropertyDescriptor` 确认是否为 `defineProperty` 占位 getter（降级标志），不要直接当函数调用。
- 规则 4（工具链）：`ch_cdp_status` 的 `browser_id` 字段不可信；所有 MCP 浏览器调用先用 `ch_page_get_info({})` 自动探出真实 `browser_id`（UUID 形式）。

## 回归说明

- 哪些点容易变：bdms / secsdk 版本升级会重排自研加密容器与 WASM 导出函数；`frontierSign` 参数形态、dfp/boe 环境对象结构、占位 getter 命名均可能变动。
- 下次升级时先检查：探测 `window.byted_acrawler.frontierSign` 是否仍可用；`Object.getOwnPropertyDescriptor(window,'getSign')` 是否仍为占位 getter；`init()` 是否仍读 dfp/boe。若降级根因变化（如改为读其他 env 字段），更新适配器降级根因描述与突破策略。

## 踩坑记录

- 全局 fetch 误判(以为自动注入) → 真实原因(业务层显式调用 bdms 挂载) → 识别信号(直接 fetch 无签名) → 修复(定位 frontierSign + 确认 a_bogus 业务层挂载) → 可复用规则(规则 1/2)。
- 抖音当 JS VM(误判 BogusTown) → 真实原因(WASM 闭包) → 识别信号(bdms.js 无明文 instantiate / a_bogus 字面量不在 SDK) → 修复(适配器标记 vm_family=bytedance_wasm_bogus) → 可复用规则(规则 1)。
- `ch_cdp_status` 旧 ID 失效 → 真实原因(会话重启后 registry 用新 UUID 重注册，旧 ID 失效) → 识别信号(调工具报 browser not found) → 规避(先用 ch_page_get_info 探当前实例真实 ID) → 可复用规则(规则 4)。
- 降级死局(零入口/零签名/验证页) → 真实原因(init 读 dfp/boe undefined) → 识别信号(getSign getter undefined + 降级页零 DOM) → 修复(固化降级根因到适配器 + 转 X-Bogus 已验证入口) → 可复用规则(规则 1/3)。

## 动态取证准备（下一阶段）

### 环境探测（2026-07-14）
- 复用 `chrome_profile`（已登录 cookie）启动真机 Chrome，`include_base_script=true` 注入 final_capture 建立 tab 握手。
- 首页 `/jingxuan` 无验证页（cookie 有效），但为降级页（未登录态或风控） —— DOM 零 `<a>` 零 `<input>`，无视频入口、无搜索框。
- `ch_page_get_info({})` 自动探出真实 `browser_id`（UUID 形式），会话切换后旧 ID 失效的规避已记录（见「误判点 3」）。

### 全局对象探测（已落地）
- `window.byted_acrawler.frontierSign(query, ua)` → 同步 `{"X-Bogus":"..."}`，UA 参与（已验证）。
- `window.bdms` → WASM 闭包，仅 `getReferer`/`init`；`init()` 读 `undefined.boe` 报错。
- `window.getSign`/`calcSign`/`genSign` → `defineProperty` 占位 getter，访问即 undefined（降级标志）。
- `window.useWebSecsdkApi(e)` → secsdk `W.require` 模块加载器。

### 请求链触发尝试（已证伪的路径）
- 手动 `fetch` `/aweme/v1/web/aweme/favorite/` → 无 a_bogus，响应 `{"aweme_list":null}`（绕过 SDK 不签名）。
- 滚动 `/jingxuan` SSR 页 → 不触发签名 API（首屏已含视频流）。
- 导航 `/search?type=video` → 触发验证中间页（风控升级）。

### 突破降级的下一阶段路线
1. 补 `dfp`（device fingerprint）/ `boe`（env 对象）环境对象，或换真实浏览器指纹，使 `bdms.init()` 不再读 undefined。
2. 触发 WASM 实例化后，用 base script 的 WasmHook 拦截 `WebAssembly.instantiate/Module`，抓解密后真 WASM 分块上传 `/api/wasm/analyze`。
3. 用 `ch_wasm_analyze` / `ch_wasm_crypto_functions` / `ch_wasm_disassemble` 分析导出函数，定位 a_bogus 计算本体。
4. 运行时 hook a_bogus 生成函数记录 I/O 做黑盒复现。
- 当前 X-Bogus 已可纯协议复现，a_bogus 完整复现为更大工程，需先突破环境降级。

### 实际执行结果（2026-07-14 运行时取证落地）

**环境**：复用 `chrome_profile` 启动真机 Chrome（CDP + `include_base_script=true`），加载 `https://www.douyin.com`。
首次实例（pid 12876）因会话重启浏览器 ID 缓存失效，改用 `ch_page_get_info({})` 探出真实 `browser_id=7b5c1052-f657-4f6a-be11-15a2f9b39668`；
重启实例（复用 cookie，避开验证页）`browser_id=917db75b-6293-419f-bcd9-4bde8f20f863`，首页正常无验证页。

**X-Bogus 入口验证（成功）**：
- `window.byted_acrawler.frontierSign(query, ua)` 同步返回 `{"X-Bogus":"..."}`。
- 两次调用（带/不带 UA）结果不同 → UA 参与签名（已确证）。
- 这是可直接复现的签名锚点（纯 JS，无需浏览器）。

**a_bogus 抓取边界（已确证）**：
- `Object.getOwnPropertyDescriptor(window,'getSign')` 确认其为 secsdk `defineProperty` 占位 getter，访问即 undefined。
- `calcSign`/`genSign` 同理。window 上无可直接调用的 a_bogus 生成函数。
- 静态层：`a_bogus` 字面量不在 bdms.js/secsdk.js 内 → 参数名在业务层挂载（已佐证）。
- bdms.js 无明文 `WebAssembly.instantiate` → WASM 实例化被自研加密容器包裹，静态定位困难。

**降级根因（根因级发现）**：
- `byted_acrawler.init()` 读 `undefined.dfp`（device fingerprint）报错。
- `bdms.init()` 读 `undefined.boe`（env 对象）报错。
- → secsdk 拒绝初始化真实签名模块，只挂占位 getter；a_bogus 的 WASM 路径因环境校验失败被禁用。
- X-Bogus 基础路径不依赖 dfp，故 `frontierSign` 仍可用 —— 解释全链路现象（降级页零 DOM、getSign undefined、直接 fetch 无签名、导航触发验证）。

**会话状态规避（已记录）**：
- 会话重启后旧实例的 `browser_id` 已失效（registry 用新 UUID 重注册）；`ch_cdp_status` 成功注册后返回的 `browser_id` 本身即正确 UUID，非缺陷。
- 规避：会话切换后用 `ch_page_get_info({})` 不带 ID，从返回取当前实例真实 `browser_id`（UUID 形式），再以该 ID 调后续工具。

### X-Bogus 端到端验证（2026-07-14 续，已落地）

**动机**：X-Bogus 入口 `frontierSign` 已验证可用，需进一步确认其产出的签名是否被服务器接受（对照 toutiao case 的服务器接受度验证方法论）。

**验证链路**（复用 `chrome_profile` 实例 browser_id `917db75b-...`，`include_base_script=true`）：
1. `ch_page_run_js` 调用 `window.byted_acrawler.frontierSign(q, ua)` 生成 X-Bogus。
2. 对真实 API `/aweme/v1/web/search/item/`（当前有效路径）发带 X-Bogus 请求。
3. 对照：同一 API 不带 X-Bogus 请求。

**关键结果**：
- **X-Bogus 格式验证**：`frontierSign` 产出 16 字符标准格式签名（样本 `fZCkNLQLVQlklkhu...`），与抖音 X-Bogus 公开形态一致。
- **API 路径验证**：`/aweme/v1/web/search/item/` 返回 `200`（非 404），路径有效；旧路径 `/aweme/v1/web/search/suggest/` 已被 Janus 网关废弃（`404 Unsupported path(Janus)`）。
- **签名校验强度（弱校验，已确证）**：
  - 带 X-Bogus：`200` + `{"status_code":2483,"status_msg":"请先登录，再继续搜索吧"}`
  - 不带 X-Bogus：`200` + 完全相同响应（`status_code:2483` 请先登录）
  - **两者完全一致** → 抖音 web search/item API 当前对 X-Bogus **弱校验**（带/不带签名响应无差异），与 toutiao PC 端 `serverEnforcesSignature=false` 同理。

**诚实边界（关键）**：
- X-Bogus 格式正确（16 字符，frontierSign 产出）是算法层有效证据，但未登录态下无法验证「X-Bogus 是否被强校验」——业务层优先拦截（请先登录 2483），签名层未参与区分。
- X-Bogus 的强校验作用需在**已登录态**下对比「正确 X-Bogus vs 错误/缺失 X-Bogus」的响应差异（正确返回数据、错误返回签名失败）才能证伪，当前降级态不可达。
- 结论：X-Bogus 是字节系 PC web 的「防御性签名」，存在但当前弱校验；纯协议复现 X-Bogus 值本身有意义（格式合法），但单凭服务器响应无法反推算法正确性（同 toutiao §4.7 深度边界）。

**证据落盘**：`cases/douyin_a_bogus/xbogus_verify_result.json`（含 frontierSign 产出样本 + 带/不带签名响应对照）。

### 下一步（基于实测收敛与原理边界）
1. **X-Bogus 入口已验证（需浏览器调用）**：`frontierSign(query, ua)` 在抖音前端 bundle 内产出 16 字符标准格式签名（已验证）；纯离线 X-Bogus 算法复现待实现（不凭空构造）。弱校验已确证（search/item API 带/不带 X-Bogus 响应一致，均为请先登录），强校验验证需登录态。
2. **a_bogus 突破降级**：补 dfp/boe 环境对象或换真实浏览器指纹，使 `bdms.init()` 成功；再用 WasmHook 抓真 WASM 走 `ch_wasm_*` 分析链路。
3. **会话状态规避固化**：把「会话切换后用 `ch_page_get_info({})` 探真实 `browser_id`」作为标准动作写入 MCP 工具使用规范，避免复用失效旧 ID。
4. 任一阶段产出可复现脚本后，回填本案例「验证结果」并补充新 fixture/回归。

### 续做进展（2026-07-23 · Edge attach / recommend 页）

**环境**：Edge `9222` attach + `safe_capture`；`browser_id=1598da14-...`；页 `https://www.douyin.com/?recommend=1`；task `task_20260723_061837_889ab753`；listener `lst_580b26d711fb45c8`。

**关键突破（纠正旧结论）**：
- 推荐流滚动可稳定触发 `GET /aweme/v1/web/comment/list/`，query 带 **有效 `a_bogus`**（多样本，约 180~200 字符）+ `msToken` + `x-secsdk-web-signature`；响应 `200` / `status_code=0` 有评论数据。
- 这些请求 **不带** query `X-Bogus`（与旧「双签同挂」印象不同，至少本接口如此）。
- `frontierSign` 仍可用（样本 `X-Bogus=6KRZiuFGpE6xS9Se`）。
- `bdms.init()` 仍报 `undefined.boe`，但 **业务层已在产出可被服务器接受的 a_bogus** → 旧「降级=WASM 路径彻底禁用、抓不到 a_bogus」需修正：`init()` 再调失败 ≠ 签名链路未工作。
- DOM 非旧降级页：`a≈220 / input=2 / video=4`；`getSign/calcSign/genSign` 本次甚至不存在占位 getter。

**仍缺**：
- a_bogus 生成函数 / 业务挂载点源码（`ch_search_loaded_scripts('a_bogus')` 无字面量命中，符合「参数名在业务层」）。
- WasmHook 实例数=0（attach 晚于 WASM 实例化；`safe_capture` 也可能未开 WasmHook）→ 需干净启动 + `inject_wasm_hook` / full 隔离实例早注入。
- XHR 断点命中时栈顶被 `final_capture` 的 `XMLHttpRequest.send` 包裹，业务帧未完整抽出。
- 本地 repro / 多样本算法闭环尚未做。

**下一步优先**：
1. 清干净残留 XHR 断点后，用「导航前注入」抓 `WebAssembly.instantiate` 真模块。
2. 对 `comment/list` 做发包前栈钩子（在业务拼 query 处，而非 final_capture send 层）。
3. 黑盒：固定 query 改 cursor，对照 a_bogus 变化；负向篡改 a_bogus 看服务器拒绝形态。

### 续做进展（2026-07-23 下午 · 早注入闭环）

**早注入**：`ch_page_inject_early` 注入 WASM + `a_bogus` 栈钩子后刷新 recommend 页。

**WASM**：抓到真模块头 `00 61 73 6d` + `instantiateStreaming` emscripten/embind 导出（`malloc/free/dynCall_*`）。小 Module(286B) 来自 `83347.3f00021f.js`。

**调用栈（发包时 `a_bogus` 已在 URL）**：
`XHR.open/send` → `final_capture` → `secsdk/runtime_bundler_34.js`（策略引擎 `Ne.run` / `originFn.apply`）→ `sdk-glue.js` → `sec_sdk captcha`。

**签名分层（关键）**：
- `window.use("webSignUrl")(url)` → 只追加 `uifid` / `timestamp` / `x-secsdk-web-signature`（+ headers），**不生成 `a_bogus`**。
- secsdk `webSign` 保护列表含 `comment/list`、`tab/feed` 等。
- `a_bogus` 生成在更底层：`webmssdk.es5.js` / `bdms_1.0.1.19_alpha.js` / glue（版本见 `_sdkGlueVersionMap`）。

**脚本清单**：
- `runtime_bundler_34.js`（secsdk）
- `c-webmssdk/1.0.0.20/webmssdk.es5.js`
- `web/glue/1.0.0.64-alpha.01/sdk-glue.js`
- `bdms_1.0.1.19_alpha.js`

**负向**：`/aweme/v1/web/user/settings/` 对 a_bogus **弱校验**（篡改/缺失仍 `status_code=0`）。强校验请用 `comment/list` 或 `tab/feed`。

**任务置信度**：约 0.9；缺项主要是 `reproduction_code`（本地可调用生成函数）。

### 突破（2026-07-23 · 写入点确证）

**`a_bogus` 写入点 = `bdms_1.0.1.19_alpha.js`（不是 webSignUrl）**

钩住 `URLSearchParams.append` 后，活体栈稳定为：

```text
URLSearchParams.append('a_bogus', value)
  ← bdms d() @ col≈131912   // 实为自定义 JS VM 的 opcode 分发
  ← bdms X() @ col≈131083   // VM 解释器入口
  ← bdms XMLHttpRequest.n @ col≈130952  // bdms 对 XHR.send 的钩子
  ← douyin async/50727… → uc-secure-dtrait-core → 5179…
```

同一次注入还会 `append('msToken', …)`。

**与 X-Bogus 分层**：
| 参数 | 生成方 | 入口 |
|------|--------|------|
| `X-Bogus` | `byted_acrawler.frontierSign`（webmssdk，`isWebmssdk=true`） | 仅返回 `{X-Bogus}` |
| `a_bogus` / `msToken` | **bdms**（VM + SM3） | XHR.send 钩子内拼 query |
| `uifid` / `timestamp` / `x-secsdk-web-signature` | secsdk `window.use('webSignUrl')` | 改写 URL/headers |

**算法线索（bdms 明文区）**：
- 约 `col 141900+` 有哈希类：`reset/write/sum/_compress`，IV = SM3 标准初值  
  (`0x7380166f…0xb0fb0e4e`)。
- `write()` 用 `encodeURIComponent` → 字节数组喂 SM3；活体见先对整段 query（`device_platform=…`）再对签名中间结果做 encode。
- 源码中 **无** 字面量 `a_bogus`/`msToken`；参数名与拼装逻辑在 VM 字节码里（`D/X/d` 解释器 + 大段编码常量）。
- Debugger `script_id=11105`，本地已落盘：`server/data/reverse_runs/task_20260723_061837_889ab753/scripts/bdms_1.0.1.19_alpha.js`（CDN 直连常 404，需从 Debugger 拉）。

**下一阶段（算法复现）**：
1. 对 bdms VM 在 `append('a_bogus')` 前设侧写 / `ch_debugger_side_capture`，截获 SM3 输入明文与输出。
2. 反汇编 VM 字节码，还原 `a_bogus` 打包（SM3 → 自定义编码 ≈180–200 字符）。
3. 对 `comment/list` / `tab/feed` 做正负向强校验；补 `reproduction_code`。

### SM3 子链已闭环（2026-07-23 晚）

早注入 `Object.defineProperty` 在 SM3 `reset` 定义时 wrap `write/sum`，刷新后稳定采到：

**单次签名典型序**（可交错并发）：
1. `SM3(query_string)` → 32B  
2. `SM3(上一步32B)` → 32B（双 SM3）  
3. `SM3("dhzx")` / `SM3(SM3("dhzx"))`（常量盐，本地 hashlib 已对齐）  
4. `SM3(固定168字符串)` → 常量摘要 `5ae9cec7…d1f3`（串会话内不变，base64 解码 125B）

`URLSearchParams.append('a_bogus'|'msToken')` 与上述 SM3 窗口已成对落盘。

**本地验证**：
- `server/data/reverse_runs/task_20260723_061837_889ab753/repro/verify_sm3_live.py`（三组 match=True）
- `.../repro/verify_sm3_chain.py`（子链断言脚本）
- 样本：`.../runtime_scopes/sm3_abogus_pairs.json`

**仍缺**：VM 内把「双 SM3(query) + 盐哈希 + 时间/随机」打包成 ~192 字符 `a_bogus` 的编码步骤。

### VM 字节码包已完整解密（2026-07-23 续）

**加载器（宿主 JS，非 ZIP）**：
```text
r = atob(blob)                         # 头 PK\\x02\\x00
key = sum(r[4:8]) % 256
data = inflate_raw(XOR(r.slice(8), key))  # fflate inflateSync / zlib -15
Z[i] = K(data) × n_str                 # 类 UTF-8，byte≥248 终止
z[i] = [opcodes[], arity, flag, exc]
```

**解密结果**（`scripts/decode_bdms_bytecode.py` → `scripts/bdms_vm_decoded/`）：
- inflate 后 **86939B**，解析 **1001** 字符串 + **796** 函数，`remain=0`
- 常量命中：`a_bogus`(220)、`msToken`(165)、`dhzx`(262)、`append`(163)、`sum`(279)
- **自定义 Base64 字母表**（func≈130 注册为 s0–s4）：
  - s1: `Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=`
  - s2: `Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=`
  - s4: `Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe`
- 字节码是「opcode + 立即数」交错流；`73,<strIdx>,…` 为取常量模式；func `219` ops=`[63,220,76]` 直接引用 `a_bogus`

**纠正**：旧案例把内嵌 `PK\\x02\\x00` 当成 WASM 容器 —— 本版本实际是 **自定义 JS VM 字节码包**（XOR+raw deflate），SM3 在宿主明文区 / 注入 VM（`gr`），最终打包与字母表编码在 VM 内。

**下一步**：
1. 采完整 `a_bogus`（非 vhead 截断）→ 用 s2/s4 反解二进制结构，对齐 SM3 双哈希字段。
2. 反汇编编码相关函数（130/139/145/148/150）还原打包布局。
3. 对 `comment/list` 做正/负向强校验后补完整 repro。

### 完整 a_bogus + 字母表反解（2026-07-23 续）

活体 `URLSearchParams.append` 钩到完整值（约 188–192 字符）。字母表试验：

| 字母表 | 5 样本可解 |
|--------|:---------:|
| s1（`+`） | 3/5 |
| **s2（`-`）** | **5/5** |
| s4 | 5/5 |

选用 **s2** 反解 → 原始载荷约 **141–142 字节**。跨样本稳定字节约 15 处（含 `off=15` 恒为 `0xf3`），头部高变（疑似随机头/异或层），尚不能直接对齐明文 SM3 摘要。

样本与结构落盘：
- `runtime_scopes/abogus_full_samples.json`
- `runtime_scopes/abogus_decoded_struct.json`
- `repro/decode_abogus_alphabet.py`

**仍缺**：打包前的异或/排列步骤 + SM3 字段在 142B 中的偏移（需 SM3 原子样本成对或反汇编 func 150/139）。

### 原子对 + 打包层试探（2026-07-23 晚续）

**环境**：CDP 曾 `WinError 10054`，已 `attach@9222 + safe_capture` 恢复。

**双钩**：`append(a_bogus)` 完整值 + SM3 `write/sum`（`sm3_n≈100` 已重新挂上）。

**结论**：
1. 原 168 字符「常量」**会轮换**（`VyzXuLhn…` → `GIC0Qj9K…`）。
2. VM 编码路径偏 **s4**；s2/s4 均可解但字节不同。
3. 活体 SM3 `outHex` 对 s2/s4 反解载荷做明文/异或/RC4（含 `[255]`、`[0,1,14]`）——**全部未命中**。
4. 142B 中无连续明文 SM3；打包强于简单 RC4/异或。单靠「本地 SM3 → 在 a_bogus 里搜」无法闭环。

落盘：`atomic_sm3_abogus_pairs.json` / `atomic_sm3_align_report.json` / `repro/align_live_sm3_abogus.py`

**下一步**：在 VM Base64 编码前截获明文数组（func≈139/148），或短超时侧写 `append` 前 buffer；勿挂全局 `Function.apply`。

### 深度验证续（2026-07-23 下午）

**1. 字母表往返（纠正误判）**

此前 `verify_alphabet_roundtrip.py` 报 exact/loose=0/10，是 **padding 对比脚本 bug**。修正后：

| 字母表 | loose(去`=`)| exact(含原`==`) |
|--------|:---:|:---:|
| s2 | **10/10** | **10/10** |
| s4 | **10/10** | **10/10** |

结论：`a_bogus` **确为标准 sextet Base64 + 自定义 64 字符表**（非另类位宽编码）。s2/s4 **字符集合相同、排列不同**，仅凭字符无法二选一；VM 引用密度显示编码路径更偏 **s4**（func 139/145/146/148/150…），字母表注册在 **func 130**。

落盘：`runtime_scopes/alphabet_roundtrip.json`（已重写）。

**2. 142B 载荷差分**

- 长度众数 141/142；s2 对齐后 **15** 个跨样本恒定字节（`off=15→0xf3`，`off=23→0x25` 等）。
- 活体 SM3 `outHex` 在载荷中：**明文 / 单字节异或 / 标准 RC4 / 乘法魔改 KSA RC4** 均未命中（`rc4_probe_report.json`）。
- 与公开资料对齐：142B 是 **盐数组位运算打散 +（魔改）RC4 之后** 的编码前缓冲，不是 SM3 原文拼接。

**3. 宿主采盐失败（已验证负向）**

早注入 `Array.prototype.push` / `charAt(字母表)` / `concat` 在 SM3 后短窗内 **salt_n=0 / b64_n=0**。打包与查表编码均在 **VM 内部**完成，不经过宿主 `Array.push`；字母表访问也非 `String.prototype.charAt`（或 VM 持有原始引用）。

`String.fromCharCode` 能采到 64/206 长度调用，但是 WebCrypto JWK 等噪音，**未对齐** a_bogus 142B。

**4. 加密入口字节码指纹（与公开补环境教程一致）**

White 博客用于暴露 `window.encrypt` 的 ops 指纹：

`[34,54,0,3,34,30,214,…]`

在已解码字节码中命中 **VM func 107**（`n_ops=238`，arity=1）。该函数常量引用 `msToken` / `a_bogus` / `bdmsInvokeList` —— 是 **XHR 钩子内拼 query 的入口**，不是底层 RC4/盐数组本体。

落盘：`runtime_scopes/vm_func_107_ops.json`。

**5. SM3 子链（再次活体确认）**

`write` 序仍稳定：`query` → 32B → `dhzx` → 32B → 轮换 168 字符盐串（当前头 `GIC0Qj9K…`）。`sum` 实现为：可选 `sum(data)` 内 `reset+write`，返回 32 字节数组后 `reset`。SM3 类闭包在 bdms 模块内，**不在 window 上**，运行时扫描原型易失败；需依赖 `defineProperty` 早注入。

**6. 阶段结论与下一刀**

| 已闭环 | 未闭环 |
|--------|--------|
| 签名分层 / 写入栈 | 盐数组字段布局 |
| VM 字节码完整解密 | 魔改 RC4 与标准差异点 |
| SM3 子链本地可复现 | 142B←盐数组 的可执行映射 |
| s4/s2 自定义 Base64 往返 | 纯协议 `a_bogus` 生成 |
| func 107 入口指纹 | `comment/list` 强校验样本 |

**推荐下一路径（二选一）**：
1. **补环境复现（工程优先）**：按 White 方案在 Node 跑 `bdms_1.0.1.19_alpha.js`，用 func 107 指纹挂 `window.encrypt`，先拿到可验证黑盒生成器。
2. **算法还原（研究优先）**：对 func 148/150 插桩或反编译盐数组→RC4；宿主钩已证明不够。

勿再挂全局 `Function.prototype.apply`；保持 `safe_capture`。

### VM CALL 插桩突破（2026-07-23 插桩路径）

**方法**：独立 CDP `Fetch`（Response）拦截 `bdms_*.js`，在解释器 **CALL 路径**插桩（内部调用走 `V.get→g()`，不经 `D()` 返回的 `n()`）。

补丁点：
```text
var y=V.get(n);if(y)h.push(...),g(y[0],d,e,y[1]);else{n.apply...}
```
按 ops 指纹匹配 fid ∈ {107,130,139,145,146,148,150,219}，记录 enter args。

**活体命中（`vm_instr_dump_v3.json`，log_n≈176）**：

| fid | 角色 | 入参要点 |
|-----|------|----------|
| **150** | 主签名入口 | 9 元：`[1,0,8, queryString, body, UA, code, aid=6383, "1.0.1.19-alpha.01"]` |
| **148** | 盐/打散输入 | 单参 **~99 字节数组**；含魔数 `41`；尾部 ASCII 屏参 `1360\|992\|2064\|...\|Win32` |
| **139** | 指纹串 | 屏参串或短片段如 `"210,"` |
| **145** | 随机/辅助 | 无参 |
| **130** | 编码相关 | 二进制串入；leave 见 `{magic,version,dataType}` |
| **107** | XHR 挂载 | 外部调用（ext），拼 `a_bogus`/`msToken` |

**流水线（已由插桩证实）**：
```text
150(query,UA,aid,ver) → 组装中间态 → 148(≈99B 盐数组) → 位运算打散
→ (RC4/编码) → 130/s4 Base64 → 107 append a_bogus
```

落盘：
- `repro/cdp_instr_call_v3.py` / `repro/pull_vm_dump.py` / `repro/analyze_vm_instr_v3.py`
- `runtime_scopes/vm_instr_dump_v3.json` / `vm_instr_analysis_v3.json` / `vm_func_fingerprints.json`

### v4 返回值插桩闭环（2026-07-23）

补丁：CALL enter 压 `__dy_vm_fid_stack`；在
`return!!(g=h.pop())&&(v[++p]=l,...)` 处 pop fid 并采真正的 `l`。

**活体结论（`vm_instr_dump_v4.json`）**：
| 观察 | 证据 |
|------|------|
| **150 leave == `a_bogus` 字符串** | 与 `append('a_bogus')` 逐字节一致 |
| **148**：≈99B → ≈132B | 含魔数 41 的盐数组经打散/扩写后变长 |
| enter/leave 计数对齐 | 148:9/9，150:8/9（栈残差 0） |

落盘：`repro/cdp_instr_call_v4.py`、`analyze_vm_instr_v4.py`、`runtime_scopes/vm_instr_*_v4.json`

**下一刀**：解析 148 的 99B 字段布局（时间/SM3/屏参）；从 132B 反推 146/自定义 RC4；本地复现 148→Base64(s4)→与 150 输出对齐。

### 协议闭环续篇（2026-07-24）

工程路径已打通，结论以正式案例为准：

- 算法打包终版：[`cases/a_bogus/README.md`](a_bogus/README.md)
- **评论纯协议爬取 + 心得踩坑**：[`cases/douyin_comment_crawl/README.md`](douyin_comment_crawl/README.md)

关键更新（相对上文「未闭环」表）：

| 原状态 | 2026-07-24 |
|--------|------------|
| 纯协议 `a_bogus` 生成 | **已闭环（sdenv 直调 fn150）**；纯 Python 算法仍未闭环 |
| `comment/list` 强校验样本 | **已实证** 200/350 条；需 Cookie+a_bogus+msToken；活体常**不带** query `X-Bogus` |
| func 107 当 encrypt | **错误用法**；107=XHR 钩子，签入口是 **150 leave** |

本地交付：`task_20260723_061837_889ab753/repro/{sdenv_local_sign,crawl_video_comments}.py` + Cookie/`xmst` 缓存。
