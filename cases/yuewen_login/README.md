# yuewen_login 登录密码加密参数逆向

> 站点：https://passport.yuewen.com/yuewen.html
> 工具：crypto-hunter-lite（服务端抓源码 + 官方 JSBN 离线长度校验）

## 结论

- 加密算法：**RSA-1024 / PKCS#1 v1.5（JSBN `RSAKey.encrypt`，输出 hex，不是 JSEncrypt/base64）**
- 密钥来源：页面内联 `LoginV1.init({modulus, exponent})` 注入静态 1024-bit RSA 公钥；exponent 固定 `10001`。库文件 https://ywloginstatic.yuewen.com/rsa/rsa_encrypt.js。

## 证据

- 页面 LoginV1.init 注入 1024-bit modulus + exponent 10001
- login_yw.js rsa_encryption: RSAKey.setPublic + encrypt，输出 hex，长度>50 才当密文
- 库 https://ywloginstatic.yuewen.com/rsa/rsa_encrypt.js（JSBN pkcs1pad2 + RSAEncrypt）
- 离线 Node vm 跑官方 rsa_encrypt.js：同明文两次加密 hex 长度均 256 且不相等
- Python PKCS1_v1_5 同公钥：输出 hex 长度 256、每次不同、模数 1024-bit
- 提交 JSONP https://ptlogin.yuewen.com/login/login 或 /login/checkcode，password 字段为 RSA hex

## 表单字段

| name | id | type | hidden | value 示例 |
|------|----|------|:------:|-----------|
|  | username |  |  |  |
|  | password |  |  |  |
|  | txtCode |  |  |  |
|  | autologin |  |  |  |
| ywtoken |  |  |  |  |
| sessionkey |  |  |  |  |

## 相关脚本

- JSBN RSA：https://ywloginstatic.yuewen.com/rsa/rsa_encrypt.js
- 登录客户端：https://ywloginstatic.yuewen.com/js4/login_yw.js（`rsa_encryption`）
- 公钥注入：https://passport.yuewen.com/yuewen.html（`LoginV1.init`）

## 备注

PKCS#1 v1.5 随机填充，不能逐字节比对两次密文。验证用：hex 长度 256、两次不同、官方 JSBN 与 Python PKCS1_v1_5 格式一致。登录请求还需 ywtoken/可能的图形验证码，本案不做真实账号登录。当前调试浏览器约 124 个 CDP target，页面侧 ch_detect_login_encryption 超时，结论来自服务端抓源码 + 离线 JSBN。sdenv verify-code 加 super_env 会塞住 FastAPI 事件循环，改用隔离 Node vm。
