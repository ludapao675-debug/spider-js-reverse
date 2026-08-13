# 天翼云登录复现与踩坑记录

## 基本信息

- 目标名称：天翼云登录
- 目标类型：登录接口签名与加密链路
- 日期：2026-07-06
- 负责人：Codex

## 问题描述

- 现象：`ctyun_login_reproduce.py` 返回 `{"resultCode":"-1","resultMsg":"账户或密码不正确","data":null}`
- 失败表现：之前卡在“请求头签名”，实际根因是漏了 URL 查询参数签名 `comParam_signature`
- 结论：这是业务层返回，说明签名、加密、请求格式都已经被服务端接受；当前失败原因更接近账号不存在或测试账号无效

## 证据

- 目标请求：`/account/login?referrer=wap&mainVersion=300031500&comParam_curTime={n}&comParam_seqCode={r}&comParam_signature={sign}&isCheck=true&locale=zh-cn`
- 关键参数：
  - `n = 当前毫秒时间 - timestampOffset`
  - `r = 32 位大写十六进制随机串`
  - `sign = md5(n + r + md5(r + "s54zv9bm1vd5czfujy6nnuxj1l4g2ny6" + n))`
  - `Cst = 毫秒时间戳`
  - `Csm = hex(HMAC-SHA256(key=ct_ss, msg=path+":"+Cst+":"+ct_ss))`  ← **实测为 SHA-256（64位hex），非 SHA-1**
  - `path` 在浏览器真实登录调用里取 `"login"`
- 请求体格式：
  - 必须是 `application/x-www-form-urlencoded`
  - 只能有 `userName` 和 `password` 两个字段
- 密码加密：
  - `TripleDES-ECB-PKCS7`
  - `key = pad_key_24(remove_whitespace(account))`，**实测填充字符为 `'0'`（账号右补 0 至 24 字节）**
- 相关源码：`assets/repro/ctyun_wap_login_reproduce.py`
- 运行时证据：浏览器真实调用后，服务端接受签名与加密，最终返回业务层账号/密码错误

## WAP 复现验证（2026-07-10）

- 目标：`https://m.ctyun.cn/wap/main/auth/login`（移动端登录，端点 `/account/login?referrer=wap`）
- 方法：用 MCP 浏览器注入捕获真实登录请求（账号 `testuser123@163.com` / 密码 `Testpass@123`，服务端回“账户或密码不正确”说明链路已被接受），再用 Python 逐项复算比对。
- 捕获到的真实请求样本（节选）：
  ```
  POST /account/login?referrer=wap&mainVersion=300031500
       &comParam_curTime=1783678401184
       &comParam_seqCode=931086D20A7775EA5247636CEEB5D22A
       &comParam_signature=bf165ec4dc64c59c195a546e9bb0d124
       &isCheck=true&locale=zh-cn
  Headers: Cst=1783678401367, Csm=17eff32f... (64hex=SHA-256), x-riskdevicesign=8900dff7c76e372ac8a39b6af01587e9
  Body: userName=testuser123@163.com&password=Yzm8X3Zrk+//r7JmLandzw==
  ```
- 复算比对（两次独立真实请求均通过）：
  - `comParam_signature = md5(n + r + md5(r + SALT + n))` → ✅ 完全一致
  - `Csm = hex(HMAC-SHA256("", "login:"+Cst+":"))` → ✅ 完全一致（证实为 SHA-256）
  - `password = base64(TripleDES-ECB-PKCS7(pwd, account+"00000"))` → ✅ 完全一致
- 结论：WAP 登录与 PC 端使用**完全相同**的签名/加密链路；算法已 100% 离线复现。
- 交付脚本：`assets/repro/ctyun_wap_login_reproduce.py`（含 `self_test()` 用两次真实样本自校验，运行即 PASS）。
- 易错点修正：
  1. `Csm` 是 **HMAC-SHA256**，不是案例原文写的 HMAC-SHA1（64hex=256bit 可直接判断）。
  2. 密码密钥 `pad_key_24` 的填充字符是 **`'0'`**（账号右补足 24 字节），不是空格/空字节。
  3. 捕获到的 `password` base64 形如 `Yzm8X3Zrk+//r7JmLandzw==`（含连续 `//`），是合法 24 字符标准 base64，勿误读为单 `/`。

## 分析过程

- 类型判断：先按“请求头签名”排查，后来发现真正拦截点在 URL 查询参数签名
- 入口定位：先保证请求能进入接口，再分别验证 URL 参数签名、请求头签名、请求体格式、密码加密
- 环境补丁：请求体必须从 JSON 改为表单；字段必须精简到 `userName/password`
- 复现方法：逐项对比浏览器真实请求，先让服务端接受链路，再替换真实账号测试业务结果

## 最终结果

- 生成位置：`ctyun_login_reproduce.py`
- 本地复现方式：替换为真实天翼云账号后直接运行复现脚本
- 验证结果：当前返回 `账户或密码不正确`，说明签名和加密链路已通过服务端校验

## 回归说明

- 哪些点容易变：
  - `timestampOffset` 可能会变
  - `comParam_signature` 的参数拼接顺序不能错
  - 登录接口返回的业务错误可能会误导排障方向
  - 请求体格式从表单改回 JSON 会直接失效
- 下次升级时先检查什么：
  - 先看 URL 查询参数签名是否仍然存在
  - 再看请求头 HMAC 是否仍然使用 `path="login"`
  - 再看密码加密是否仍然是 `TripleDES-ECB-PKCS7`

## 踩坑记录

### 1. 误判为只有请求头签名

- 误判：只检查请求头签名，忽略了 URL 查询参数里的 `comParam_signature`
- 真实原因：天翼云登录有两层校验，URL 参数签名决定接口能不能进
- 识别信号：不带这组参数时会返回“客户端版本过低”
- 修复方式：先补齐 `comParam_curTime`、`comParam_seqCode`、`comParam_signature`
- 可复用规则：登录类接口先查 URL 查询参数，不要默认只看 Header

### 2. 请求体格式错用 JSON

- 误判：把登录参数按 JSON 发送
- 真实原因：接口要求 `application/x-www-form-urlencoded`
- 识别信号：返回“缺少参数”
- 修复方式：只提交 `userName` 和 `password`
- 可复用规则：登录接口先确认 Content-Type，再决定是 form 还是 JSON

### 3. 请求头签名的 path 取值容易写错

- 误判：把完整 URL 或错误路径塞进 HMAC 签名
- 真实原因：真实调用时 `ct_ss` 为空，`path` 取 `"login"`
- 识别信号：签名长度对了，但服务端仍然拒绝
- 修复方式：按浏览器实际行为复现 `Csm = hex(HMAC-SHA1(key=ct_ss, msg=path+":"+Cst+":"+ct_ss))`
- 可复用规则：签名里一旦出现 path，优先从浏览器原始调用推断它是不是“短路径名”而不是完整 URL

### 4. 通用可复用坑点

- 关键词编码：用 `urllib.parse.quote()`，不要把 `urlencode()` 的 `+` 当成通用答案
- 空值字段保留：`_extra=`、`category_id=` 这类字段不要随手删
- 0 值字段保留：`pubtime_begin_s=0` 这种字段不要默认省略
- 排序规则：按 key 字符串升序排序，再拼接签名或请求串

## 可复用规则

- 先分层，再下结论：
  1. URL 查询参数签名
  2. 请求头签名
  3. 请求体格式
  4. 字段保留与排序
  5. 账号/业务层校验
- 看到“账号或密码不正确”这类业务错误时，不要立刻回头怀疑签名，先判断链路是否已经被服务端接受
- 同类登录站点优先用“误判 -> 真实原因 -> 识别信号 -> 修复方式 -> 可复用规则”的格式写入案例，后续 AI 才能直接复用
