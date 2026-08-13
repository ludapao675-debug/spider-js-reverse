# 南京大学 NJU 统一身份认证登录 — 密码加密参数逆向

> 站点：`authserver.nju.edu.cn/authserver/login`
> 目标：`oa.nju.edu.cn` 登录
> 日期：2026-07-15
> 工具：crypto-hunter-lite（Chromium @9222 + final_capture.user.js 注入）

## 结论：密码用 **AES-128-CBC** 加密（非 RSA）

### 加密公式
```
密文 = base64( AES-128-CBC( 明文 = random64(64) + password,
                             key  = utf8(pwdEncryptSalt),
                             iv   = utf8(random64(16)) ) )
```
- 填充：PKCS7；base64 输出 **不带** `Salted__` 前缀（key 以 WordArray 直传，不走 OpenSSL KDF）。
- 随机字符集：`ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678`
  （排除 I L O U 0 1 9）
- `pwdEncryptSalt`：**动态盐**，每次刷新登录页都会变（实测 `ftM1Pobp0LPQ44Fh` → `12ttwoFBUBXfwYBZ`），复现时必须实时解析。
- key = `utf8(pwdEncryptSalt)`（16 字节 → AES-128）；iv = `utf8(random64(16))`（16 字节）。

### 调用链（login.js）
```js
$("#saltPassword").val(encryptPassword($(密码框).val(), $("#pwdEncryptSalt").val()));
// encryptPassword(pwd, salt) → encryptAES → getAesString(random64(64)+pwd, salt, random64(16))
```
加密结果写入隐藏字段 `#saltPassword`（name=`password`）；可见密码框 `#password` 的值被忽略。

## 提交表单字段
| 字段 | 说明 |
|------|------|
| `username` | 账号 |
| `password` | **AES 密文**（来自 #saltPassword） |
| `captcha` | 图形验证码（**必填**，需人工识别） |
| `_eventId` | `submit` |
| `cllt` | `userNameLogin` |
| `dllt` | `generalLogin` |
| `lt` | 可能为空 |
| `execution` | 如 `e1s1` / `e2s1` |
| `pwdEncryptSalt` | 动态盐（加密 key） |

## 验证
1. 确定性比对：固定 key/iv 调浏览器 `getAesString`，Python 复算逐字节一致
   （`r26XTIZ7TTZAo7bk0K748w==`）。
2. 随机路径：Python 生成的密文为 108 字符 base64，与浏览器 `encryptPassword` 真实输出格式一致。
3. 脚本实拉登录页解析到动态盐 `12ttwoFBUBXfwYBZ` 并成功加密。

## 复现
```bash
d:\python_work\venv\Scripts\python.exe cases/nju_login/repro.py <账号> <密码> [验证码]
```
`repro.py` 自动 GET 解析 `pwdEncryptSalt`/`execution`/`lt` 并加密密码、组装 POST 数据。
完整提交需补充 `captcha`（图形验证码，需人工识别）。
