# facebook_login — Facebook Web 登录请求逆向

> 站点：https://www.facebook.com/  
> 工具：crypto-hunter-lite（listener 抓包 + 页面 `require('FBBrowserPasswordEncryption')` + 本地 Python 复现）  
> 日期：2026-07-22  
> 验证样本：随机假账号（**不使用**截图中的真实邮箱）

## 结论

| 项 | 值 |
|----|----|
| 登录入口 | `POST https://www.facebook.com/api/graphql/` |
| GraphQL | `fb_api_req_friendly_name=useCDSWebLoginMutation`，`doc_id=9807605492696448`（可能轮换） |
| 账号字段 | `variables.input.identifier` |
| 密码字段 | `variables.input.enc_password.sensitive_string_value`（`password` 字段同值） |
| 加密格式 | `#PWD_BROWSER:5:<unix_ts>:<base64>` |
| 公钥来源 | 首页 SSR：`caa_password_encryption_data.encryption_data`（实测 `key_id=148`） |
| 算法模块 | `FBBrowserPasswordEncryption.encryptPassword` → `EnvelopeEncryption.encrypt` |

### `#PWD_BROWSER:5` 算法

1. 随机 32 字节 AES key  
2. **AES-256-GCM**：nonce = 12 字节 `0x00`；AAD = 秒级时间戳 UTF-8；明文 = 密码 UTF-8  
3. **NaCl SealedBox**（Curve25519 + XSalsa20-Poly1305）用页面 `public_key` 封装 AES key（密文长度固定 80）  
4. 二进制拼接后标准 Base64：

```text
[1][key_id][sealed_len:u16le][sealed_key][gcm_tag:16][ciphertext]
→ #PWD_BROWSER:5:<ts>:<b64>
```

浏览器捕获样例结构：`v0=1, kid=148, sealedLen=80, tag_cipher=16+len(password)`。

## 证据

- 监听器：`lst_d6a54589775f44c4`，请求 `21424.338` / `21424.345`
- 响应：`caa_login_web.error_code=1348131`，文案「你输入的登录信息有误…」
- WebCrypto 捕获：登录前 `generateKey(AES-GCM)` + `encrypt(AES-GCM)`，`dataLen` = 明文密码长度
- 页面内调用：`require('FBBrowserPasswordEncryption').encryptPassword(148, pub, pwd, ts)` → `#PWD_BROWSER:5:...`
- 公钥 HTML：`"caa_password_encryption_data":{"encryption_data":{"key_id":148,"public_key":"c5c61f9b..."}}`
- 注意：同页还有 `InstagramPasswordEncryption`（`key_id=132`, `version=10`），**不要混用**

## 本地复现

```bash
pip install pycryptodome pynacl
python cases/facebook_login/repro.py
# 仅测加密格式：
python cases/facebook_login/repro.py --offline-only
```

`repro.py` 会：

1. 随机生成假邮箱/密码（或 `--email` / `--password`）  
2. 本地生成 `#PWD_BROWSER:5` 并断言 payload 结构  
3. GET 首页提取 `key_id` / `public_key` / `lsd` / `jazoest`  
4. POST GraphQL；随机账号期望 `error_code=1348131`（协议接受加密载荷）

## 踩坑记录

| 误判 | 真实原因 | 识别信号 | 修复 |
|------|----------|----------|------|
| 登录是 form POST 到 `/` | 现已是 Comet GraphQL mutation | `x-fb-friendly-name: useCDSWebLoginMutation` | 盯 `/api/graphql/` |
| Hook body 截断丢 `enc_password` | 中间件只留了前 4KB | `body_len≈4000` 且 `enc_near=null` | 不截断保存 / 用 listener extract |
| 用 Instagram 公钥 | 同页两套密钥 | `InstagramPasswordEncryption` vs `caa_password_encryption_data` | 只用 `caa_password_encryption_data` |
| `ch_page_run_js` 直接 `await` 返回空 | CDP as_expr 不自动 await Promise | `result: {}` | `.then` 写 `window.__x` 再读 |
| 登录按钮 `button[name=login]` 找不到 | 现为 `div[role=button][aria-label=登录]` | find-element 命中 DIV | JS `.click()` 或按 aria-label |

## 验证结果

- 离线：payload 结构与浏览器捕获一致（`kid=148`, `sealedLen=80`）
- 页面：`encryptPassword` 输出 `#PWD_BROWSER:5:...`
- **Python 密文投递闭环（关键）**：用 `repro.encrypt_password(...)` 生成密文，替换进浏览器捕获的完整 `variables` 后 `fetch('/api/graphql/')` → **`error_code=1348131`** / 「你输入的登录信息有误」——证明本地算法与线上一致
- 纯 urllib live：需带齐 `caa_login_request_extra_info`（含 `shared_prefs_data` 等）；缺字段可能先报 GraphQL `noncoercible_variable_value`，与加密无关

## 依赖

```text
pip install pycryptodome pynacl
```