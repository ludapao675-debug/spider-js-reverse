# kgCaptcha 触发式滑动拼图（通用接口原图识别 + 拖拽回弹修复）

## 基本信息

- 目标名称：kgCaptcha 触发式滑动拼图
- 目标类型：滑块验证码（slider / 拼图缺口）
- 目标地址：`https://www.kgcaptcha.com/demo/content?t=2`
- 日期：2026-07-28
- 结论：✅ 干净会话下识别+拖拽已跑通（绿态 + token 回填）；通用「接口原图」识别路径与拖拽回弹修复已落地

## 页面结构（触发式）

- `#captchaBox`：触发条（360×45，文案「向右拖动滑块完成拼图」），**点击后**才弹出拼图层。
- `.bodyCaptcha`：弹出层（360×483）。
- `.KgBasemapTop`：拼图**背景图**，360×180，`background-image` 为**内联 base64 data URI**（来自 kg `requestFront` 接口）。
- 拼块：`.bodyCaptcha` 内一张 `<img>`，`src` 为**内联 base64 data URI**，72×180，初始贴左边（x≈0）。
- `#KgSlide`：滑轨（360×45）；手柄 = `#KgSlide>div:nth-of-type(3)`（52×45，箭头背景）。
- `#kgCaptchaToken`：隐藏 input，**验证通过后由 kg 回填 token**（成功判据之一）。

## 证据

- 目标请求：kg 前端接口 `requestFront`（返回并内联 bg/piece 的 base64）。
- 关键参数：拖拽距离 = 缺口左边 x（背景自然坐标）× 缩放；成功后 `#kgCaptchaToken` 回填 150 字符 token（样本 `eef1debe73bac1123a3c20e2…`）。
- 相关源码：识别/执行在 `server/captcha/auto_domain.py`；拖拽在 `server/captcha/../browser_runtime.py`。
- 运行时变量：`.KgBasemapTop` 自然 360×180 = 显示 360×180 → **scale=1（不缩放）**；ddddocr `slide_match` target 宽固定 90。
- 网络记录：bg/piece 均为 data URI，无需二次请求。

## 识别公式（通用接口原图）

1. 只取**接口原图**：`.KgBasemapTop` 的 `background-image` data URI 作 bg；`.bodyCaptcha img[src^=data:]` 作 piece。**不截前端渲染图**，绕开 DPR/CSS transform/裁剪误差。
2. `ddddocr.DdddOcr(det=False,ocr=False).slide_match(piece_bytes, bg_bytes, simple_target=True)` → `target=[x1,y1,x2,y2]`，`gap_left=x1`。
3. `natural_w` 由后端 PIL 解码 bg 得到；`display_w = bg.getBoundingClientRect().width`。
4. `scale = display_w / natural_w`；`drag_distance_css = gap_left × scale`（kg scale=1，故 = gap_left）。
5. 手柄↔拼块 **1:1**，`ch_page_drag_element(offset_x=drag_distance)`。
6. 实测样本：`target=[226,0,316,180]` → 拖 226px → 通过。

## 拖拽回弹修复（本案例核心 bug）

- **现象**：拼块拖到缺口，**松手前又滑回原点**，kg 判失败（`#KgSlide` 变红 `rgb(255,0,0)`）。
- **根因**：`page_drag_element` 的 `human_like` 走 DrissionPage `Actions.hold()/release()`，**不维持鼠标左键 `buttons:1` 状态**（DrissionPage#569），滑块未真正进入拖拽态，mouseup 落地前被弹回。
- **修复**（`server/captcha/../browser_runtime.py`）：
  - 新增 `_build_human_trajectory()`：单调递进钟形加减速 + 末尾停顿，**无反向过冲**，总位移精确。
  - `page_drag_element` 的 human_like 水平滑块**优先自动走原始 CDP Input**（`_raw_cdp_mouse_trajectory`：mousePressed[buttons:1]→mouseMoved[buttons:1]→settle→mouseReleased），DrissionPage Actions 仅回退。
- **修复前后对比**：

| | 修复前 | 修复后 |
|---|---|---|
| method | `drissionpage+Actions.right_left` | `browser_runtime+raw_cdp_pointer_auto` |
| 现象 | 松手前弹回，红色失败 | 稳定吸附缺口 |
| `#kgCaptchaToken` | 空 | 回填 150 字符 token |
| `#KgSlide` | 红 `rgb(255,0,0)` | 绿 `rgb(1,199,181)` |

## 通用路径接入

- `server/captcha/auto_domain.py`：新增 `recognize_generic_slider_fast()` + `_GENERIC_SLIDER_PROBE_JS`，接在 `recognize_session_plan` 的 **yidun 之后、外部 `CaptchaSolver` 之前**；命中直接返回，miss 则零回归回退。
- 防误判：只在**验证码容器内**（祖先含 `captcha/verify/puzzle/jigsaw/geetest/shumei/yidun/slider`，**故意不含 `slide`** 以排除 `swiper-slide` 轮播图）找 bg/piece；距离护栏 `[5, 显示宽]`；含 ~3s 重试等待拼图异步加载。
- 外部 solver 超时护栏：`CRYPTO_HUNTER_CAPTCHA_EXTERNAL_TIMEOUT`（默认 30s），避免识别 miss 回退外部 solver 在重 DOM 页 `tab.ele` 挂死到 120s。实测 solve 34.7s 返回，替代原 120s。

## 误判点

- 误判点 1：以为 ddddocr 距离 13/76/116「抖动」——实为**不同验证码**（bg hash 每次不同），各自可能都对。
- 误判点 2：以为回弹是 kg 服务端拒绝——实为**客户端 mouseup 按键态丢失**（DrissionPage Actions）。
- 误判点 3：以为通用求解截前端渲染图即可——渲染图受缩放/遮挡影响，**应优先接口原图**。

## 真正原因

- 拖拽失败根因：DrissionPage `Actions` 释放不维持 `buttons:1` → 松手前回弹。
- 修复方式：滑块拖拽改走原始 CDP Input（保持按键态，mouseup 精确落点）。

## 验证结果

- 干净会话：识别 226 → CDP 拖拽 → `#kgCaptchaToken` 回填 + `#KgSlide` 绿态 = **通过**。
- 回归：`pytest tests/server/test_captcha_auto_domain.py test_captcha_auto_executor.py test_captcha_auto_bridge.py` → **29 项全绿**。
- 分析脚本：`scratch/kg_solve.py`（bg/piece → ddddocr 距离）。

## 可复用规则

- 规则 1：滑块识别**优先接口原图**（`img.src` / 背景图 `url()` / 内联 base64），在**原图空间**算缺口，再 `display_w/natural_w` 转 CSS。
- 规则 2：滑块拖拽**必须走原始 CDP Input**（press/move/release 带 `buttons:1`），不要用 DrissionPage `Actions.hold/release`（会松手前回弹）。
- 规则 3：容器判定**用 `slider` 不用 `slide`**，否则会把 `swiper-slide` 轮播图误当验证码图。
- 规则 4：外部兜底 solver 必须有**超时护栏**，避免重 DOM 页 `tab.ele` 挂死。

## 回归说明

- 易变点：kg 手柄 `nth-of-type` 索引随失败态变化（红/绿态会插入不同子元素）；缺口每次不同；触发条类名。
- 下次先查：`.KgBasemapTop` 是否渲染出尺寸（0×0 说明未出图）；`#kgCaptchaToken` 是否回填。

## 踩坑记录（反自动化观察）

- kgCaptcha **服务端反自动化**：首个干净会话正常渲染 `.KgBasemapTop`(360×180) 并可求解；**重复自动访问后，服务端拒绝渲染拼图背景**（`.KgBasemapTop` 恒为 0×0，仅弹层框架出现），换全新 profile(kg_v2/v3) 无效 → 属 **IP+行为层标记**，非指纹层，非本项目代码问题。
- 复现建议：换干净出口 IP + 全新 profile，**首次访问即跑**（趁未被标记）。
- 误判 -> 真实原因 -> 识别信号 -> 修复方式 -> 可复用规则：
  松手前回弹 -> DrissionPage 释放丢按键态 -> `method=drissionpage+Actions.right_left` 且滑块变红 -> 改原始 CDP Input -> 滑块拖拽一律走 CDP `buttons:1` 序列。
