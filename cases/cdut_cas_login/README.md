# 成都理工大学 CAS (cas.paas.cdut.edu.cn) — 登录密码加密参数逆向

> 目标站点：`https://cas.paas.cdut.edu.cn/cas/login`
> 业务入口：教务 `jw.cdut.edu.cn` SSO
> 日期：2026-07-19
> 复现脚本：`cases/cdut_cas_login/repro.py`（纯 Python 标准库）

## 结论：密码用 **RSA-2048（PKCS#1 v1.5）+ `__RSA__` 前缀**

| 项目 | 内容 |
|------|------|
| 算法 | JSEncrypt → RSA-2048 / PKCS#1 v1.5 → Base64 |
| 字段变换 | `password = "__RSA__" + encrypt.encrypt(明文密码)` |
| 公钥 | `GET /cas/jwt/publicKey`（PEM，`encryptEnabled=true`） |
| username | **明文** |
| 提交 | `POST /cas/login?service=...` 表单 `#fm1` |

### 加密公式

```text
password_field = "__RSA__" + base64( RSAES_PKCS1_v1_5( password_utf8, publicKey ) )
```

- 密文长度：256 字节 → 344 字符 Base64 → 加上前缀共 **351** 字符
- RSA 随机填充，**两次密文不同**，不能逐字节比对；以长度/前缀/公钥可解析为验证标准

### 前端调用链

```js
// 页面初始化
var encrypt = new JSEncrypt();
$.get("/cas/jwt/publicKey", function(publicKey){
  encrypt.setPublicKey(publicKey);
});

// 提交前（Vue 登录按钮 / mfaDetect）
if (encryptEnabled && password.indexOf('__RSA__') < 0) {
  var encodedPassword = "__RSA__" + encrypt.encrypt(password);
  $("#fm1").find("#password").val(encodedPassword);
}
// mfaEnabled=false 时直接 submitFm1()；为 true 时先 POST /cas/mfa/detect
```

## 登录请求字段（`#fm1`）

| 字段 | 说明 |
|------|------|
| `username` | 学工号/邮箱/证件号/手机等（明文） |
| `password` | `__RSA__` + RSA 密文 |
| `captcha` | 图形验证码；`failN >= captchaSkipN(3)` 时需要 |
| `execution` | CAS 流式票据（页面隐藏域，一次性，很长） |
| `_eventId` | `submit` |
| `currentMenu` | `1`（账密登录） |
| `failN` / `mfaState` / `fpVisitorId` / `geolocation` / `trustAgent` | 风控/指纹相关，可空或页面默认 |
| `rememberMe` | 可选 |

验证码图片：`/cas/captcha.jpg?r=<ts>`

## 验证

```bash
E:\python-word\Scripts\python.exe cases/cdut_cas_login/repro.py --self-test
# → 公钥 2048-bit / e=65537 / cipher 256B / b64 344 / 前缀 __RSA__ / execution 可解析 → PASS
```

组装登录字段（不强制真实登录成功）：

```bash
E:\python-word\Scripts\python.exe cases/cdut_cas_login/repro.py <账号> <密码>
# 加 --post 才会真正 POST（需有效账号；验证码场景另传 --captcha）
```

## 证据清单

- target_request：`POST /cas/login?service=...`（`#fm1`）
- cipher_or_sign：`password = __RSA__ + JSEncrypt.encrypt(明文)`
- source_code：页面内联 `JSEncrypt` + `/cas/jwt/publicKey` + 提交前赋值
- runtime_scope：`encryptEnabled=true`，`mfaEnabled=false`，`JSEncrypt` 已加载
- reproduction_code：`cases/cdut_cas_login/repro.py`
- validation：本地 self_test PASS（长度/前缀/公钥/execution）

## 踩坑记录

| 误判 | 真实原因 | 识别信号 | 修复 |
|------|----------|----------|------|
| 当成东软 `strEnc`（sdu/jnu） | 本站是 PaaS CAS + JSEncrypt | 有 `jsencrypt.min.js`、`/cas/jwt/publicKey`、无 `des.js` | 走 RSA 路径 |
| 只加密密码无前缀 | 服务端靠 `__RSA__` 识别密文 | 源码 `indexOf('__RSA__')` | 必须加前缀 |
| MFA 必调 `/cas/mfa/detect` | 当前 `mfaEnabled=false` 直接 `submitFm1` | `var mfaEnabled = "false" == "true"` | 以 globalConfig 为准 |
| 复用旧 `execution` | CAS 一次性 | 每次 GET 登录页刷新 | 先拉页再 POST |
