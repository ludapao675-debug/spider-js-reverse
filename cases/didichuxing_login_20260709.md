# didichuxing.com (滴滴出行 PC 登录 passport) 逆向

- 日期：2026-07-09
- 类型：RSA 密码加密 (JSEncrypt PKCS#1 v1.5, 1024-bit, 硬编码公钥) + **wsgsig 远程协作签名** (强混淆 VM + 远端签名服务)
- 站点：https://passport.didichuxing.com/common/pc-login/v3/index.html#/
- 难度评估：中等偏上（密码加密离线可解；完整登录被 wsgsig 远程签名阻断）

## 目标请求

### 1) 登录主请求（结构已知，实时抓取受阻）
```
POST https://passport.didichuxing.com/passport/login/v5/signInByPassword?wsgsig=<token>
Content-Type: application/x-www-form-urlencoded
Body: q=<URL编码的 JSON.stringify(r)>
```
- `r` 字段（来自源码 @27223 构造）：`phone`、`password`(RSA 密文)、`wsgenv`、`commonParams`、`password_encrypt_type` 等。
- 请求体形态：`{q: JSON.stringify(r)}`（源码 `o={q:JSON.stringify(r)}`）。
- `wsgsig` 查询参数由安全 SDK 注入（见下"请求签名"）。

### 2) 前置远程签名请求（已实抓确认）
```
POST https://security.xiaojukeji.com/sign/v1/wsgsigsession/signupdate
Content-Type: application/json; charset=UTF-8
sign: <由 4bf1 VM 计算的签名, 本体>   # 注意 sign 头本身也由同一混淆 VM 生成
Body: {"diuu":"d5cd8d4635b0b9b70a216550fd049593","noiss":"<base64>"}
Response 200: {"code":0,"msg":"success","data":{"noiss":"<base64>","cpTe":"11","epTe":1783592470852}}
```
- `diuu` 为设备/会话指纹（页面加载即固定）；`noiss` 为上一轮令牌（首次为初始值）。
- 响应回传新 `noiss` + 有效期 `cpTe`/`epTe`，本地 VM 据此合成后续请求的 `wsgsig`。

## 加密方案（密码 RSA）

- 公钥硬编码在 app 包（@9433 变量 `q`），JSEncrypt 默认小写 `public key` 头，本质为标准 SubjectPublicKeyInfo：

```
-----BEGIN public key-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3yWkNvyIYZMLLm4BJdt7DaD/3
kxPXkjuvPcsd8aVeoRb4RIFEUZhXCbppEuhGAAgJoaZtMaFEn9pSByQ8V7AaOIZT
qDlSus8R1yXOMsotYG7bTgLbaPMB1wGgrn95woNZzZP9tYZ84oBi8Nm5pofEhZ/W
ImT1HOLVP5EtGG6lbwIDAQAB
-----END public key-----
```

- 加密函数（源码 @14909）：
```js
function De(e){
  var t = new S.a;          // S = JSEncrypt 模块
  return t.setPublicKey(q), // q = 上述硬编码公钥
         t.encrypt(e)        // JSEncrypt 默认 = RSAES-PKCS1-v1_5
}
```
- 明文处理：密码原文**直接** `De(pwd)`，不经 `encodeURIComponent`（与 iyunzhi 的 jsbn 路线不同）。
- 触发时机（@27223）：`if(We.getParams().password_encrypt_type){ n=r.password; ...; r.password=De(n) }` —— 开启密码加密类型时，用 RSA 密文替换明文。

## 请求签名（wsgsig —— 阻断项）

- 签名器 `4bf1` 位于 `safe-vendor.38d4ce256f9191f4b5bb.js`，导出 `gt.a`(签名)、`gt.b`。
- 内部为强混淆 VM：`te()` 做 XOR 字符串解密 + `re`/`ne` 混淆 opcode 数组，静态还原成本极高。
- 协作流程：`onRequest` → `s` → `signupdate`（见上"前置远程签名请求"）。即**每次请求前本地 VM 先向远端 `security.xiaojukeji.com` 取令牌，再合成 `wsgsig`**。
- 结论：`wsgsig` 是"远程协作签名"，纯离线无法复现，除非：
  - (a) 反向还原强混淆 VM `4bf1` 的签名算法（高成本）；或
  - (b) 复刻对 `security.xiaojukeji.com/sign/v1/wsgsigsession/signupdate` 的调用（需 `sign` 头也由同一 VM 计算，仍绕不开 VM）。

## 离线复现（Python —— 已验证）

见 `assets/repro/didichuxing_com_cn.py`：

```python
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import base64

key = RSA.import_key(标准大写头 PEM)         # 与硬编码公钥密钥体相同
ct  = PKCS1_v1_5.new(key).encrypt(pwd.encode("utf-8"))
password_field = base64.b64encode(ct).decode("ascii")   # 172 字符
```

## 验证结果

- **密码 RSA 加密（已闭环验证）**：
  - 浏览器用 JSEncrypt 加密 `Test@123456` → 密文 → Python `PKCS1_v1_5` 解密 = `Test@123456` ✓
  - 滴滴公钥独立加密 `Test@123456` → 172 字符（128 字节）✓
  - Python 自生成 RSA 密钥 round-trip 通过 ✓
  → 密码加密字段完全离线可复现。
- **登录主请求 signInByPassword 实时抓取：受阻**：
  - 本会话后端重启后，CDP 监听器在旧监听器停止、新监听器重建后无法再接收 Network 事件（即便 `network_enabled=true`、唯一监听器、页面重新加载，仍 0 捕获）。早期会话（重启前）曾抓到前置 `signupdate` 请求。
  - 即便能抓到，登录端点 `passport.didichuxing.com` 在本测试代理环境（127.0.0.1:9000 Reqable）下点击登录后页面返回"网络异常，请刷新再试" + "参数错误"，疑似该 host 的登录 POST 被代理拦截/不可达（而 `security.xiaojukeji.com` 可达）。
  - 因此 signInByPassword 的完整 `wsgsig`/`sign` 头与含 RSA 密文的 body 未能实抓，但其结构已由源码静态确认（见上）。

## 证据

- 主 JS 包：`scratch/didi_app_58927d3c62a7e9ec6976_js`（登录端点、公钥、De、请求构造）。
- 安全包：`scratch/didi_safe-vendor_38d4ce256f9191f4b5bb_js`（模块 `4bf1` 强混淆 wsgsig 签名 VM）。
- 通用 vendor：`scratch/didi_vendor_2356865637cd3baa9938_js`（JSEncrypt / RSA / AES / MD5）。
- 实抓样本（早期会话）：`signupdate` 请求 + 响应（见"前置远程签名请求"）。
- 复现脚本：`assets/repro/didichuxing_com_cn.py`（RSA 加密 + 登录请求体骨架）。

## 超级补环境

- 是否启用：部分（wsgsig 需要）。
- 判定原因：密码 RSA 纯前端、无环境依赖；但 `wsgsig` 由 `safe-vendor` 在浏览器运行时结合 `diuu`/`noiss`/环境参数计算，含运行时指纹与远端协作，补环境难度等同于还原整个安全 SDK。
- 触发信号：`4bf1` 模块、`onRequest` 钩子、`signupdate` 远端调用。
- 补环境建议：若强还原 `4bf1` VM，需补齐 `navigator`/`screen`/`canvas` 等运行时指纹输入；更现实路线是保留浏览器上下文调用安全 SDK 自发签名（即"带浏览器跑"而非纯离线）。

## 验证应对（wsgsig 远程签名）

- 验证类型：自定义强混淆签名（非标准验证码），远程协作式。
- 是否需要人工接力：否（非验证码），但**纯离线无法复现**。
- 处理路由：`ai_assist`（还原 VM）或 `browser_handoff`（保留浏览器上下文由 SDK 自己签名）。本项目选择"保留浏览器上下文"路线更现实。
- 识别信号：登录前必发 `signupdate`；请求 URL 带 `?wsgsig=`；`4bf1` 导出强混淆 VM。

## 分析过程

- 类型判断：登录接口 + 密码加密 → 先查 RSA（JSEncrypt，易确认）；再查请求签名 → 命中 wsgsig 远程协作。
- 入口定位：全局搜 `setPublicKey` / `encrypt` 命中 `De`（@14909）与公钥 `q`（@9433）；搜 `/passport/login/v5/signInByPassword` 命中登录端点；搜 `signupdate` 命中远程签名协作。
- 环境补丁：密码加密无；wsgsig 需浏览器上下文。
- 复现方法：pycryptodome `PKCS1_v1_5` + 硬编码公钥；完整登录受阻于 wsgsig。

## 误判点

- 误判点 1：以为页面内 XHR/fetch hook 能抓到登录请求。→ 真实原因：登录请求经非主线程路径（疑似隐藏 form 提交/Worker），主线程 XHR 钩子始终为空；改用 CDP 网络层监听器才抓到 `signupdate`。
- 误判点 2：以为 CDP 监听器 `focus_xhr_fetch=true` 能抓到登录请求。→ 真实原因：该过滤只收 XHR/fetch，登录请求（若走 form 提交）为 Document 类型被过滤；且本会话后端重启后监听器 CDP 回调整体失效（见"验证结果"）。
- 误判点 3：以为 `wsgsig` 是纯前端本地签名可离线算。→ 真实原因：每次请求前本地 VM 先调远端 `signupdate` 取令牌再合成，属远程协作签名。

## 真正原因

- 真正原因：密码经 1024-bit RSA (PKCS#1 v1.5, JSEncrypt) 加密，公钥硬编码、明文直接加密，离线可复现；但登录请求还需 `wsgsig` 签名，该签名由 `safe-vendor` 的强混淆 VM `4bf1` 结合远端 `signupdate` 令牌协作生成，纯离线无法复现。
- 识别信号：`De()` 的 `setPublicKey(q).encrypt(e)` + 源码 `o={q:JSON.stringify(r)}` + `signupdate` 前置调用 + URL `?wsgsig=`。
- 修复方式（针对本项目）：新增 `cases/didichuxing_login_20260709.md` 与 `assets/repro/didichuxing_com_cn.py`（密码加密离线复现已闭环）。
- 工具链附带问题：后端重启后 CDP 监听器需在"无其它监听器"状态下重建才能重新接收 Network 事件；旧监听器停止后新监听器若未正确重新 enable Network 域会 0 捕获。

## 验证结果

- 生成位置：密码加密 `De`(@14909)，公钥 `q`(@9433)；签名 `4bf1`(safe-vendor)。
- 本地复现方式：`python assets/repro/didichuxing_com_cn.py`（验证 RSA 加密正确性并构造登录请求体骨架）。
- 验证结果：密码 RSA 加密已闭环（浏览器↔Python 双向一致）；完整登录因 wsgsig 远程签名 + 测试环境登录端点不可达，未能实抓实登，属预期阻断。

## 可复用规则

- 规则 1：登录页出现 `setPublicKey`/`encrypt` 且库为 JSEncrypt → 直接判定 RSA PKCS#1 v1.5，用 pycryptodome `PKCS1_v1_5` 复现；注意 JSEncrypt 默认小写 `public key` 头，import 时需转标准大写头（密钥体不变）。
- 规则 2：明文是否先 `encodeURIComponent` 取决于站点（滴滴：直接加密；iyunzhi：先 encodeURIComponent）。复现前需在源码确认。
- 规则 3：请求体 `{q: JSON.stringify(r)}` 形态 + 端点含 `?wsgsig=` → 滴滴系签名特征；`wsgsig` 几乎都伴随 `security.xiaojukeji.com/sign/v1/wsgsigsession/signupdate` 远端协作。
- 规则 4（项目工具链）：CDP 监听器在后端重启/多监听器竞态后可能失活；排查时先 `ch_listener_status` 看 `event_count`，必要时停掉其它监听器、新建唯一全类型监听器并确认 `network_enabled=true`。

## 回归说明

- 易变点：硬编码 RSA 公钥可能随版本更换；`wsgsig`/安全 SDK（safe-vendor 哈希名）频繁升级混淆；`signupdate` 接口路径或令牌字段可能调整；登录端点路径字段可能微调。
- 下次升级先检查：① `q` 公钥常量；② `4bf1` 模块与 `signupdate` 流程；③ `/passport/login/v5/signInByPassword` 路径与 `q` 字段结构；④ 测试环境代理是否放行登录端点。

## 踩坑记录

- 误判（XHR 钩子抓登录）→ 真实原因（非主线程路径/被过滤）→ 识别信号（主线程钩子为空、CDP 抓到 signupdate）→ 修复方式（改用 CDP 监听器）→ 可复用规则（规则 3/4）。
- 误判（wsgsig 纯本地）→ 真实原因（远端 signupdate 协作）→ 识别信号（登录前必发 signupdate、URL 带 ?wsgsig）→ 修复方式（标注远程签名阻断，保留浏览器上下文路线）→ 可复用规则（规则 3）。
- 工具链坑（后端重启后 CDP 监听器 0 捕获）→ 真实原因（多监听器竞态/Network 域未重 enable）→ 识别信号（`event_count=0` 但页面已加载）→ 修复方式（停其它监听器、重建唯一全类型监听器确认 network_enabled）→ 可复用规则（规则 4）。
