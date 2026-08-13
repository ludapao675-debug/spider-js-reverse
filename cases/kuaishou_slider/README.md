# 快手滑块验证码协议逆向（快手自研 captcha.zt.kuaishou.com）

> ⚠️ 重要纠正：此前误判为「字节系 rmc-captcha」（verifycenter.js / captcha.js）。
> 实网抓包证明快手网页端滑块是**自研系统** `captcha.zt.kuaishou.com`，与抖音/头条的
> `rmc.bytedance.com` 体系**完全不同**。本文档为实测证据重构。

## 基本信息

- 目标：快手网页端滑块拼图验证码（"请完成安全验证" / 拼图缺口，type=1）
- 类型：滑块拼图（slide / 拼图缺口），另有 spinner(旋转,type=2) / picker(点选,type=4)
- 验证框架：**快手自研 `captcha.zt.kuaishou.com`**（iframe 内独立加载，非字节系）
- 加密 SDK：`encrypt.ee7d2a41.js`（**JSFG 虚拟机壳** + Jose 库，强混淆）
- 日期：2026-08-02
- 进度：✅ 接口路径 + 提交字段 100% 静态还原；⏳ verify 真实 POST body 待新滑块会话实网补抓（当前 captchaSn 已过期）

## 1. 验证框架加载（实网证据）

父页注入 iframe，src 实测全貌：
```
https://captcha.zt.kuaishou.com/iframe/index.html
  ?captchaSession=<base64-proto>      # 顶层会话（protobuf 编码，浏览器 URL 中可见）
  &type=1                              # 1=滑块拼图 2=旋转 4=点选
  &configUrl=https://captcha.zt.kuaishou.com/rest/zt/captcha/sliding/config
  &bizName=DOWNSTREAM_SMS_V2          # 业务场景
  &displayType=popup
```

iframe 内加载脚本（实测）：
- `iframe/index.c9ae8c81.js`（445KB，webpack 打包，**字符串加密数组混淆**，已本地反混淆）
- `encrypt.ee7d2a41.js`（46KB，**JSFG 虚拟机壳**，真正的加密逻辑在 `e("[\"<script>\"...]")` 字节码里）
- `chunk-vendors.39300a01.js`、`weblogger.2e328f42.js`

## 2. 核心接口（已实网抓到 3 个 GET，verify POST 待补）

```
GET  /rest/zt/captcha/sliding/config            # 取配置（bgImgWidth/Height、sliderImg 等）
GET  /rest/zt/captcha/sliding/bgPic?captchaSn=  # 背景缺口底图
GET  /rest/zt/captcha/sliding/cutPic?captchaSn= # 拼块图
POST /rest/zt/captcha/sliding/verify(推断)       # 提交轨迹校验（待实网抓取确认路径/body）
```
- `captchaSn`：每次滑块会话的**子会话号**（protobuf，从 config 响应里获取，非顶层 captchaSession）
- 注意：浏览器直连重放 bgPic/cutPic 会返回 `350010 captchaSN expired` / `350006 captchaSN err`
  → **captchaSn 有有效期，必须同一会话内使用，不能跨会话重放**。

## 3. 提交 body（verifyCaptcha 函数，iframe/index.js @200263 已还原明文）

实网 JS 里 `verifyCaptcha` 拼装的提交对象（滑块模式）：
```js
u = {
  captchaSn:        <子会话号>,
  bgDisWidth:       parseInt(..., 10),   // 背景图显示宽
  bgDisHeight:      parseInt(..., 10),   // 背景图显示高
  cutDisWidth:      parseInt(...),        // 拼块显示宽
  cutDisHeight:     parseInt(...),        // 拼块显示高
  relativeX:        parseInt(...),        // ★ 缺口相对 X（答案横坐标）
  relativeY:        parseInt(...),        // ★ 缺口相对 Y（答案纵坐标）
  trajectory:       a.getConfig_res_(1),  // ★ 拖拽轨迹（经编码函数处理）
  gpuInfo:          JSON.stringify(Object(Gt.b)()),  // GPU/环境信息
  captchaExtraParam:JSON.stringify(i)     // 额外参数
}
// 发送入口（统一封装）
s = vn({ action: <action名>, params: { type: <滑块类型>, word_num: 0 }, contentPackage: {} }, <状态>)
```
- 旋转模式(type=2)对应字段为 `angle` / `width` / `height` / `trajectory`（@221495）
- `relativeX`/`relativeY` 即缺口坐标 = **拖拽目标位移**（与 kgcaptcha 一致：手柄↔拼块 1:1）
- `trajectory` 由 `a.getConfig_res_(1)` 编码（参数 `1` 疑为编码模式；具体算法在 encrypt.js 字节码或 iframe 内，待动态执行还原）

## 4. 轨迹采集格式（iframe/index.js 事件层）

滑块监听 `touch-move`/`drag-start`/`drag-end`，每次 move 记录：
```js
{ x: event.clientX, y: event.clientY, time: Date.now() }   // 与 kgcaptcha 同构
```
组成数组 `trajectory`，拖拽起点入数组，松手时提交。`getConfig_res_` 对数组做最终编码。

## 5. 加密层（encrypt.ee7d2a41.js —— JSFG 虚拟机壳）

- 文件结构：`window.Jose=...`(标准 Jose/JWE 库) + 自定义 `Fiber` 字节码虚拟机
- 真正加密逻辑藏在 `e("[\"<script>\",0,[[21]...]")` 这段 **JSFG 编码字节码** 里，
  静态无法直接阅读，需动态执行 `e(encodedString)` 解出函数并挂到 window。
- 内部引用 CryptoJS（`StreamCipher`/`BlockCipherMode`/`EvpKDF` → AES/DES/RC4 全套），
  推测轨迹/参数用 CryptoJS 对称加密或 Jose JWE 封装。
- **还原路线**：在浏览器内执行该 JS → 用 `ch_debugger_get_scope` 在加密调用处取密钥/IV/明文，
  或 `ch_sdenv_auto_reproduce` 智能复现（禁止手写 polyfill）。

## 6. 缺口识别

- 用接口原图：`bgPic`(底图) + `cutPic`(拼块)，不在前端渲染图算缺口（避开 DPR/CSS transform）。
- `ddddocr.slide_match(piece_bytes, bg_bytes)` → 缺口左边 x（`relativeX` 目标值）。
- `drag_distance = gap_left × (display_w / natural_w)`；快手滑块手柄↔拼块 1:1。

## 7. 拖拽执行（关键经验，来自 kgcaptcha_slider 案例）

- **必须走原始 CDP Input**（`mousePressed[buttons:1] → mouseMoved[buttons:1] → settle → mouseReleased`），
  不要 DrissionPage `Actions.hold/release`（会丢按键态，松手前回弹判失败）。
- 轨迹人类化：单调递进钟形加减速 + 末尾停顿，无反向过冲，总位移 = 缺口距离。
- 滑块在跨域 iframe 内，CDP 需切到 iframe 的 `target_id`（用 `ch_page_navigate`/CDP Target 树获取），
  不能用父页坐标。

## 8. 本地复现路线图（待实网闭环）

1. 用户重新触发滑块（风控被动触发，无法主动导航）→ 新 `captchaSession`+`captchaSn` 生成。
2. `ch_listener_start` 实时抓 `config`/`bgPic`/`cutPic`/`verify` 全链路（已挂监听器 `lst_2d4c1b1cc085457b`）。
3. 取 `bgPic`/`cutPic` → ddddocr 算 `gap_left` → `relativeX`/`relativeY` 目标。
4. 切 iframe target → CDP Input 拟人拖拽 → 实时抓 **verify POST 真实 body**（解 `VERIFY_FIELDS` 占位）。
5. 动态还原 `encrypt.js` 加密函数：在加密调用处取密钥/IV，写纯协议脚本：
   `requests` 发 config → 本地识别缺口 → 本地生成人类化轨迹 → 加密 → POST verify。
6. 成功判据：响应 `code=1` / passToken / 父窗口收到 `success`。

## 9. 已落盘证据文件（cases/kuaishou_slider/）

| 文件 | 说明 |
|------|------|
| `iframe_index.c9ae8c81.js` | iframe 主 JS 原文（445KB，webpack+字符串混淆） |
| `iframe_index.deobf.js` | 字符串反混淆后可读版（1971 处 `Hi/Na/Ei` 调用已还原） |
| `encrypt.ee7d2a41.full.js` | 加密 JS 原文（46KB，JSFG 虚拟机壳） |
| `_resolved_strings.json` | 还原的字符串表（Wi 数组 shift162 / Xi 数组 shift452 + base64 + URI 解码） |
| `repro_skeleton.py` | 协议复现骨架（VERIFY_FIELDS 待 verify 实网样本补全） |

## 10. 阻塞与风险

- **captchaSn 过期**：旧会话的 bgPic/cutPic 无法重放（`350010/350006`），verify 真实样本需新滑块会话。
- **加密层未破**：encrypt.js 是 JSFG 字节码壳，明文加密函数需动态执行还原，禁止静态臆测。
- **合规边界**：自动拖拽绕过滑块属风控对抗；定位为「协议逆向 + 本地复现」用途，拖拽建议人工触发或授权测试环境。
- **跨域 iframe**：父页 JS 读不到 iframe 内 `window`，解密函数/加密密钥只能在 iframe target 内取证。

## 11. 可复用规则

1. 快手滑块是**自研体系** `captcha.zt.kuaishou.com`，与字节系 `rmc-captcha` 协议**不通用**，勿混用。
2. webpack 字符串加密数组混淆（base64 + 数组循环移位 + 二次 URI 解码）可用本地脚本批量还原，
   反混淆后定位 `verifyCaptcha` 提交逻辑极高效。
3. 滑块识别优先接口原图；拖拽必须走 CDP `buttons:1` 序列；缺口坐标 = 相对位移目标。
4. 抓包定位「定位门禁」已满足（已搜到 captcha 关键词），可用 `ch_breakpoint_set_xhr` 在 verify 处断点取 body。
