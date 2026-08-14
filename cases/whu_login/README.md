# 武汉大学 WHU 统一身份认证登录 — 密码加密参数逆向

> 站点：`cas.whu.edu.cn/authserver/login`
> 目标：`adbjh.whu.edu.cn` 登录
> 日期：2026-08-05
> 工具：crypto-hunter-lite（Chromium @9222 + final_capture.user.js 注入 + MCP 工具链）

## 结论：密码用 **AES-128-CBC** 加密（金智 Wisedu CAS 通用方案）

### 加密公式
```
密文 = base64( AES-128-CBC( 明文 = random64(64) + password,
                             key  = utf8(pwdEncryptSalt),
                             iv   = utf8(random64(16)) ) )
```
- 填充：PKCS7；base64 输出 **不带** `Salted__` 前缀（key 以 WordArray 直传，不走 OpenSSL KDF）。
- 随机字符集：`ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678`
  （排除 I L O U 0 1 9）
- `pwdEncryptSalt`：**动态盐**，每次刷新登录页都会变（实测 `t9lAoFs0w6MwaPpc`），复现时必须实时解析。
- key = `utf8(pwdEncryptSalt)`（16 字节 → AES-128）；iv = `utf8(random64(16))`（16 字节）。

### 调用链（encrypt.js + login.js）
```js
// encrypt.js
getAesString(n, f, c):
  f = f.trim(); f = Utf8.parse(f); c = Utf8.parse(c);
  return CryptoJS.AES.encrypt(n, f, {iv:c, mode:CBC, padding:Pkcs7}).toString();
encryptAES(n, f)   => f ? getAesString(randomString(64)+n, f, randomString(16)) : n;
encryptPassword(n, f) => try { return encryptAES(n, f) } catch(c){ return n }

// login.js（推断，与 NJU 同款）
$("#saltPassword").val(encryptPassword($("#password").val(), $("#pwdEncryptSalt").val()));
```
加密结果写入隐藏字段 `#saltPassword`（name=`password`）；可见密码框 `#password` 的值被忽略。

## 识别依据（ch_detect_login_encryption）
- `algorithm=aes_cbc`，置信度 0.88
- 全局检测到 `CryptoJS`、`getAesString`、`encryptPassword`、`encryptAES`、`WebCryptoRSA`（RSA 未实际用于密码）
- 动态盐隐藏字段 `#pwdEncryptSalt`（16 字节）
- 密文镜像隐藏字段 `#saltPassword`（name=password）
- 关键脚本：`whuThemeNew1/static/common/encrypt.js?v=20260724.140937`

## 提交表单字段
| 字段 | 说明 |
|------|------|
| `username` | 账号 |
| `password` | **AES 密文**（来自 #saltPassword） |
| `captcha` | 图形验证码（**必填**，需人工识别） |
| `_eventId` | `submit` |
| `cllt` | `userNameLogin` |
| `dllt` | `generalLogin` |
| `lt` | 可能为空 |
| `execution` | 如 `e3s1` |
| `pwdEncryptSalt` | 动态盐（加密 key） |

## 验证
1. **确定性逐字节比对（闭环通过）**：固定 plain/salt/iv 调浏览器 `getAesString` 与 Python `pycryptodome` 复算：
   - 输入：`plain="TESTPLAINTEXT_123456"`, `salt="t9lAoFs0w6MwaPpc"`, `iv="0123456789abcdef"`
   - 输出一致：`+CoU0m2TgRNcvl6u6BP1B/6LqQ9/P6i35OCnk0jFCLg=`（**MATCH: True**）
2. **随机路径**：页面 `encryptPassword("MyTestPass123!","t9lAoFs0w6MwaPpc")` 返回 108 字符 base64，与 Python 生成格式一致。
3. **脚本实拉登录页**：`repro.py` 自动 GET 解析动态盐并成功加密。

### 实战登录闭环验证（2026-08-05 浏览器实测，随机账号）
1. **真实提交**：`ch_page_run_js` 用 jQuery 写入随机账号 `test_rand_2026` / 密码 `RandPass_!2026x`，调 `window.startLogin($('#login_submit'))` 触发 login.js 原生提交流程（`checkForm()` → `#saltPassword` 加密填充 → 表单 POST）。
2. **捕获真实登录 POST**（监听器 `lst_bb4131a4a6834474`）：
   - `POST https://cas.whu.edu.cn/authserver/login?service=...` → **status 401**（随机账号不存在，预期）
   - body：`username=test_rand_2026&password=VLNhza37P1q5xqOBxHADK6Z9hRkaeAopqJvig1qXB+GH/APkoEnL6eY40afkc8Z9A1A2AHPXABjlfCirzsXETnvvsrKxioMjeSJKqFuLhBw=&captcha=&_eventId=submit&cllt=userNameLogin&dllt=generalLogin&lt=&execution=e3s1`
   - 密文长度 108 字符 base64，与 Python 复现完全一致
3. **解密密文还原密码（MATCH=True）**：用已知 salt `t9lAoFs0w6MwaPpc` 对密文做 CBC 解密（跳过依赖随机 IV 的首块），还原出：
   - 随机前缀段（字符集一致）：`H8MiX7JNK4D2PYxApGS3famjpsatpnrfzkhtadhQdt4pwk4A...`
   - **密码：`RandPass_!2026x`**（与输入完全一致）✓
   - PKCS7 填充：`\x01`（79 明文补 1 到 80）✓
4. **随机账号 401 验证**：完整提交无需验证码（`checkNeedCaptcha.htl` 返回 `{"isNeed":false}`），返回 401 = 账号/密码校验失败，说明加密参数与请求链完全正常。

## 滑块拼图验证码逆向（2026-08-05 二次登录触发）

> 随机账号登录失败后，页面弹出**滑块拼图验证码** `#captcha-id`（slidercaptcha 组件，非 iframe）。

### 验证码触发与初始化
1. 登录失败 → 弹出滑块弹窗；`openSliderCaptcha()` 调 **`GET /common/openSliderCaptcha.htl`** 返回 `{bigImage, smallImage}`（base64）。
2. **safeSecure** = smallImage(base64) 解码后**最后 16 字节**，动态变化（实测 `vKMZW9GSV8JlDxwb`、`rHgai7sV3TMcES7S`），写入全局 `safeSecure.value`。
3. `#sliderDiv.sliderCaptcha({width:280,height:155,sliderL:42,sliderR:9,offset:5,...})` 初始化，`isRemoveUrl=1`（走**后端验证**，非纯前端）。

### 拖动轨迹采集（longbow.slidercaptcha.js bindEvents）
- mousedown：`tracks=[{a:0,b:0,c:0}]`，记录按下 clientX/Y。
- mousemove（间隔>20ms 且位移>2px）：push `{a:x位移, b:y位移, c:与上次间隔ms}`。
- mouseup：push `{a:最终x, b:最终y, c:间隔}`；`canvasLength=$("#sliderDiv").width()`（实际 **278**），`moveLength=clientX差`。

### sign 加密参数（核心）
```
sign = encryptPassword( JSON.stringify({canvasLength:278, moveLength:X, tracks:[{a,b,c}...]}), safeSecure )
```
- `encryptPassword` 即**登录密码同一函数**（encrypt.js）：AES-128-CBC(key=utf8(safeSecure), iv=random16, 明文=random64(64)+JSON) → base64。
- 用 XHR 断点（`ch_breakpoint_set_xhr`）在发包处确认：仅 `sign` 一个参数，POST `verifySliderCaptcha.htl`。

### 验证接口与结果
- **`POST /common/verifySliderCaptcha.htl`**，参数仅 `sign`（base64，长度随 tracks 变化 500~810）。
- 成功标志 **`errorCode==1`**；失败 `errorCode==0`。
- 后端解密 sign 得到 `{canvasLength, moveLength, tracks}`，**校验 moveLength 等于其生成的拼图缺口位置**（非前端 inst.x）。

### 验证结论（Python == 页面 MATCH）
- 确定性：固定 salt/iv 调页面 `encryptPassword` 与 Python `pycryptodome` 复算，**216 字符一致**。
- 完整 sign 生成复现于 `repro_slider.py`（`build_human_tracks` 拟人轨迹 + `gen_sign`）。
- **注意**：前端 `inst.x`（随机缺口 89/167）是误导值，后端期望的 moveLength 需 **OpenCV 分析背景图真实缺口**。CDP 合成拖动（offset 94/89）与构造轨迹均因 moveLength≠真实缺口 返回 errorCode=0。滑块每次失败会刷新（新缺口+新 safeSecure）。

### 相关文件
- `repro_slider.py`：sign 生成复现 + safeSecure 提取 + 拟人轨迹构造。

## 复现
```bash
python cases/whu_login/repro.py <账号> <密码> [验证码]
```
`repro.py` 自动 GET 解析 `pwdEncryptSalt`/`execution`/`lt` 并加密密码、组装 POST 数据。
完整提交需补充 `captcha`（图形验证码，需人工识别）。

## 关联
- 与 `cases/nju_login` 同源（金智 Wisedu CAS），算法、字符集、字段完全一致。
