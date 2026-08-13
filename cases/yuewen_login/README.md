# 阅文通行证登录 — 密码加密参数逆向

> 站点：`https://passport.yuewen.com/yuewen.html`
> 接口：`https://ptlogin.yuewen.com/login/login`（JSONP GET）
> 日期：2026-08-13

## 结论：密码用 **RSA-1024 / PKCS#1 v1.5**，输出 **hex**（不是 JSEncrypt/base64）

```
密文 = RSAKey.encrypt(password)          # JSBN
     = hex( RSA-1024( PKCS#1 v1.5 pad(utf8(password)) ) )
长度 = 256 hex 字符（128 字节）
```

- 公钥：页面内联 `LoginV1.init({ modulus, exponent: "10001" })`，写入 `LoginV1.config`
- 库：`https://ywloginstatic.yuewen.com/rsa/rsa_encrypt.js`（`pkcs1pad2` + `RSAEncrypt`）
- 封装：`https://ywloginstatic.yuewen.com/js4/login_yw.js` 的 `rsa_encryption`
- PKCS#1 随机填充，**不能逐字节比对密文**；校验 hex 长度 256、两次加密结果不同
- 若 `encrypt()` 结果长度 ≤ 50 会回退明文（失败兜底，正常 1024 位不会走这条）

### 调用链

```js
function rsa_encryption(password) {
    var rsa = new RSAKey();
    rsa.setPublic(LoginV1.config.modulus, LoginV1.config.exponent);
    var encrypt_password = rsa.encrypt(password);
    if (encrypt_password.length > 50) return encrypt_password;
    else return password;
}

// LoginV1.login → JSONP
data.password = rsa_encryption(password);
data.method = 'LoginV1.loginCallback';
LoginV1.jsonp(baseUrl + '/login/login', data);  // nextAction===0
// nextAction!==0 时走 /login/checkcode
```

## 提交参数（JSONP GET `/login/login`）

| 字段 | 说明 |
|------|------|
| `appId` | `37` |
| `areaId` | `1` |
| `username` | 账号（可加 `loginPostfix`） |
| `password` | **RSA hex 密文** |
| `ywtoken` | 页面 `LoginV1.init` 注入，每次打开会变 |
| `code` | 图形验证码；失败码 `-11004` 时出现 |
| `sessionkey` | 验证码会话，对应 `LoginV1.codeKey` |
| `method` | `LoginV1.loginCallback`（jQuery JSONP 另带 `callback=`） |
| `format` | `jsonp` |
| `auto` | 自动登录 0/1 |
| `returnurl` / `target` / `ajaxdm` / `jumpdm` | `buildBaseData()` 公共字段 |

表单：`#username` `#password` `#txtCode` `#autologin` `#protocol1`。

## 协议对齐（假账号，2026-08-13）

成功标准：**本地 JSONP 的 `code`/`message` 与网页 `LoginV1.loginCallback` 一致**。

| 路径 | `code` | `message` |
|------|--------|-----------|
| 网页 RSA hex / 本地 `PKCS1_v1_5` hex | **72141** | 账号或密码错误，请重新输入 |
| 负向：password 发明文 | **-11016** | 您输入的账号或密码不正确，请重新输入 |

`72141` 不在 `LoginV1.errors` 表里，页面用 `data.message` 展示。明文走 `-11016` 说明服务端能区分「密文格式正确但账号错」和「没加密」。

`data.autoLoginExpiredTime` 每次不同，比对时忽略。

## 复现

```bash
python cases/yuewen_login/repro.py
```

脚本会：拉登录页解析 `modulus`/`ywtoken` → RSA hex 登录 → 与网页合同 `72141` 比对 → 再发一次明文做负向。

可选：把页面回调 JSON 传进去再对一次：

```bash
python cases/yuewen_login/repro.py --page-json "{\"code\":72141,\"message\":\"账号或密码错误，请重新输入\"}"
```

不提交真实账号。`ywtoken` 每次从 HTML 现取。

## 踩坑

- 输出是 **hex** 不是 base64；不要按 JSEncrypt 案例套。
- 登录是 **JSONP script**，不是 XHR。对齐返回应挂钩 `LoginV1.loginCallback`，或本地直接 GET JSONP。
- 失败多次可能出图形验证码 / 滑块（`nextAction` / `showSlideCode`），假账号探测未触发。本案例不覆盖验证码。
