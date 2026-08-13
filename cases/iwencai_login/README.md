# iwencai_login 登录密码加密参数逆向

> 站点：https://upass.iwencai.com/login?isIframe=1&source=iwc_aime_web
> 工具：crypto-hunter-lite（ch_detect_login_encryption 自动识别 + ch_verify_page_function 验证）

## 结论

- 加密算法：**RSA / PKCS#1 v1.5（JSEncrypt）**
- 密钥来源：https://upass.iwencai.com/pubkey/default.js

## 证据

- 同花顺 SSO 登录密码采用 RSA-1024 模数与指数 Hex 编码加密，密文长度 256 字符 Hex 字符串
- 模数 (Modulus): D90F4DD5BF444916913F7B434F192587...
- 指数 (Exponent): 10001 (65537)

## 表单字段

| name | id | type | hidden | value 示例 |
|------|----|------|:------:|-----------|

## 补环境 (sdenv) 离线复现

- **sdenv 脚本路径**：[iwencai_sdenv.js](file:///f:/AICode/%E9%80%86%E5%90%91%E5%B7%A5%E5%85%B7/crypto-hunter-lite/cases/iwencai_login/iwencai_sdenv.js)
- **依赖对象**：`window`, `document.cookie`, `location`, `navigator`, `screen`
- **运行命令**：`node cases/iwencai_login/iwencai_sdenv.js`
- **生成产物**：实时生成同花顺 `v` (hexin-v) 安全防阻参数与 Cookie 继承

## 相关脚本

- https://upass.iwencai.com/pubkey/default.js?t=201809011552
- https://upass.iwencai.com/asset/common/static/encrypt.min.js?t=20210604
- https://s.thsi.cn/js/chameleon/chameleon.1.7.min.1785295.js

