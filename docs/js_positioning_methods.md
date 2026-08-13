# JS 加密参数定位方法论

> **定位阶段是逆向分析的前置条件。** 本文件是定位方法的详细参考，由 AGENTS.md 门禁强制引用。
> **定位未完成前，禁止调用断点/调试/追踪类工具。**
>
> 本文描述的是**分析顺序与边界选择**；项目运行时（`panel/final_capture.user.js`、`ch_hook_crypto`、`ch_wasm_*` 等）已覆盖其中大量 Hook 点，优先读注入证据，不要重复发明全局 Hook。

---

## 推荐定位顺序（先读这张）

```text
Network Initiator / 请求调用栈
  ↓
XHR/fetch Breakpoint（仅覆盖 XHR/fetch）
  ↓
请求发送层 Hook（XHR / fetch / Headers / WS / beacon）
  ↓
序列化 / TextEncoder / Web Crypto 边界
  ↓
冻结时间与随机源做差分
  ↓
检查 iframe / Worker / Service Worker / Worklet
  ↓
检查 Wasm imports / exports
  ↓
【大方向】内存搜索：JS 堆 → TypedArray/ArrayBuffer → Wasm 线性内存（差分）
  ↓
Overrides 或 AST 插桩
  ↓
最后再进入 JSVMP 指令 Trace
```

比一上来全局 Hook `JSON.stringify`、`Function`、或 `Proxy(window)` 更稳，噪音也更小。  
**内存搜索不是兜底彩票**：它与 Hook/断点互补——Hook 告诉你「谁在写」，内存搜索告诉你「写到了哪里、明文/密钥还在不在」。

---

## 定位决策树

```
Network Initiator（零 Hook 成本）
  ├─ 能跳到业务代码 → 跟栈确认 → 定位完成
  └─ 不够 → 密文特征反推（候选算法方向）
       │
静态搜索（协议字段/字符串常量 > URL路径 > 关键词库 > 拦截器模式）
  ├─ 命中 → 确认位置 → 定位完成（门禁自动解除）
  └─ 未命中 → Hook 分层排查
       │
Hook：网络发送 → 序列化/规范化 → Web Crypto/密码库 → 随机/时间 → 存储
  ├─ 命中 → 跟栈确认 → 定位完成
  └─ 未命中 / 只有密文没有生成点
       │
内存搜索（JS 堆 → 二进制缓冲 → Wasm Memory，优先短探针 + 差分）
  ├─ 命中明文/密钥/中间态 → 反推写入点 → 再回 Hook/断点闭环
  └─ 仍未命中 → 多 Realm / 动态代码 / 响应解密 / JSVMP
```

---

## 一、Network 面板与请求发起栈

**第一步优先看 Network → Initiator / 调用栈。** 很多请求不用写 Hook 就能直接跳到发起代码。

工具映射：

| 目标 | 工具 |
|------|------|
| 抓目标请求 | `ch_listener_start` → `ch_listener_read` → `ch_extract_request` |
| 注入侧高价值网络/加密日志 | `ch_injection_evidence` → `ch_get_entry` |
| XHR/fetch 发包暂停 | `ch_breakpoint_set_xhr(url_substring=...)` |

---

## 二、DevTools / CDP 断点体系

不要把不同断点类型混为一谈：

| 类型 | 含义 | 本项目入口 |
|------|------|-----------|
| **XHR/fetch Breakpoint** | 按 **URL 子串**匹配；命中后暂停在 XHR/fetch **发起位置**。不是通用网络断点，**不覆盖** `WebSocket.send`、`sendBeacon`、表单导航提交、图片打点等 | `ch_breakpoint_set_xhr` |
| **Event Listener Breakpoints** | click、submit、Timer、Worker/Service Worker 事件等 | DevTools 事件断点；适合从用户操作入口收窄异步链 |
| **Instrumentation Breakpoints** | 脚本执行前、带 Source Map 脚本执行前（CDP：`Debugger.setInstrumentationBreakpoint` / `beforeScriptExecution`） | 动态脚本/WAF 场景配合 `ch_find_runtime_script` |
| **URL / 文本 / 行号断点** | 已知脚本位置时 | `ch_breakpoint_set_by_url` / `ch_breakpoint_set_by_text` |
| **Function Breakpoints** | 已拿到函数对象时 `debug(fn)` | 页面内 `ch_page_run_js` + 调试器 |

> XHR/fetch Breakpoint：根据请求 URL 片段暂停在 XHR/fetch 发起位置；其他网络通道仍需单独 Hook。

**元素/事件断点**：命中精度低于发包断点，但适合从用户操作入口追踪完整异步链：

```text
click/submit → 表单校验 → 参数组装 → 请求拦截器 → 签名 → fetch
```

不要说「元素侦听器一般不行」——它不是加密本体，但是常见业务链入口。

---

## 三、网络发送层 Hook

| Hook 点 | 说明 |
|---------|------|
| `XMLHttpRequest.prototype.open/send/setRequestHeader` | 绝大多数 XHR |
| `window.fetch` + `Request` 构造函数 | fetch；最终入参检查很关键 |
| `Headers` 构造函数 / `set` / `append` / `delete` | 只 Hook `Headers.prototype.set` **会漏**：构造器初始化、`append`、以及 `fetch(url, { headers: {...} })` 对象字面量；部分 Headers 还可能不可修改 |
| `WebSocket.prototype.send` | WS 通道（XHR 断点覆盖不到） |
| `navigator.sendBeacon` | 打点/卸载上报 |
| 表单 `HTMLFormElement.submit` | 传统导航提交 |

注入方式：`ch_page_run_js`；或先读 `final_capture` 已采集的网络证据（`ch_injection_evidence`）。

```javascript
// 网络层 Hook 示例 - fetch 拦截
const _fetch = window.fetch;
window.fetch = function(...args) {
    console.trace('[Hook] fetch called', args[0]);
    return _fetch.apply(this, args);
};
```

---

## 四、序列化与规范化层 Hook

数据编码和序列化 API 是**高命中率边界**，但**并非**所有加密流程都会经过 JSON、Base64 或 URL 编码。

现代签名可能直接处理 `Uint8Array` / `ArrayBuffer` / `DataView` / protobuf / msgpack / CBOR / Wasm 内存 / 自定义二进制协议。`Request.body` 也可以是字符串、Blob、ArrayBuffer、TypedArray、DataView、FormData、URLSearchParams 或 ReadableStream。

### 高价值边界

```text
JSON.stringify / JSON.parse          # 高频，非必经
atob / btoa / encodeURIComponent
URLSearchParams / FormData.append|set
TextEncoder.prototype.encode
TextEncoder.prototype.encodeInto     # 常直接写入 TypedArray / Wasm 堆
TextDecoder.prototype.decode
Uint8Array / ArrayBuffer / DataView
qs.stringify / 稳定 JSON 排序 / 空值过滤 / Unicode 归一化
protobuf / msgpack / CBOR
压缩后再加密
```

### 签名前原文（往往比 AES/HMAC 函数更重要）

```text
原始业务对象
  → 字段过滤
  → 排序/规范化
  → 序列化
  → UTF-8 字节化
  → Hash/HMAC/加密
  → Hex/Base64
  → 请求发送
```

```javascript
// 数据处理层 Hook 示例 - JSON.stringify（高频边界，注意过滤刷屏）
const _stringify = JSON.stringify;
JSON.stringify = function(obj, ...rest) {
    const s = _stringify.call(this, obj);
    if (/sign|token|encrypt/i.test(s)) {
        console.trace('[Hook] JSON.stringify candidate', s.slice(0, 200));
    }
    return _stringify.call(this, obj, ...rest);
};
```

`final_capture` 在非 `safe_capture` 下也会采集编码类边界；页面不稳时优先 `safe_capture` + 注入证据，不要强行全量包装。

---

## 五、Web Crypto 与第三方密码库

### Web Crypto API（P0，高价值边界）

```text
crypto.subtle.encrypt / decrypt
crypto.subtle.sign / verify
crypto.subtle.digest
crypto.subtle.importKey / exportKey
crypto.subtle.generateKey
crypto.subtle.deriveKey / deriveBits
crypto.subtle.wrapKey / unwrapKey
```

参数里通常已有算法名、IV、salt、additionalData、tagLength、CryptoKey——定位效率极高。

工具：`ch_hook_crypto`、`ch_injection_evidence`（`final_capture` 已 Hook SubtleCrypto 全家桶）。

### 第三方库搜索关键词

```
CryptoJS（仍常出现，但上游已停止积极维护；现代项目还要搜 Web Crypto / Wasm / libsodium / noble / tweetnacl）
JSEncrypt / forge / jsrsasign / KEYUTIL
sm-crypto / sm2 / sm3 / sm4
encryptLong / setPublicKey
-----BEGIN PUBLIC KEY-----
wordArray / hex_md5 / getSignature
```

### 国密专项

```text
sm2.doEncrypt / doDecrypt / doSignature / doVerifySignature
sm3
sm4.encrypt / decrypt
C1C2C3 / C1C3C2          # 模式不同会导致“算法找对但无法互通”
ASN.1 DER
04 非压缩公钥前缀
userId / ZA
```

案例参考：`cases/tsinghua_id_login`（SM2 C1C3C2）。

---

## 六、随机数、时间戳与设备状态（非确定性源）

差分实验前必须意识到：只改一个业务字段时，签名仍可能因时间戳/nonce/IV/salt/UUID 每次不同而全变。

```text
crypto.getRandomValues
crypto.randomUUID
Math.random
Date.now / new Date
performance.now
```

建议单独做：**非确定性源定位与冻结**——先用 Hook/`final_capture` 确认谁在读随机与时间，再在对照样本中固定这些值，否则控制变量结论不可信。

`final_capture` 已采集 `getRandomValues` 等；全量模式可能改写 `Date.now`（高侵入），页面异常时改用 `safe_capture`，不要为了“冻结时间”把页面弄挂。

---

## 七、存储与缓存

| 边界 | 工具/做法 |
|------|-----------|
| `localStorage` / `sessionStorage` | `ch_page_get_storage`；Hook `setItem` |
| `document.cookie` | `ch_hook_cookie_write` / `ch_page_get_cookies` |
| IndexedDB | 密钥、设备指纹、token 种子、预计算表常在这里，不只 localStorage |
| Cache Storage / Service Worker Cache | 离线缓存的脚本或票据 |
| Cookie Store API | 现代 Cookie 读写 |
| BroadcastChannel / MessageChannel | 跨上下文传密钥/票据 |

---

## 八、iframe / Worker / Service Worker / Worklet（多执行上下文）

每个 iframe、Worker、Worklet 都有自己的 **Realm** 和原型对象；主页面 Hook 一次**不能**覆盖所有上下文。

```text
iframe
Worker / SharedWorker / ServiceWorker
AudioWorklet / PaintWorklet
Blob Worker / data: URL Worker / 模块 Worker
```

### Worker 注意点

- `importScripts()` 属于 `WorkerGlobalScope`，**只存在于 Worker 内部**。主线程 Hook `window.importScripts` **无效**。
- 主线程只能直接观察：`Worker`/`SharedWorker` 构造、`postMessage`、Worker 脚本 URL。
- 要捕获 Worker 内的 `fetch` / `crypto.subtle` / `importScripts`，需要：替换 Worker 脚本为 bootstrap、Local Overrides、CDP 自动附加 Worker Target、或在 Worker Realm 内重新注入 Hook。

本项目：`final_capture` 会对 Worker 做 bootstrap/再注入；分析时用 `ch_injection_evidence` 看 Worker 侧日志，不要假设主线程 Hook 已覆盖。

---

## 九、WebAssembly：编译、导入导出与线性内存

完整定位链（不要只记两个入口）：

```text
WebAssembly.compile / compileStreaming
WebAssembly.instantiate / instantiateStreaming
WebAssembly.Module / Instance
WebAssembly.Module.imports / exports
WebAssembly.Memory（线性内存 / Memory.buffer）
```

- `imports`：看 JS→Wasm 依赖
- `exports`：枚举暴露函数
- `Memory.buffer`：观察输入、输出、中间字节 —— **详细搜法见「十九、内存搜索」**

工具：`ch_wasm_start` → `ch_cdp_start(capture_profile='wasm_safe_capture')` → 触发业务 → `ch_wasm_analyze` → `ch_wasm_read` → `ch_wasm_validate`。

静态命中与时间窗口关联只能当候选，**未完成运行时/复现验证时禁止宣称算法已还原**。

---

## 十、调用栈与异步链

| 方式 | 工具 | 适用场景 |
|------|------|---------|
| `console.trace()` / `Error().stack` | Hook 内打印 | 快速定位 |
| XHR 断点 + Call Stack | `ch_breakpoint_set_xhr` → `ch_debugger_wait_paused` → `ch_debugger_get_call_frames` | 需要读闭包 |
| 作用域变量 | `ch_debugger_get_scope` | 明文/密钥/IV |
| 反调试暂停洪水 | `ch_debugger_side_capture` | 不能让页面停住时 |

**栈帧缺失**更常见的原因：

- V8 默认只保留顶部约 10 帧（可先 `Error.stackTraceLimit = 100`）
- Promise / 回调 / Worker / iframe 等异步或跨 Realm 边界
- `eval` / `Function` 动态代码
- Source Map 缺失
- 混淆器重写控制流
- 页面改写了 `Error.prepareStackTrace`

> 栈帧可能因默认深度限制、异步边界、跨 Realm、动态代码和混淆而缺失；打印栈不足时使用硬断点、异步调用栈或 CDP。  
> **不要把丢栈主要归因于“尾调用优化”。**

V8 异步栈主要补充 `await`、`Promise.all` / `any` 等有限场景，不是所有异步链都能完整恢复。

---

## 十一、动态代码与模块加载

```text
eval / Function
setTimeout("string") / setInterval("string")
URL.createObjectURL + Blob
HTMLScriptElement.src / Node.appendChild
dynamic import()
webpack chunk loader / Vite 动态 chunk
```

很多混淆器把第二阶段放进字符串、Blob URL 或动态 chunk，而不是初始 `document.scripts`。

工具：`ch_find_runtime_script(marker=...)`（需在目标脚本执行前启用 Debugger）→ 必要时 `ch_debugger_side_capture`。

---

## 十二、静态搜索与打包器运行时

### 搜索维度优先级（稳定的是协议字段，不是形参名）

生产压缩后：

```js
function sign(timestamp, nonce) {}
// 可能变成
function a(e, t) {}
```

**较稳定的是**：

- 对象属性字符串、请求字段名、Header 名、URL 参数名
- 错误信息、算法常量、PEM 头、OID、长字符串常量

因此维度应写成：**协议字段名与字符串常量**，而不是「函数形参名通常不变」。

按命中率大致排序：

1. **协议字段 / Header / Query 名**：`sign=`、`nonce=`、`X-Sign`、`token=`
2. **URL / 接口路径片段**
3. **请求库拦截器模式**：`interceptors.request.use`、`transformRequest`
4. **请求头设置**：`setRequestHeader`、`headers[`
5. **加密关键词 / 库指纹**：`encrypt`、`CryptoJS`、`subtle`、`sm2`

### 工具映射

| 搜索目标 | 工具 |
|---------|------|
| 已加载脚本关键词 | `ch_search_loaded_scripts(q=...)` |
| 分段读源码 | `ch_script_get_source(script_id, start_line, end_line)` |
| 密文/明文片段反查 | `ch_cipher_search(query=...)` |
| 服务端直连抓脚本 | `ch_fetch_url(url, grep=...)` |
| Webpack/Vite moduleId | `ch_index_modules` |

大 bundle 命中后**必须分段读**，禁止无范围拉整文件。`runtime_*` 合成 ID 精读外部脚本时用 `ch_fetch_url(script_url)`。

---

## 十三、Source Map 还原

不要一上来盲猜 `xxx.js.map`。顺序：

1. 检查 JS 尾部 `//# sourceMappingURL=`
2. 检查响应头 `SourceMap`（优先级高于文件内注释）
3. 检查旧版 `X-SourceMap`
4. 查看 DevTools Developer Resources
5. 手动加载本地 Map
6. 最后再尝试常见路径

工具：`ch_sourcemap_resolve` / `ch_sourcemap_parse` / `ch_sourcemap_search`。

---

## 十四、密文特征与算法判断（候选，非定论）

**先看密文长相，再决定搜索方向。** 下表只是**候选推断**，必须结合上下文验证。

| 特征 | 更严谨的推断 | 后续搜索关键词 |
|------|-------------|----------------|
| 三段 `.` 分隔 | 更像 JWS/JWT；JWE Compact 是**五段**；header 可再看 `alg` | `jwt`, `sign`, `HS256`/`RS256` |
| Base64 字符集 `A-Za-z0-9+/` | 只是编码；**Base64URL** 可能用 `-_` 且**没有 `=`** | `btoa`, `atob`, `base64` |
| 纯 Hex 且偶数长度 | 只是二进制转 Hex，**不能直接判断算法** | `hex`, `toString(16)` |
| 长度是 16 字节倍数 | 可能是带填充的 AES-CBC/ECB；**CTR/GCM 不一定满足** | `CryptoJS.AES`, `AES-GCM`, `subtle` |
| 固定约 128/256 字节（或对应 Base64 长度） | 可能是 1024/2048 位 RSA 运算结果 | `JSEncrypt`, `RSA`, `forge` |
| 32/40/64 字符 Hex | 可能是 MD5/SHA-1/SHA-256/SM3，**仅候选** | `md5`, `sha256`, `sm3` |
| 自定义字母表或频繁 `+`/`/` | 自定义 Base64 变体 | `_keyStr`, `_b64` |

**ECB 模式识别**：固定其他参数只改一个输入；若明文重复分组导致密文出现重复片段，才倾向 ECB。

---

## 十五、控制变量与差分实验

固定其他参数，只改一个输入，观察密文变化：

1. 只改时间戳 → 哪些密文段变（时间是否入签）
2. 只改请求体 → 全变还是部分变（签名范围）
3. 重复相同请求 → 是否相同（是否有随机/时间）

**前提**：先定位并尽可能冻结随机源与时间源（见第六节），否则差分会被 nonce/IV 污染。

---

## 十六、响应解密定位

不要只盯请求加密。常见模式是请求明文、响应在拦截器里统一解密：

```text
Response.prototype.json / text / arrayBuffer
XMLHttpRequest response getter
WebSocket onmessage
axios response interceptor / transformResponse
decrypt / decode / unpack
```

流程：`ch_listener_read` 看响应形态 → 搜索 `transformResponse`/`decrypt` → Hook 响应解码边界 → 跟栈。

---

## 十七、反调试、反 Hook 与完整性检测

注入 Hook 前若存在无限 `debugger;`、定时器检测、原型链完整性校验：

- 先用 `ch_anti_debug_bypass`
- 页面白屏/卡顿/刷屏时**立即** `capture_profile="safe_capture"`，不要继续 `full`
- `safe_capture` 仍保留 SubtleCrypto/网络/高价值日志；Console 不回显不等于证据丢失（改读 `ch_injection_evidence`）

---

## 十八、混淆器识别与 JSVMP 降级策略

定位前先识别混淆类型，再选策略。

> **动态捷径 ≠ 跳过解混淆**：XHR / Call Stack / scope 可以先定位入口与运行时值；但要读混淆源码、静态搜关键字或交付算法复现时，必须先评分并解混淆（或走 JSVMP 专用链），禁止「看到混淆就绕开」。

| 混淆类型 | 识别特征 | 定位策略 |
|---------|---------|---------|
| **JSVMP** | 巨大数组 + `while`/`switch` 分发器 | 不要硬跟栈；`ch_jsvmp` 指纹；无 execution_trace 禁止宣称已还原 |
| **obfuscator.io** | `_0x` + 字符串数组偏移 | `ch_obfuscation_score` → `ch_deobfuscate_auto` 后再搜；精细控档再用 `ch_deobfuscate_js` |
| **sojson** | 多层 `eval` + 反格式化 | 先过反调试，再搜特征；可读性不足时同样先解混淆 |
| **AAEncode** | 颜文字 | 先解码再搜 |
| **Webpack** | `__webpack_require__` + moduleId | `ch_index_modules` |

工具：`ch_obfuscation_score(script_id)`，≥50 必须解混淆或 JSVMP 分流；≥70 可并行动态调试。高分 ≠「有加密」。解混淆结果只是候选，须活体/协议验证。

---

## 十九、内存搜索（大方向）

> **定位里的「内存搜索」**：在运行时已存在的存储介质中，用**已知短探针**（明文片段、密文 hex、IV、salt、PEM、协议字段值）找回残留对象或字节区域，再反推「最后写入点」。  
> 它解决的是 Hook 断点找不到、或只看到密文看不到中间态时的缺口；**不能替代** Network Initiator、静态搜索与发送层 Hook。

### 19.1 为什么是大方向

现代签名/加密经常出现这些现象：

| 现象 | 内存搜索的价值 |
|------|----------------|
| 算法在 Wasm / JSVMP 内，JS 栈几乎无业务帧 | 在线性内存或堆残留里找明文、密钥、S-Box、中间 hash |
| 只 Hook 到 `fetch`，入参已是最终密文 | 在缓冲/堆里回搜「签名前原文」或规范化串 |
| Web Crypto 的 CryptoKey 不可导出 | 搜 importKey 前后的 raw 字节、JWK JSON、PEM 残留 |
| 控制变量密文全变 | 在内存里对齐 nonce/IV/时间字段，确认差分噪声来源 |
| Worker / iframe 多 Realm | 主线程 Hook 落空时，在对应 Realm 的堆或 Wasm 内存里搜同一探针 |

核心闭环：

```text
已知探针（明文/密文/IV/字段值）
  → 在对应内存层命中 offset / 对象引用
  → 看前后文与谁持有该缓冲
  → 回到写入 API（TextEncoder / Memory 写入 / 密码库 / export）
  → 断点或 Hook 取闭包 → 本地复现验证
```

### 19.2 何时启用（触发条件）

**优先启用**（有明确探针时）：

1. 已抓到请求密文/签名，但静态搜索与发送层 Hook 未给出生成函数
2. 已确认 Wasm 参与（`.wasm` / `WebAssembly.instantiate`），需要看线性内存输入输出
3. 怀疑密钥、设备指纹、预计算表在堆或 IndexedDB 相关对象中残留
4. 差分实验需要确认「哪一段字节随输入变、哪一段是随机/时间」

**暂缓或降噪**：

- 还没有任何短探针（盲扫整堆极易 OOM、误报）
- 页面已卡顿 / 处于应使用 `safe_capture` 的状态（大块内存拷贝会加重卡顿）
- 探针短于 4～8 字节（ASCII）或短于 8～16 hex 字符（二进制）——误报率过高

### 19.3 四层模型（必须分层，禁止混为一谈）

```text
┌─────────────────────────────────────────────────────────┐
│  A. JS 堆对象层     字符串、普通对象、闭包、库单例         │
├─────────────────────────────────────────────────────────┤
│  B. 二进制缓冲层    ArrayBuffer / TypedArray / DataView   │
├─────────────────────────────────────────────────────────┤
│  C. Wasm 线性内存   WebAssembly.Memory.buffer             │
├─────────────────────────────────────────────────────────┤
│  D. Native / 进程   Frida、调试器（非本工具网页主责）       │
└─────────────────────────────────────────────────────────┘
```

| 层 | 典型残留 | 首选手段 | 本项目能力 |
|----|----------|----------|------------|
| **A. JS 堆** | 明文 JSON、规范化待签串、PEM、JWK、错误信息、配置对象 | Chrome Memory → Heap snapshot → 按字符串搜索；调试器 Scope | `ch_debugger_get_scope`、`ch_page_run_js` 读已知全局；**无通用整堆扫描 MCP** |
| **B. 缓冲** | IV、key raw、UTF-8 字节、protobuf 帧 | Memory Inspector；对已知 `Uint8Array` 做 hex/ASCII 子串搜索 | `ch_page_run_js` 对已定位缓冲搜索；注入日志里的 hex 预览 |
| **C. Wasm** | 堆上明文、输出密文、常量表、S-Box | `__ch.wasmSearch` / `wasmRead` / `wasmSnapshot`；调用前后差分 | **最强**：`final_capture` WasmHook + `ch_wasm_memory_snapshot` + `ch_wasm_*` |
| **D. Native** | SO/DEX/进程堆 | Frida `Memory.scan`、x64dbg `findallmem` | **不要**用网页方法论硬套；本仓库不提供 APP 内存扫描主路径 |

> Chrome Memory Inspector 可查看 `ArrayBuffer`、TypedArray、DataView、`WebAssembly.Memory`。  
> **「纯网页只能 Heap Snapshot」是过时说法**——二进制缓冲与 Wasm 内存必须单独看。

### 19.4 探针设计（搜什么）

探针质量决定成败。按稳定性排序：

| 优先级 | 探针类型 | 示例 | 备注 |
|--------|----------|------|------|
| P0 | 协议字段**值**（非形参名） | 某次请求的 `sign` hex/base64 片段、`token` 原文 | 先从 `ch_extract_request` 取真实样本 |
| P0 | 可控明文片段 | 自己输入的昵称、固定 `appId`、订单号 | 控制变量后内存中应出现 UTF-8 |
| P1 | IV / nonce / salt | `getRandomValues` 刚产出的 12/16 字节 hex | 用 `__ch.randomValues()` / 注入日志关联 |
| P1 | 密钥材料 | PEM 头、`-----BEGIN`、JWK `"kty"`、raw key hex | CryptoKey 本身可能搜不到，搜 import 前字节 |
| P1 | 规范化待签串 | `key=value&...`、稳定排序 JSON | 常比密文更容易在堆里找到 |
| P2 | 算法常量 | AES S-Box、SHA 初始向量、SM 相关常量 | Wasm/静态库特征；误报需对照 |
| P2 | 结构魔数 | protobuf tag、msgpack、`04` 非压缩公钥前缀 | 辅助定边界 |

**编码变体要一起搜**：同一逻辑值可能以 UTF-8、Hex、Base64、Base64URL、URI 编码同时存在。至少准备 2～3 种探针编码。

**长度建议**：

- 可打印串：≥ 8 字符（特殊常量可 ≥ 4）
- Hex：≥ 16 字符（8 字节）
- 全空间盲搜高熵「疑似密钥」：只能当**候选**，必须回到写入点验证

### 19.5 标准操作流程

```text
1. 取探针
   ch_listener_read / ch_extract_request / ch_injection_evidence
   → 得到密文、明文片段、IV、字段值

2. 选层
   有 Wasm？→ 先 C 层
   只有 JS 库？→ A/B 层
   多 Realm？→ 在目标 Worker/iframe 内重复

3. 短探针搜索（精确子串 / 字节序列）
   → 记录 offset、前后 32～64 字节上下文、持有对象

4. 差分（强烈推荐）
   改一个业务输入或触发一次加密
   → 再搜 / 再快照 → 看哪些区域变、哪些不变

5. 反推写入点
   TextEncoder.encode / encodeInto、Memory 写入、
   crypto.subtle.*、库 encrypt、Wasm export 调用

6. 闭环
   断点/scope 或本地复现；仅内存命中不足以结案
```

### 19.6 A 层：JS 堆对象搜索

**适用**：明文、配置、PEM、待签字符串仍以 JS `string` / 普通对象存在。

**做法**：

1. DevTools → Memory → **Heap snapshot** → 搜索字符串探针
2. 看 Retainers：谁引用了该字符串（闭包、模块单例、Vue/React fiber 等）
3. 调试暂停时用 `ch_debugger_get_scope` 读局部/闭包（比盲目扫堆更干净）
4. 已知全局/库：`ch_page_run_js` / `__ch.keys()` / `__ch.contexts` 读注入已捕获的加密上下文

**局限**：

- V8 可能对字符串做内部化、切片共享；短命临时串可能已被 GC
- 加密后立即释放的中间串可能搜不到 → 必须在加密**触发瞬间**抓快照，或改回 Hook `JSON.stringify`/`TextEncoder`
- 本项目 **没有**「一键扫描整堆」的 MCP 工具；堆搜索以 DevTools + 已知对象读取为主

### 19.7 B 层：二进制缓冲搜索

**适用**：数据已进入 `Uint8Array` / `ArrayBuffer`，尚未或不再是 JS 字符串。

**做法**：

1. Memory Inspector 打开可疑 `ArrayBuffer` / TypedArray / `DataView`
2. 对**已定位**的缓冲做子序列搜索（避免遍历页面全部堆对象）：

```javascript
// 中文注释：仅在已知 buffer 上搜索，禁止无范围扫整个 heap
function findBytes(buf, needleBytes) {
    const hay = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    const out = [];
    outer: for (let i = 0; i <= hay.length - needleBytes.length; i++) {
        for (let j = 0; j < needleBytes.length; j++) {
            if (hay[i + j] !== needleBytes[j]) continue outer;
        }
        out.push(i);
    }
    return out;
}

// 明文 UTF-8
findBytes(someUint8Array, new TextEncoder().encode('my_probe_plaintext'));

// 密文 / IV 的 hex → bytes
function hexToBytes(hex) {
    const h = hex.replace(/\s+/g, '');
    const u8 = new Uint8Array(h.length / 2);
    for (let i = 0; i < u8.length; i++) u8[i] = parseInt(h.substr(i * 2, 2), 16);
    return u8;
}
findBytes(someUint8Array, hexToBytes('a1b2c3d4e5f60708'));
```

3. 关注 `TextEncoder.encodeInto`：它常把字符串**直接写入** TypedArray 或 Wasm 堆，是 A→B→C 的桥

**与注入证据的关系**：`final_capture` 对 SubtleCrypto / 编码边界会打 hex 预览；先 `ch_injection_evidence` / `ch_get_entry`，再决定对哪个缓冲深挖。

### 19.8 C 层：Wasm 线性内存搜索（本项目主战场）

**适用**：签名/加密在 Wasm 内，或 JS 只负责把字节拷进 `exports.memory`。

**页面内调试 API**（`final_capture` 注入后，在页面控制台或 `ch_page_run_js`）：

| API | 作用 |
|-----|------|
| `__ch.wasmInstances` | 已拦截的实例列表与 memory |
| `__ch.wasmSearch(keyword, idx?)` | 在指定实例线性内存中按 **UTF-8 关键字**搜索，返回 offset 列表 |
| `__ch.wasmRead(offset, len?, idx?)` | 读一段内存，输出 hex + utf8 |
| `__ch.wasmSnapshot(idx?)` | 整段 memory → 后端 `/api/wasm/memory-snapshot` |
| `__ch.wasmExports()` / `__ch.wasmClues()` | 导出调用热度与模块线索 |

```javascript
// 中文注释：先搜可控明文，再读命中点前后文
__ch.wasmSearch('order_id_12345');
__ch.wasmRead(0x1a2b0, 128, 0);
```

**MCP / 后端**：

| 工具 | 作用 | 注意 |
|------|------|------|
| `ch_wasm_start` / `ch_wasm_analyze` / `ch_wasm_status` | 任务与摘要 | 先看摘要与 next_actions |
| `ch_wasm_read` | 按 kind 精读 function/interaction/logs/artifact | 必须带 `kind`+`limit`，禁止一次拉全量 |
| `ch_wasm_memory_snapshot` | 上传 memory base64，分析可打印串与高熵块 | 高熵「疑似密钥」仅为候选 |
| `ch_wasm_validate` | 结案前检查证据是否齐 | `can_claim_solved=false` 时禁止宣称已解 |

**调用前后差分（强烈推荐）**：

```text
触发加密前：__ch.wasmSnapshot(0) 或对关键 ptr 区间 __ch.wasmRead
触发加密后：再 snapshot / read
对比：哪些 offset 变为明文输入，哪些变为输出摘要/密文
再对「变化区」用密文探针反查，确认输出缓冲区
```

`final_capture` 在 export 包装里会对指针参数做有限长度的前后内存对比（有速率限制，重页可能跳过快照以防 OOM）。分析时优先读已有 wasm 交互日志，不要对热路径无节流地狂打 snapshot。

**静态侧补充**：Wasm 二进制里的常量表/密码特征可用 `ch_wasm_crypto_functions`、静态签名扫描；这与**运行时线性内存搜索**互补，不能互相替代。

### 19.9 和「密文搜索」工具的区别（避免用错）

| 能力 | 搜的对象 | 工具 |
|------|----------|------|
| **内存搜索** | 运行时堆 / ArrayBuffer / Wasm Memory | DevTools、`__ch.wasm*`、`ch_wasm_memory_snapshot`、定向 `ch_page_run_js` |
| **密文/日志反查** | 已捕获的 listener、注入日志、crypto-context | `ch_cipher_search` |
| **脚本源码搜索** | 已加载 JS 文本 | `ch_search_loaded_scripts` |

`ch_cipher_search` **不会**扫描浏览器堆或 Wasm 内存。内存未命中时，用它确认「探针是否至少在日志里出现过」是有用的，但不要当成内存扫描。

### 19.10 多 Realm 下的内存搜索

主页面搜不到时，按 Realm 重复：

1. 列出 Worker / iframe / SharedWorker / ServiceWorker
2. 在**目标 Realm** 内取同一探针（或读该 Realm 的注入日志）
3. Worker 内 Wasm 的 `Memory` 与主线程不是同一块缓冲
4. 主线程 `__ch.wasmSearch` 只覆盖主线程已 hook 到的实例

### 19.11 证据标准与常见误判

**可接受的内存证据（仍需闭环）**：

- 可控明文在加密触发后出现在 Wasm 内存或 TypedArray，且 offset 与 export 参数指针一致
- 请求中的密文/签名字节在输出缓冲区命中，并与调用时间对齐
- 同一 IV/nonce 在 `getRandomValues` 记录与内存区同时出现

**常见误判**：

| 误判 | 真实情况 |
|------|----------|
| 高熵块 = 密钥 | 可能是压缩数据、图片、随机填充、已封存密文 |
| 搜到密文 = 找到算法 | 可能只是发送缓冲或日志残留，生成点在别处 |
| Heap 未命中 = 无明文 | 可能已 GC，或从未以 JS 字符串存在（只在 Wasm/TypedArray） |
| 主线程未命中 = 无此数据 | 数据在 Worker/iframe Realm |
| Base64 搜不到 | 内存里是原始字节或 Base64URL |

### 19.12 禁忌

- 不要无探针整堆/整 Memory 盲扫（易卡死、OOM、误报）
- 不要在 `safe_capture` 恢复期对故障页狂打全量 memory snapshot
- 不要把 `ch_cipher_search` 或脚本搜索当成内存搜索
- 不要仅凭内存命中或静态常量命中宣称算法已还原
- 不要把 Frida/native `findallmem` 流程原样套到纯网页任务
- 不要忽略编码变体与多 Realm
- 差分前尽量冻结或记录随机/时间源，否则「全变」无法解释

### 19.13 Local Overrides（相关手法，非内存搜索本身）

DevTools Overrides 或 Fiddler AutoResponder 把目标 JS/Worker 落到本地并插入 `debugger` / 额外 dump，适合反复调试同一写入点；与内存搜索配合时，可在写入前打断并立刻 `wasmRead`/Inspector 观察缓冲。

---
## 静态搜索速查（门禁快速通道）

调用以下工具并返回命中时，定位门禁**自动解除**：

| 定位工具 | 自动置位条件 |
|---------|------------|
| `ch_search_loaded_scripts(q="关键词")` | `match_count > 0` 或 `matches` 非空 |
| `ch_cipher_search(query="密文片段")` | `total > 0` 或 `results` 非空 |

每次 `ch_cdp_start`（新浏览器会话）重置门禁。

### 定位完成的证据标准（至少一项）

| 证据 | 对应工具 | 自动置位 |
|------|---------|:---:|
| 静态搜索命中并确认位置 | `ch_search_loaded_scripts` + `ch_script_get_source` | ✅ |
| 密文/明文片段反查命中 | `ch_cipher_search` | ✅ |
| Hook/注入截获加密调用栈 | `ch_page_run_js` / `ch_injection_evidence` | 需结合确认 |
| 内存搜索命中明文/密钥/中间态并回到写入点 | `__ch.wasmSearch` / Memory Inspector / `ch_wasm_memory_snapshot` | 需结合确认 |
| 密文特征仅作算法候选 | 肉眼分析 | 必须结合其他证据 |

---

## 不要做

- 不要不先看 Network Initiator / 密文就直接盲设断点
- 不要不先搜索就直接全局 Hook
- 不要把 JSON/Base64 当成「必经之路」
- 不要用 `Proxy(window)` 当透明全局拦截（Proxy 只作用于**通过该 Proxy 引用**的操作；适合包裹已定位对象/imports/导出对象）
- 不要只在主线程 Hook `importScripts` 指望覆盖 Worker
- 不要在框架代码里盲目 F11（跟了 20 步还没业务代码 = 方向错了）
- 不要忘记多 Realm / 内存搜索（堆/缓冲/Wasm）/ 响应解密 / 非确定性源
- 不要无探针盲扫整堆或整段 Wasm Memory；不要把 ch_cipher_search 当成内存扫描
- 不要把 native 内存扫描套用到纯网页 JS
- 不要所有目标用同一套 Hook；先识别混淆类型
- 不要在 `association_quality=static_only` 或无 Wasm/JSVMP 运行时证据时宣称算法已解

### 更可靠的全局拦截替代

- `Object.defineProperty` 替换明确的全局属性
- 包裹特定库对象 / Wasm imports
- CDP 函数断点 / 文本断点
- AST 插桩
- 脚本执行前注入（Instrumentation / early inject）
