# 暨南大学 JNU 统一身份认证 (icas.jnu.edu.cn) — 密码加密参数复现

## 结论

| 项目 | 内容 |
|------|------|
| 站点 | `https://icas.jnu.edu.cn/cas/login` |
| 登录框架 | 东软(Neusoft) CAS（自定义 `des.js` 3DES 风格算法） |
| 加密算法 | `strEnc(明文, '1', '2', '3')` —— 自定义 3DES，4 字节分组，三把定长密钥顺序作用，**确定性**（无随机填充） |
| 提交方式 | `POST /cas/login` 表单 `submit()` |
| 难度 | 低（标准 Neusoft CAS 模板，密钥硬编码为 `1/2/3`） |

## 加密构造

登录时 `login10.js`（L210-217）的提交逻辑：

```js
$("#ul").val(u.length);            // 用户名长度
$("#pl").val(p.length);            // 密码长度
$("#rsa").val(strEnc(u + p + lt, '1', '2', '3'));  // 密文
$("#loginForm")[0].submit();
```

- **明文** = `username + password + lt`（`lt` 为页面隐藏字段 `LT-xxxx-...`，每次登录变化）
- **密钥** = 三个定长字符串 `'1'`、`'2'`、`'3'`（对应 `getKeyBytes` 后得到单字节 `0x31/0x32/0x33`）
- **输出** = 十六进制字符串，无填充；每组 4 字节明文产生 16 个十六进制字符（即 8 字节 DES 密文块），逐组拼接

隐藏字段（`#rsa` `#ul` `#pl` `#lt` `#execution` `#_eventId` `#not_exit_number` `#service_id`）随页面返回，提交时一并 POST。

## 复现验证

用页面真实 `des.js`（已下载到本目录 `des.js`）直接加载 `strEnc`，与浏览器内执行结果**逐字节一致**：

```
明文 = user123 + Pass5678 + LT-250745-abc
rsa  = EB6D16D13160C8DCB5B5F98C3691B9262E9317767E7C076B769938721F4E35FD5341FF584B5500F9C935586EF049C6827DBBAFFA02992D43
闭环 = strDec(rsa,'1','2','3') == 明文  ->  true
```

运行：

```bash
node cases/jnu_login/repro.js <username> <password> <lt>
# 例：node cases/jnu_login/repro.js user123 Pass5678 LT-250745-abc
```

输出 `rsa`（即 POST 时填到 `#rsa` 的值）、`ul`、`pl`。

## 取证要点

- 表单含 `rsa/ul/pl/lt/execution/_eventId` 隐藏字段，外部脚本 `cas/comm/js/des.js?v=202606172` 提供 `strEnc/strDec`。
- `des.js` 为通用 3DES 风格实现（`getKeyBytes` + 逐字节 `enc`，分组 64 bit），并非标准 3DES 库；密钥 `'1'/'2'/'3'` 在 `login10.js` 中硬编码。
- 与 NJU（AES-CBC）、PKU（RSA-2048）、CHSI（明文）同属校园 CAS 体系，但 JNU 采用东软分支的自定义算法。

## 备注

- `lt` 每次登录变化，复现真实提交时需先从 `GET /cas/login` 页面解析最新 `lt`（及 `execution`）。
- 该算法确定性，同一 `(username,password,lt)` 永远得到相同 `rsa`，便于离线批量复现。

## 2026-07-22 真实页面验证码取证（不提交）

- 用户提供的 JNU CAS 页面真实加载，标题为“统一身份认证平台”。
- 页面加载了 `cas/comm/js/des.js`、`login10.js` 和 `jquery.captcha.js`；隐藏字段包含 `rsa`、`ul`、`pl`、`lt`、`execution` 等，未读取或保存字段值。
- 页面同时出现网易易盾验证码背景/滑块图像和安全验证 iframe；本次只记录候选类型与脚本指纹，没有 hover、拖动、填写密码或提交登录。
- 统一管线结论：`recognized=true`、`action_executed=false`、`verified=false`、`verdict=pending`。密码加密证据和验证码证据分开归档，不能把其中任一项当作登录成功。
