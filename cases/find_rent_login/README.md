# find_rent_login 登录密码加密参数逆向

> 站点：https://www.find-rent.com/sign_in
> 工具：crypto-hunter-lite（ch_detect_login_encryption 自动识别 + ch_verify_page_function 验证）

## 结论

- 加密算法：**明文（无客户端加密，仅 HTTPS）**
- 密钥来源：无客户端加密，密码明文提交（仅 HTTPS 保护）

## 证据

- 提交的表单 user[password] 字段未加密，直接抓包显示明文
- 未加载任何密码学相关全局库，也没有相关的加密脚本钩子

## 表单字段

| name | id | type | hidden | value 示例 |
|------|----|------|:------:|-----------|
