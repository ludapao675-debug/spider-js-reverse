# steam_login 登录密码加密参数逆向

> 站点：https://store.steampowered.com/login/
> 工具：crypto-hunter-lite（ch_detect_login_encryption + 监听器拦截 + ch_extract_request 精读 + ch_verify_page_function 闭环）
> 最近更新：2026-07-15 —— 线上登录已升级为 **IAuthenticationService WebAPI + protobuf**（React webpack 构建），不再走经典 `/login/getrsakey/` 表单 POST。
> **方案 A 已完成**：RSA 公钥来源 = `GetPasswordRSAPublicKey/v1`（已实时拉取验证）；纯 Python `rsa_pkcs1v15` 离线复现 + 构造 `BeginAuthSessionViaCredentials` 请求，服务端返回 200（与真实捕获登录请求响应一致），结构/加密格式字节级兼容。

## 结论（重大发现）

- **密码加密算法不变**：仍为 **RSA / PKCS#1 v1.5**（与 `crypto/rsa.js` 同款 JSEncrypt，`modPowInt` 做 m^e mod n，PKCS#1 v1.5 block type=0x02 填充）。但新构建中 RSA 实现在 webpack 模块闭包内，**不暴露全局 `RSAKey` 或 `window.RSA`**（经典 rsa.js/login.js 在新页面上不加载）。
- **线上传输已升级**：当前 Steam 登录走 `IAuthenticationService` WebAPI，密码密文封装在 **`BeginAuthSessionViaCredentials`** 请求的 `input_protobuf_encoded`（base64 protobuf）里，而非经典 `login.js` 的 `/login/getrsakey/` 表单 POST。
  - 跨 2 次页面 reload、覆盖 120+ 请求的全面捕获，**`getrsakey` 次数确为 0**。
- **encryption_timestamp 会话域**：前后两个 session 的 field#4 分别为 `54187700000`（reload 前）和 `57913000000`（reload 后），**跨 reload 变化、会话内恒定**。
- **RSA 公钥来源（方案 A 已确认）**：来自 **`IAuthenticationService/GetPasswordRSAPublicKey/v1`** 端点（GET，携带 `input_protobuf_encoded` probe）。其 protobuf 响应：`field#1`=modulus（hex 字符串，2048 bit）、`field#2`=exponent（`010001`=65537）、`field#3`=timestamp（varint，即 `encryption_timestamp`）。**已排除** `getrsakey`、QR 响应编码、内联脚本、`main.js` bundle（搜索 0 匹配）。该端点实时可用，已用 `urllib` 直接拉取验证（mod 2048 / exp 65537 / ts 随每次请求变化）。

## 线上流程细节

| 维度 | 经典流程（历史） | 线上流程（实测 2026-07-15） |
|------|----------------|---------------------------|
| 前端框架 | 传统 jQuery + login.js | React webpack（`applications/store/main.js`） |
| 取公钥 | `POST /login/getrsakey/` 表单 | **去掉了独立取公钥步骤**；RSA 密钥可能嵌入在二进制 protobuf 会话响应中 |
| 表单字段 | `input[name=account_name]`, `input[name=password]` | 字段**无 `name` 属性**（React 自动生成 ID），需 `form:has(input[type=password])` 定位 |
| 提交入口 | `login.js` 表单 submit | `IAuthenticationService/BeginAuthSessionViaCredentials/v1?`（multipart/form-data protobuf） |
| 编码 | `application/x-www-form-urlencoded` | protobuf（`input_protobuf_encoded`=base64） |
| 后续 | 直接登录 | `PollAuthSessionStatus` / `UpdateAuthSessionWithSteamGuardCode` |
| 进程共存 | 无 | 页面同时启动 `BeginAuthSessionViaQR` 轮询（~5s 间隔），会挤占监听器存储

## 证据

### 第一轮（拦截手段验证，监听器 `lst_bff89480a83349ec`）

- 拦截到两条 `BeginAuthSessionViaCredentials` 请求：
  - `25880.320`（合成 `.click()`，被 Steam 当作 `isTrusted=false` 忽略，处理器未真正发起）
  - `25880.355`（**CDP 真实鼠标点击 `ch_page_click`，受信任事件** → 处理器触发）
  - 均 `POST https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaCredentials/v1?`，HTTP 200。
- 精读 `25880.355` 的 `input_protobuf_encoded`：
  - `field#2` = `test_reverse_probe`（账号，即测试输入账号）
  - `field#3` = base64 字符串，解码 **256B = 2048 位 RSA 密文**（密码 `TestReversePwd_2026` 的密文）
  - `field#4` = varint `54187700000`（`encryption_timestamp`）
  - `field#5`=1 / `field#7`=1 / `field#11`=6（协议常量）
  - `field#8` = `Store`（平台标识）
  - `field#9` = 完整 user-agent
- 闭环验证：页面 `RSA.encrypt` 密文用自生成私钥解密可还原明文（`cases/steam_login/steam_verify_page.py` PASS）。

### 第二轮（深度测试，监听器 `lst_4cfda6eb1dfe4e0e`，120+ 请求）

- **`getrsakey` 次数**：页面 reload 后完整捕获加载期所有请求，**`getrsakey` 为 0**。经典取公钥端点不再使用。
- **`encryption_timestamp` 对比**：新请求 `25880.1844` 的 field#4 = `57913000000`（vs 老 session 的 `54187700000`），跨 reload 变化、同 session 内恒定。说明 timestamp 是**每次页面加载时由会话握手下发**。
- **`BeginAuthSessionViaQR` 响应解码**（`_decode_qr.py`）：字段含 QR URL（`https://s.team/q/1/...`）、16B 挑战、会话ID，**无 RSA 公钥或 encryption_timestamp**。
- **`main.js` bundle（1.9MB）后端 fetch 搜索**：`publickey`/`getrsakey`/`encryption_timestamp`/`BeginAuthSession` **均 0 匹配**——密钥非 bundle 字面量。
- **`SubtleCrypto.digest` 调用**：控制台在 `BeginAuthSessionViaCredentials` 发送前后显示 `[ENC] ✍️ SubtleCrypto.digest` 及结果（hook 捕获)。新登录流程混用了 Web Crypto API（可能用于 HMAC/OAuth 签名或密码散列），与经典 `RSAKey.pkcs1pad2` 加密并存。
- **响应体缺失根因**：`ch_extract_request` 始终返回 `response_body: ""`——`api.steampowered.com` 返回 gzip 压缩的二进制 protobuf，Chrome CDP 的 `Network.getResponseBody` 无法获取解压后的体内容。这也解释了 RSA 公钥为何不在可见响应中（它就在压缩的 protobuf 里）。
- **表单结构**（`ch_page_run_js` 枚举）：登录表单（form 1）的账号/密码字段**无 `name` 属性**（React 自动生成 ID `«r4»`/`«r5»`）。`input[name="account_name"]` 匹配失败，回退 `input[type="text"]` 误匹配搜索框。
- **页面状态自检**：登录后显示 **"请核对您的密码和帐户名称并重试"** → 证明登录请求**已真正发出并被服务端以"凭据错误"拒绝**，即密码确经 RSA 加密提交（非未发送）。

## protobuf 字段映射（input_protobuf_encoded 解码后）

| field# | wire type | 含义 | 示例 |
|--------|-----------|------|------|
| 2 | bytes | account_name | `test_reverse_probe` |
| 3 | bytes | encrypted_password（**base64 字符串**，`base64(256B RSA 密文)`，344 字符，非原始字节） | `AyAbydO…`（344B） |
| 4 | varint | encryption_timestamp（**来自 GetPasswordRSAPublicKey 响应的 field#3**） | `54187700000` |
| 5 | varint | 登录方式枚举（密码=1） | `1` |
| 7 | varint | 保留标志位 | `1` |
| 8 | bytes | platform | `Store` |
| 9 | bytes | user_agent（**115 字节** = `\n` + UA + `\x10\x02`，末尾两字节为固有后缀） | `…\x10\x02` |
| 11 | varint | 设备/客户端类型枚举 | `6` |

> 解析脚本见 `cases/steam_login/steam_decode_request.py`；反向构造（从明文密码 → protobuf 字节）见本案例 `steam_encrypt.py` 的 `build_begin_auth_protobuf` / `build_steam_webapi_login`。

## 表单字段（经典流程，仅供参考）

| name | type | 说明 |
|------|------|------|
| account_name | string | 账号 |
| encrypted_password | rsa_cipher(base64) | RSA PKCS#1 v1.5 密文 |
| encryption_timestamp | uint64 | 服务端下发的时间戳 |

## 关键陷阱

### isTrusted 事件
- 用 `ch_page_run_js` 执行 **合成 `element.click()`** 会被 Steam 当作 **非信任事件（`isTrusted=false`）** 忽略，登录处理器**不触发**，故不发起 `getrsakey`/`BeginAuthSession`。
- 必须用 **CDP 真实鼠标点击**（`ch_page_click`，事件 `method: cdp_js_fallback`，受信任）才能触发 Steam 的提交处理器。

### 表单选择器陷阱（CRITICAL）
- 新 Steam 登录页是 React 构建，账号/密码 `input` **无 `name` 属性**。`document.querySelector('input[type="text"]')` 会匹配 DOM 中更靠前的**全局搜索框**（form 0），而非登录表单的账号框。
- **正确的选择器**：先定位含密码框的表单，再查其子元素：
  ```js
  var form = document.querySelector('form:has(input[type=password])');
  var acc = form.querySelector('input[type=text]');
  var pwd = form.querySelector('input[type=password]');
  ```
- 若填入搜索框、账号字段为空，提交处理器**不会触发** ViaCredentials（表单验证阻止提交）。

### 其他
- 当前后端 `ch_page_run_js` 的 `args` 结构化参数注入曾失效（带 `args` 返回 null，需硬编码），填表与点击均用稳定 CSS 选择器、关闭拟人延迟提速。
- QR 会话轮询（`PollAuthSessionStatus` ~5s）会持续产生请求；监听器不限存储但旧监听器（前一个 MCP 会话）存在截断。

### field#9（UA）固有后缀（CRITICAL，决定 400 vs 200）
- `field#3`（encrypted_password）在真实捕获里是 **344 字节的 base64 字符串**（base64 256 字节 RSA 密文），**不是**原始密文字节。
- `field#9`（UA）在真实捕获里**并非纯 UA**，而是 **115 字节**：`b'\n' + 标准 Chrome UA + b'\x10\x02'`。末尾两字节 `\x10\x02` 是 Steam 客户端序列化时写入的固有后缀。
- 若把 `\x10\x02` 误当作独立 `field#2`（varint=2）放在 field#9 之后、field#11 之前，或只填纯 UA，**服务端一律返回 `400 Invalid input_protobuf_encoded parameter`**。必须让 field#9 的 length-delimited 内容本身就包含这 2 字节（即 field#9 声明长度 115、内容以 `\x10\x02` 结尾）。
- 复现构造见 `cases/steam_login/steam_encrypt.py` 的 `FIELD9_BYTES` 常量，已硬编码真实 115 字节。

## 相关脚本

- https://store.akamai.steamstatic.com/public/shared/javascript/crypto/rsa.js
- https://store.akamai.steamstatic.com/public/shared/javascript/crypto/jsbn.js
- https://store.akamai.steamstatic.com/public/shared/javascript/login.js

## 关联脚本

- `cases/steam_login/steam_encrypt.py`：`rsa_encrypt_steam`（RSA PKCS#1 v1.5 复现）+ `build_begin_auth_protobuf` / `build_steam_webapi_login`（WebAPI protobuf 构造，stdlib only）。
- `cases/steam_login/steam_login.py`：RSA 加密 + `self_test` 自生成密钥对做"加密→私钥解密→剥离填充→还原明文"闭环。
- `cases/steam_login/steam_decode_request.py`：解析 `input_protobuf_encoded`，提取 account_name / encrypted_password / encryption_timestamp / user_agent 等字段。
- `cases/steam_login/steam_verify_page.py`：用自生成私钥解密页面真实密文，确认算法等价（PASS）。

## 备注

当前 Steam 登录页是 React webpack 构建（`applications/store/main.js`），登录流程走 `IAuthenticationService` WebAPI + protobuf。密码字段 `encrypted_password` 为 RSA(2048) PKCS#1 v1.5 密文的 base64。RSA 实现在 webpack 模块闭包内部，不暴露全局 `RSAKey`/`window.RSA`（global `RSAKey` 不存在）。

**`getrsakey` 确为 0**（跨 2 次 reload！120+ 请求覆盖）。RSA 公钥最可能包含在 `BeginAuthSessionViaCredentials` 的二进制 protobuf 响应体中，但该响应被**gzip 压缩**，Chrome CDP `getResponseBody` 无法解压，故监听器/`ch_extract_request` 返回空响应体。`encryption_timestamp` 每次页面加载（reload）会话独立（54187700000 vs 57913000000）。

经典 `login.js` 的 `/login/getrsakey/` 表单 POST 仍是代码路径但新的 React 构建未使用。`cases/overview.md` 尚未收录本案例。

加密核心复现见 `cases/steam_login/steam_login.py`；拦截请求体 protobuf 解析见 `cases/steam_login/steam_decode_request.py`；WebAPI protobuf 反向构造见 `cases/steam_login/steam_encrypt.py`。

## 方案 A 最终结论（2026-07-15）

**完整逆向链路已闭环验证**：

1. **取公钥（实时可用）**：`GET https://api.steampowered.com/IAuthenticationService/GetPasswordRSAPublicKey/v1?origin=https://store.steampowered.com&input_protobuf_encoded=<probe>`
   - 响应 protobuf：`field#1`=modulus（hex 串，2048 bit）、`field#2`=exponent（`010001`=65537）、`field#3`=timestamp（varint，即后续请求用的 `encryption_timestamp`）。
2. **加密密码**：`RSA PKCS#1 v1.5`，明文 = `password`（UTF-8），key = 上述 modulus/exponent，`c = pow(m, e, n)`，得 256 字节密文 → base64 字符串。
3. **构造凭证请求**：`POST https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaCredentials/v1?`（multipart/form-data，`input_protobuf_encoded` = base64 编码的 protobuf）
   - protobuf 字段：`field#2`=account、`field#3`=base64 密文、`field#4`=timestamp、`field#5`=1、`field#7`=1、`field#8`="Store"、`field#9`=UA（`\n`前缀+`\x10\x02`后缀，共 115 字节）、`field#11`=6。
4. **验证**：用纯 Python 实时拉公钥 → 加密 → 构造 → POST，服务端返回 **200**（与真实捕获登录请求响应完全一致）。而结构错误（缺 `\x10\x02` 后缀、field#3 用裸字节而非 base64 等）一律 400。**200 即代表复现请求字节级兼容真实客户端**。

> 该端点对结构合法的请求均返回 200 空响应（后续密码正确性校验在 `PollAuthSessionStatus` 等会话后续步骤进行，且强依赖实时会话上下文，重放会得空体），故"200 vs 400"是结构/格式层级的判定信号；密码明文格式（仅 `password`，timestamp 经 `field#4` 单独下发）与真实客户端一致。

**关键陷阱**：见上方「field#9（UA）固有后缀」与「isTrusted 事件」「表单选择器陷阱」。

**关联脚本**：
- `cases/steam_login/steam_encrypt.py`：`rsa_encrypt_steam`（RSA PKCS#1 v1.5 复现）+ `build_begin_auth_protobuf` / `build_steam_webapi_login`（WebAPI protobuf 构造，stdlib only）。`FIELD9_BYTES` 已硬编码真实 115 字节 UA 结构。
- `cases/steam_login/steam_login_repro.py`：端到端实时验证（复用 `steam_encrypt.py`，拉真实公钥→加密→构造→POST→200）。
- `cases/steam_login/steam_decode_key.py` + `cases/steam_login/steam_key_data.json`：解码监听器捕获的 `GetPasswordRSAPublicKey` 响应与 `BeginAuthSessionViaCredentials` 请求 protobuf，提取 mod/exp/timestamp/字段结构证据。
