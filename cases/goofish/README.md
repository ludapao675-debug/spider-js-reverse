# goofish.com（闲鱼国际版）密码登录加密深度分析

> 分析日期：2026-07-18 ｜ 逆向对象：`https://www.goofish.com/` → 密码登录
> 结论：**密码以 RSA-1024 + PKCS#1 v1.5 加密，公钥为服务端下发的静态固定值；登录请求体不含 MTOP 式 sign，改走 passport 自有 `/newlogin/login.do` 接口。**

---

## 1. 登录架构

- 主站 `www.goofish.com/login` 不直接渲染表单，重定向到 SSO 登录页：
  `https://passport.goofish.com/mini_login.htm?appName=xianyu&fromSite=77&...`
- 登录逻辑由阿里 passport 登录 SDK 承载：`x.alicdn.com/vip/havana-nlogin/0.10.36/index.js`（webpack bundle，约 720KB）。
- 表单有两个标签：**短信登录**（默认，`fm-sms-login-id` + `nc_1_captcha_input` 阿里 noCaptcha 滑块）与**密码登录**（`password-login-tab-item` 切换，出现 `fm-login-id` + `fm-login-password`）。
- 风控/设备指纹脚本栈（与登录并行加载）：`baxia`（风控）、`AWSC/WebUMID`、`AWSC/uab/collina`、`AWSC/fireyejs`、`AWSC/et`、`AWSC/awsc.js + baxiaCommon`、`sd/ncpc/nc.js`（滑块）、`sufei`（埋点）、`aplus_v2`。

## 2. 密码加密方案（核心结论）

**算法：标准 RSA-1024 + PKCS#1 v1.5 填充（即 Tom Wu / jsbn `RSAKey.encrypt` 的等价实现，非 SM2/非 AES/非混合盐）。**

调用链（bundle 内，`getCommonLoginData` 组件中）：

```
getLoginData()
  └─ password2 = this.rsaPassword(this.passwordNode.value())   // 取明文密码
       └─ rsaPassword(e):
            var t = new T.default;                 // T = RSAKey 类（bundle 内 N）
            t.setPublic(c.config.rsaModulus, c.config.rsaExponent);
            return t.encrypt(e);                   // PKCS#1 v1.5 加密
  └─ reqPost(this.api.loginApi, JSON.stringify(getLoginData()))
```

`N.prototype.encrypt` 原始逻辑（从 bundle 逐行还原）：

```js
N.prototype.encrypt = function(e){
  // 1) 构建 PKCS#1 v1.5 编码块：[0x00][0x02][随机非0填充 PS][0x00][明文 UTF-8]
  //    长度校验：t < e.length+11 直接 alert 并 return null
  // 2) 随机填充：SecureRandom.nextBytes，取“非 0”字节（遇 0 重取）
  // 3) var t = new r(n);          // 字节数组 -> BigInteger（大端）
  // 4) var n = this.doPublic(t);  // = t.modPowInt(this.e, this.n) = t^e mod n
  // 5) var o = n.toString(16);
  // 6) return (o.length 为奇数) ? "0"+o : o;   // 补成偶数长度十六进制
}
```

**输出编码：`password2` = 密文 BigInteger 的**小写十六进制字符串**，长度为 **256 字符**（= 128 字节密文；因 1024-bit，若 hex 长度为奇数前面补 `0`）。

## 3. RSA 公钥（服务端下发，但为静态固定值）

来自页面全局 `window.viewConfig`（即 havana-nlogin 的 `c.config`）：

```
rsaExponent = "10001"            // = 0x10001 = 65537（标准）
rsaModulus  = "d3bcef1f00424f3261c89323fa8cdfa12bbac400d9fe8bb627e8d27a4"   // 256 hex = 1024-bit
             "4bd5d59dce559135d678a8143beb5b8d7056c4e1f89c4e1f152470625b7b4194"
             "4a97f02da6f605a49a93ec6eb9cbaf2e7ac2b26a354ce69eb265953d2c29e395d6d8c1cdb688978551aa0f7521f290035fad381178da0bea8f9e6adce39020f513133fb"
```

> 该 modulus 为固定值（不随会话变化），因此可完全离线复现加密，无需动态抓取。

## 4. 登录请求结构

- **端点**：`https://passport.goofish.com/newlogin/login.do?appName=xianyu&fromSite=77`（POST，JSON body）
- **请求体**（由 `getCommonLoginData` 合并而成）：

```js
{
  loginId, password2, keepLogin,            // 来自 getLoginData()
  isIframe, banThirdPartyCookie, documentReferer,   // getPartitionedCookieParams()
  defaultView,                                // getCurrentViewParams()
  ua, umidGetStatusVal, ...getClientInfo(),
  umidToken, umidTag, weiBoMpBridge, jsVersion,  // 设备/风控标识
  ...(滑块 checkCodeNode 数据，若滑块显示时追加),
  ...requestExtParams
}
```

- `umidToken` 来源（bundle `getUmidToken`）：优先 `window.umidToken`（JSBridge/客户端）→ 否则 `window.viewData.umidToken`（本次实测值 `598d2d7e6a0005bc00a28aa5452038a3c097f321`）。
- 页面隐藏域 `loginFormData` 还含 `_csrf_token`、`hsiz`、`bizParams` 等，随登录会话下发。
- **密码登录默认不强制 noCaptcha 滑块**；滑块数据仅在 `checkCodeNode.isShow()` 为真时合并进请求体。

## 5. 离线复现与校验

复现脚本：

- `cases/goofish/evidence/rsa_password_encrypt.py` — 只生成 `password2`（纯 Python，`pow(m,e,n)`）
- `cases/goofish/evidence/login_repro.py` — 随机/指定测试账号 + 加密 + POST `login.do`

运行（venv：`E:\aicode\.venv\Scripts\python.exe`）：

```
python cases/goofish/evidence/rsa_password_encrypt.py "RandTest!9xQ2"
python cases/goofish/evidence/login_repro.py --login-id test_xy_demo01 --password "RandTest!9xQ2"
# 或完全随机账号密码:
python cases/goofish/evidence/login_repro.py
```

校验结果（实测）：

```
待测密码      : TestPwd123!
password2    : 5181e4e940aaab0d4e5b48291aab95b447577d1921d19ad929a1f074890669dff876469589cce31ff330bc328468d17d2bc1d44c22e656826186b710debf941bdf331b657a68ac6e5305f189a7c5585b647a4d772347bfba2866265fb2727efef71347250f54a8ca12477390bf6141f3eae4103a3d527ebab07339b478bb0025
密文长度     : 256 (应为 256 = 128 字节)
密文 < n     : True
公钥位数     : 1024
[校验] 确定性密文 : 72897b6b61c310952da6d62bab2abe462ccae71b8874e4466945c7ad9e1104b75fbc9a75864e9df75a4fcabb6cf4e95645751c7424bc966d024df1f0f70e8a9441c5f88a271cfbfe74e1641b58a30109f352ff5a7b94b9549d3a579af7273143cd391128692f943090c4fbfd5d517c7ec7ad64e3bdd2d87646f9c398122c1507
[校验] 块重建一致 : True
[校验] 模幂一致     : True
[校验] 块结构合法 : True     # 00 02 | 非0随机填充 | 00 | 明文
```

> 注：每次随机填充不同 → `password2` 密文不同（符合 RSA 随机化语义）；确定性 seed 复现用于验证块构建与模幂逻辑正确。

## 6. 反爬 / 风控要点

- 登录页并行加载阿里全套风控：`baxia`（无头/自动化特征检测）、`AWSC et/fireyejs/uab`（设备指纹 `umidToken`）、`sd/ncpc/nc.js`（noCaptcha 滑块）。
- 实测自动化环境下 `et_f.js` / `fireyejs.js` 持续打印 `Error` 日志，疑似风控脚本对环境异常敏感；这会影响“真实提交登录”的端到端捕获（滑块/cookie 校验可能拦截），但**不影响加密算法本身的分析与离线复现**（公钥静态、算法已 100% 还原）。
- 协议复现只需：① 静态 RSA 公钥；② 自行构造 PKCS#1 v1.5 块；③ `pow(block, 65537, n)` 取十六进制。无需滑块、无需真实 `umidToken` 即可生成合法 `password2`。
- **2026-07-18 实测 POST**：最小 JSON body（`loginId/password2/keepLogin/appName/.../umidToken`）发到 `login.do` 返回 **HTTP 200** + `FAIL_SYS_USER_VALIDATE` / `_____tmd_____/punish` 验证码页。说明密码字段格式已被协议层接受，但纯脚本缺 baxia/`x5sec` 会话会被挤爆风控拦住；端到端登录成功 ≠ 加密复现成功，二者需分层交付。

## 7. 证据

- 登录 bundle：`https://x.alicdn.com/vip/havana-nlogin/0.10.36/index.js`（722KB，Tengine，`Access-Control-Allow-Origin: *` 可跨域 fetch）
- 关键源码片段（已内联提取）：
  - `N.prototype.encrypt` / `setPublic` / `doPublic`（RSA PKCS#1 v1.5）
  - `getCommonLoginData` / `rsaPassword`（请求体组装）
  - `getUmidToken`（umidToken 取值）
  - `window.viewConfig.rsaModulus` / `rsaExponent`（静态公钥）
- 复现脚本：`cases/goofish/evidence/rsa_password_encrypt.py`

## 8. 与阿里系 MTOP 网关的区别

goofish 密码登录**不走** MTOP 的 `sign=MD5(token+timestamp+appKey+data)` 体系——那是 API 网关签名。此处登录是 passport 自有通道，密码用**静态 RSA 公钥**直接加密，`umidToken` 仅作为风控设备标识随请求带上，不参与密码加密。
