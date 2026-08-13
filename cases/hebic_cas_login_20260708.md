# 案例：cas.hebic.cn 统一身份认证登录密码加密

- 日期：2026-07-08
- 类型：签名/加密型（密码 RSA 加密）
- 平台：河北省教育网统一身份认证平台（Apereo CAS 定制版）
- 复现脚本：`assets/repro/hebic_cas_login/repro_hebic_login.py`

## 1. 目标与入口

- 登录页：`http://cas.hebic.cn/cas/login`
- 加密字段：`#password`（表单 fm1，name=password，id=ppassword）
- 明文账号：`#username`（明文提交）
- 验证码：`#authcode`（kaptcha 接口控制是否必填）

## 2. 加密算法（核心）

算法：教科书式 RSA（Stanford jsbn `RSAUtils`，无随机 padding），加密前**先反转密码字符串**。

- 库文件：`/cas/js/login/security.js`（`RSAUtils` / `RSAKeyPair` / `encryptedString`）
- 公钥下发：`jQuery.getJSON("v2/getPubKey")` → `{modulus, exponent}`
- 调用点：`/cas/js/login/login.js` 的 `checkForm()`：

```js
var password = $("#ppassword").val();
var key = new RSAUtils.getKeyPair(public_exponent, "", Modulus);
var reversedPwd = password.split("").reverse().join("");   // 先反转
var encrypedPwd = RSAUtils.encryptedString(key, reversedPwd);
$("#password").val(encrypedPwd);
$("#fm1").submit();
```

参数：
- `e = 0x10001`（65537）
- modulus：128 hex = 64 字节 = **512-bit RSA**（注意：比常见 1024/2048 位短，密钥强度弱）
- chunkSize = 2*(biHighIndex(modulus)+1) = 62 字节；单块密文 124 hex
- 整数构造：反转后的明文字节按**小端**组装成整数 m，`c = m^e mod n`
- 输出：密文十六进制字符串（小写，无 0x 前缀）

## 3. 关键差异点（相对 d.cn 案例）

| 项 | cas.hebic.cn | 当乐网 d.cn |
|---|---|---|
| 算法 | 教科书式 RSA（无 padding） | RSA PKCS#1 v1.5 |
| 密码预处理 | **先反转字符串** | 直接用明文 |
| 公钥来源 | 动态接口 `v2/getPubKey` **每次轮换** | 内联固定常量 |
| 密钥长度 | 512-bit | 1024-bit |
| exponent | 0x10001 | 0x10001 |

## 4. 运行时证据

- 浏览器内 `RSAUtils.encryptedString(key, reversedPwd)` 对 `TestPass@2026` 输出：
  `70fc62c3709228a01ef194afd4e2fa5a2563873bc161f8dad86f0eb3547fd24651a19b9a4849e8cb70fd71684903df4113286a893a35c1228444b57fbd8d74c7`
- 对 `HelloWorld#99` 输出：
  `50b509d17022736185675b768e259ccbe9b10737fdc350d34b9ba90762088af98a1c46b3f8d1ddd38e7f438cc2aaaa61a8cc47f8ded1b3481101bcf5ff483a78`
- 公钥样本（某次会话）：
  `modulus=e20e302661bb56b2cbf282325ef227c460b5defc9c5f38302aa706ef9b0550979c2b3f902d073b2baf879813bef22ebb9e50e1a798d423f7bc6f33479d6c42d3`

## 5. 完整请求结构（POST /cas/login）

表单 fm1 隐藏字段：
- `execution`：Spring WebFlow token（超长，形如 `601a708d-..._ck8wQUJYTnlBRnB2...`）
- `_eventId=submit`
提交字段：
- `username`：明文账号
- `password`：RSA 密文
- `authcode`：验证码（kaptcha 开启时必填）

## 6. 复现脚本与验证

`assets/repro/hebic_cas_login/repro_hebic_login.py`：
- `encrypt_password(plaintext, modulus_hex, exponent_hex)`：反转→小端整数→`pow(m,e,n)`→hex
- `self_test()`：与浏览器样本逐字节一致（OK）
- `fetch_pubkey()`：**动态拉取**当前公钥（因密钥轮换，必须用实时公钥）
- `live_login()`：组装并 POST（需同会话的 `execution` 与 `authcode`）

验证结果：
- `TestPass@2026`：Python `70fc62c3...d8d74c7` == 浏览器样本 OK
- `HelloWorld#99`：Python `50b509d1...f483a78` == 浏览器样本 OK

## 7. 踩坑点

1. **密码反转**：漏掉 `split("").reverse().join("")` 会得到错误密文（等价于不同明文）。
2. **小端字节序**：`encryptedString` 将字节按 `digit[j]=a[k]+a[k+1]<<8` 组装，即小端；必须用 `int.from_bytes(bytes,"little")`。
3. **密钥动态轮换**：`v2/getPubKey` 每次返回不同 modulus，离线写死公钥会失效；复现必须实时获取。
4. **512-bit 短密钥**：chunkSize=62，单块密文 124 hex；长密码会分多块（每块独立 powMod，空格分隔）。
5. **page_run_js 表达式模式**：代码含 `function`/`{}`/`;` 会被判为语句模式导致 `result:null`；取证提取须用箭头函数无块体的纯表达式。

## 8. 可复用规则

- CAS 登录页若引用 `security.js`/`RSAUtils`，优先怀疑教科书式 RSA + 密码反转。
- 公钥若来自 `getPubKey` 接口，默认可轮换，复现脚本应动态拉取。
- 用页面同源 `RSAUtils.encryptedString` 直接产出对照样本，是验证 Python 复现最稳的方式。

## 9. 不在复现范围

- kaptcha 验证码识别（行为挑战），与密码加密无关。
- 短信验证码登录（fm2，`#phone`/`#mobileCode`，同样走 RSAUtils 加密 code）。

## 10. 工具链修复记录（同会话）

- `server/report_generator.py`：新增 `_extract_request_url/method/status/post_data`，兼容多种字段名与嵌套 `request` 结构，修复报告中 URL/method 空白显示。
- `server/mcp_service.py`：新增 `_as_list()`，修复 `ch_reverse_generate_report` 的 `unhashable type: 'slice'`。
