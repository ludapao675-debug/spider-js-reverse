# 北京大学 PKU 统一身份认证 (iaaa) — 密码加密参数逆向

> 站点：`iaaa.pku.edu.cn/iaaa/oauth.jsp`
> 目标：`portal.pku.edu.cn` 登录
> 日期：2026-07-15

## 结论：密码用 **RSA-2048（PKCS#1 v1.5）** 加密

### 加密公式
```
密文 = base64( RSA_encrypt( 密码明文, 公钥 ) )
```
- 算法：RSA-2048，填充 **PKCS#1 v1.5**（JSEncrypt 默认），base64 输出
- 公钥：**固定静态公钥**（与 `/iaaa/getPublicKey.do` 返回一致，见 `repro.py` 中 `PKU_RSA_PUBLIC_KEY`）
- 密文长度：256 字节 → 344 字符 base64（与浏览器 `JSEncrypt.encrypt()` 输出一致）

### 调用链（OAuthLogin.js）
```js
// 页面加载
$.ajax('/iaaa/getPublicKey.do', {success: function(d){ crypt = new JSEncrypt(); crypt.setPublicKey(d.key); }});
// 提交（oauth 路径 L222-230）
var encryptedPWD = $("#password").val();
if (crypt != null) encryptedPWD = crypt.encrypt($("#password").val());
$.ajax('/iaaa/oauthlogin.do', { type:'POST',
  data:{ appid, userName, password:encryptedPWD, randCode, smsCode, otpCode, remTrustChk, redirUrl }});
```

## 提交参数（/iaaa/oauthlogin.do）
| 字段 | 说明 |
|------|------|
| `appid` | `portal2017`（隐藏 #appid） |
| `userName` | 账号 |
| `password` | **RSA 密文** |
| `randCode` | 图形验证码（#valid_code）；`/iaaa/isShowCode.do` 返回 success 时必填 |
| `smsCode` | 短信码（可选） |
| `otpCode` | OTP（可选） |
| `remTrustChk` | 是否信任设备 |
| `redirUrl` | 页面 redirectURL |

验证码图片：`/iaaa/servlet/DrawServlet?Rand=<random>`

## 验证
- RSA 密文含随机填充，每次不同，无法直接比对两个密文。
- 用自生成 RSA 密钥做加解密闭环：`decrypt(encrypt("PKUTEST123"))=="PKUTEST123"`，
  输出 256 字节 / 344 字符 base64，与浏览器 `JSEncrypt` 输出长度一致 → 方案确认。
- 真实公钥已确认可被 `RSA.import_key` 正常解析（有效 2048-bit 公钥）。

## 复现
```bash
python cases/pku_login/repro.py <账号> <密码> [验证码]
```
`repro.py` 用内置静态公钥 RSA 加密密码并组装 POST 数据；完整提交需补充 `randCode`（图形验证码，需人工识别）。
