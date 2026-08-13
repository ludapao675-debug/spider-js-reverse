# 案例：山东大学统一身份认证 (SDU CAS) 账号密码登录加密

> 类型：账号密码登录参数加密（三次 DES 自定义实现 / 设备预校验网关）
> 目标站点：`https://pass.sdu.edu.cn/cas/login`
> 复现脚本：`cases/sdu_cas_login/repro.py`（纯 Python 标准库，无第三方依赖）
> 重测记录：2026-07-15 从零重测，结论与旧分析一致并已用页面实时样本逐字节验证

## 1. 加密算法

表单提交字段（`#loginForm` POST 到 `/cas/login?service=...`）：

| 字段 | 说明 |
|------|------|
| `un` | 用户名（**明文**） |
| `pd` | 密码（**明文**） |
| `rsa` | `strEnc(u + p + lt, '1', '2', '3')` 密文（唯一加密字段） |
| `ul` | 用户名长度 |
| `pl` | 密码长度 |
| `lt` | 登录票据（动态，隐藏域 `#lt`） |
| `execution` | 表单执行令牌（如 `e1s1`） |
| `_eventId` | 固定 `submit` |

> 注意：**用户名和密码本身以明文提交**，只有 `rsa` 是 `(用户名+密码+票据)` 的密文。
> 所谓 "rsa" 字段名是误导，其算法与 RSA 无关。

### strEnc 算法（des.js, Guapo 2006）

源码位置：`https://pass.sdu.edu.cn/cas/comm/js/des.js`
调用位置：`https://pass.sdu.edu.cn/cas/comm/sdu/js/login.js?v=3.0` 的 `login()`：

```js
$("#ul").val(u.length);
$("#pl").val(p.length);
$("#rsa").val(strEnc(u + p + lt, '1', '2', '3'));
```

算法本质（自定义，非标准 3DES API）：

```
rsa = enc_k3( enc_k2( enc_k1( P ) ) )   三次 DES 正向串联（三遍均正向，非 EDE）
模式: 按 4 字符(64 bit)分组，各组独立加密（ECB 风格，无 IV/链接）
密钥: 每个 key 字符串按 4 字符切片 → strToBt 成 64-bit DES 密钥。
       单字符 '1'/'2'/'3' 各生成 1 个 64-bit 密钥（高位 48bit=0，低 16bit=ord(字符)）
分组填充: 末组不足 4 字符，以 0 字符补齐到 4 字符再 strToBt
输出: 每组 64-bit 密文 → bt64ToHex → 大写 hex 拼接
```

DES 核心（initPermute / expandPermute / sBoxPermute / pPermute / finallyPermute /
generateKeys）是标准 DES 的逐位移植，**置换表与标准 DES 一致**，因此可用标准库复现
（不必拉页面 JS 执行）。本案例 `cases/sdu_cas_login/repro.py` 已把 `des.js` 逐函数移植为 Python。

**验证向量（与页面原生 strEnc 实时输出一致）**：
- `strEnc("test", '1','2','3')` = `D8D35E5019288C41`
- `strEnc("testuser2026"+"TestPass@2026"+"LT-15032-...-cas")` = 272 位 hex，与浏览器实测一致
- `strDec(rsa)` 可还原原文（round-trip 通过）

## 2. 登录流程（双阶段）

1. 点击 `#index_login_btn` → `login()` 先 `$.post("/cas/device", ...)` 做设备指纹预校验
   （Fingerprint2 算 `murmur/murmur_s/murmur_md5`，以及 `u`/`p` 也各自 `strEnc` 后上报）。
2. 服务端返回 `info == 'binded' | 'pass'` 才 `$("#loginForm")[0].submit()` 提交到 `/cas/login`。

**实测结论**：`/cas/device` 当前返回 **HTTP 500（"请求出错" 服务端异常）**，是纯前端 UX 网关。
其响应不进入成功分支，故表单未被自动提交。但 `POST /cas/login` 的受理**不依赖**设备预校验结果——
只要有合法的 `lt` + 正确的 `rsa`，即可直接构造表单提交。

## 3. 本地复现

```bash
cd cases/sdu_cas_login
python repro.py
# 输出: strEnc('test') 与登录 rsa 均 [OK]，round-trip ok=True，=== ALL MATCH ===
```

生成提交用 `rsa` 与完整表单：

```python
from repro import str_enc, build_login_form

username = "testuser2026"
password = "TestPass@2026"
lt = "LT-15032-LXgE3DgkJjVpMvPVBrenqLCaPTEK3B-cas"   # 需从页面隐藏域实时获取

rsa = str_enc(username + password + lt, "1", "2", "3")
form = build_login_form(username, password, lt, execution="e1s1")
# form = {un, pd, rsa, ul, pl, lt, execution, _eventId}
```

提交示例（需带会话 Cookie / 有效 `lt`）：

```python
import requests
resp = requests.post(
    "https://pass.sdu.edu.cn/cas/login?service=https%3A%2F%2Fservice.sdu.edu.cn%2Ftp_up%2Fview%3Fm%3Dup",
    data=form,
    cookies={"JSESSIONID": "<会话>", "Language": "zh_CN"},
    allow_redirects=False,
)
```

## 4. 取证清单（task_20260715_023607_eaf18bb8）

- target_request：`POST /cas/login` 表单字段（un/pd 明文，rsa 密文）
- cipher_or_sign：`#rsa = strEnc(u+p+lt,'1','2','3')`，三次 DES 串联
- source_code：`login.js?v=3.0` 的 `login()` + `des.js` 的 `strEnc`
- runtime_scope：页面 `page_run_js` 实时样本（lt / rsa / strEnc('test') / 解密还原）
- reproduction_code：`cases/sdu_cas_login/repro.py`（des.js 逐行移植）
- validation：Python 输出与浏览器原生 `strEnc` 逐字节一致，ALL MATCH
