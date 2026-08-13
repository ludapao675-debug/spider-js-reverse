# 学信网 CHSI 登录协议逆向（account.chsi.com.cn / passport）

> 站点：国家大学生就业服务平台登录（`jy.chsi.com.cn` via `account.chsi.com.cn/passport`）
> 日期：2026-07-15

## 核心结论

**密码为【明文】提交（仅 HTTPS 保护），无客户端加密。**

- 真实登录 POST 的 `password` 字段是 URL 编码后的明文，**不是密文**。
- 表单 `onsubmit = null`，提交按钮无 `onclick`，按钮仅触发原生 `$("#fm1").submit()`。
- 页面 `window.doEncrypt` / `window.doDecrypt` **声明未赋值（undefined）**，不参与提交路径——属干扰项（可能用于站内其他模块）。

## 登录表单字段

| 字段 | 类型 | 值 | 说明 |
|------|------|----|------|
| `username` | text | 用户输入 | 邮箱/手机号/学号 |
| `password` | password | **用户输入（明文）** | 无加密 |
| `tp` | hidden | `crpusr` | 固定 |
| `lt` | hidden | `LT-<随机数>-cas` | CAS 票据，每次会话动态 |
| `execution` | hidden | `<uuid>_ZXlK...`(JWT) | 动态令牌，约 6.6KB |
| `_eventId` | hidden | `submit` | 固定 |

表单：`action=/passport/login?service=...`，`method=post`，`autocomplete=off`。

## 协议流程（标准 CAS）

1. **GET** `https://account.chsi.com.cn/passport/login?service=https%3A%2F%2Fjy.chsi.com.cn%2Fj_spring_cas_security_check`
   → 服务端在 HTML 渲染 `lt` / `execution` / `_eventId`；`JSESSIONID` 经 `Set-Cookie` 下发。
2. **POST** 同 URL，`Content-Type: application/x-www-form-urlencoded`：
   `username=&password=&tp=crpusr&lt=&execution=&_eventId=submit`

## 复现

```bash
python cases/chsi_login/repro.py <用户名> <密码>
```

`repro.py` 自动 GET 解析 `lt`/`execution` 再 POST，**负向验证通过**（错误凭证 → 服务端返回登录页+错误提示，HTTP 200，证明参数集正确）。

## 注意事项

- `lt` / `execution` 每次会话不同，必须实时从登录页解析。
- `captchaChange-1.0.1.js` 已加载，但基础表单**无验证码字段**；验证码通常在多次失败或风控触发后才出现（首次/正常登录无需）。
- 站点含风控 SDK（`CHSICC_CLIENTFLAGPASSPORT`、`acw_tc`、`aliyungf_tc`），自动化需维持正常 Cookie 与会话。

## 证据

- 登录 POST 的 `password` 为明文。
- 复现脚本负向验证：错误凭证 → HTTP 200 + 返回登录页错误提示。
