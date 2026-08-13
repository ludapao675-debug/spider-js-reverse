# csu_login 登录密码加密参数逆向

> 站点：https://ca.csu.edu.cn/authserver/login?service=https%3A%2F%2Fmy.csu.edu.cn%2F
> 工具：crypto-hunter-lite（ch_detect_login_encryption 自动识别 + ch_verify_page_function 验证）

## 结论

- 加密算法：**AES-128-CBC（CryptoJS）**
- 密钥来源：动态盐 #pwdEncryptSalt

## 证据

- 发现 #pwdEncryptSalt 动态隐藏字段作为 AES 密钥
- 密码明文 = randomString(64) + 真实密码
- iv = randomString(16)

## 表单字段

| name | id | type | hidden | value 示例 |
|------|----|------|:------:|-----------|

## 相关脚本

- https://ca.csu.edu.cn/authserver/gorgeousCsu20260630/static/common/encrypt.js
