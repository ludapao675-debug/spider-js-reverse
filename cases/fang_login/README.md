# fang_login 登录密码加密参数逆向

> 站点：https://passport.fang.com/?backurl=http://mp.fang.com/index.do
> 工具：crypto-hunter-lite（ch_detect_login_encryption 自动识别 + ch_verify_page_function 验证）

## 结论

- 加密算法：**rsa_1024**
- 密钥来源：全局变量 key_to_encode (RSAKeyPair 实例)

## 证据

- 密码字段通过 encryptedString(key_to_encode, password) 进行 RSA-1024 加密
- 公钥模数 N_hex: 978c0a92d2173439707498f0944aa476b1b62595877dd6fa87f6e2ac6dcb3d0bf0b82857439c99b5091192bc134889dff60c562ec54efba4ff2f9d55adbccea4a2fba80cb398ed501280a007c83af30c3d1a142d6133c63012b90ab26ac60c898fb66edc3192c3ec4ff66925a64003b72496099f4f09a9fb72a2cf9e4d770c41
- 公钥指数 E_hex: 00010001
- 接口位置: POST /loginwithpwdStrong.api

## 表单字段

| name | id | type | hidden | value 示例 |
|------|----|------|:------:|-----------|

## 相关脚本

- https://static.soufunimg.com/passport/commonjs/RSA.min.js
- https://static.soufunimg.com/passport/pcjs/loginbypassword20231031.js?v=006
