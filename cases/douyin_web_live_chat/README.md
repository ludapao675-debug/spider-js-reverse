# 抖音 Web 直播「与大家互动」发送（v3，2026-07-27）

> 任务：`task_20260725_144506_2d55d021`  
> 目标：`GET https://live.douyin.com/webcast/room/chat/`  
> 运行证据：`server/data/reverse_runs/task_20260725_144506_2d55d021/`  
> UI：`.zone-container.editor-kit-container[contenteditable=true]`（文案「与大家互动」）

---

## 0. v3 核心结论（本轮攻坚定论，全部实证）

一句话：**纯 HTTP 协议发送弹幕结构性不可行；唯一可靠方案是 Path B（保活浏览器 + CDP 驱动页面 IM SDK），且已实证可在窗口最小化/切走时无人值守运行。**

三层门槛（缺一不上墙）：

| 层 | 门槛 | 裸 HTTP 能否满足 |
|----|------|:---------------:|
| 1 网关 | `a_bogus` + 浏览器指纹 | ✅ sdenv 可签 |
| 2 anti-bot | 新鲜 `bd-ticket-guard-client-data`（`web-sign-type=1` + 现签 `req_sign`） | ✅ 页内裸 XHR 也被拦截器自动盖章 |
| 3 广播 | **页面 IM SDK 的活体 WSS 会话** | ❌ **无法**（纯 Python 无此会话） |

**第 3 层是杀手锏**：裸 HTTP 请求与 UI 请求逐字节同构、服务端都返回 `status_code=0`+`msg_id`，但裸 HTTP 的消息**其他客户端收不到**（独立观察号实证）。广播授权不在 HTTP 请求/响应里，而依赖 IM SDK 常驻 WSS 会话状态。

**对旧结论的修正**：v1/v2 认为「页面必须前台可见」是硬门槛——**不准确**。真实门槛是 `document.hidden`：CDP attach 模式下 DevTools 保活渲染进程，**窗口最小化/切到别的应用时 `visibilityState` 仍为 `visible`**，照发上墙。只有在**本浏览器内把直播标签切到另一个标签页**才会真 `hidden` 而不上墙。

---

## 1. 结论摘要（以公屏为准）

| 项 | 结论 |
|----|------|
| 端点 | **`GET`** `live.douyin.com/webcast/room/chat/`（axios `get` + query） |
| 关键参数 | `room_id`=**长 ID**、`content`、`type=0` + `aid=6383` 等 |
| 短号→长 ID | `GET /webcast/room/web/enter/?web_rid=...` → `data.enter_room_id` |
| 业务成功码 | 常返回 `status_code=0` + `msg_id` |
| **公屏上墙** | **不能**仅凭 `status_code=0` 判定；须看 `.webcast-chatroom___list` / 肉眼 |

### 上墙对照（账号「哈哈11」，多房间复现）

| 方式 | 请求特征 | 公屏 |
|------|----------|------|
| 用户手动输入发送 | 完整 `bd-ticket-guard-*`（含 **client-data**，`web-sign-type=1`） | **上墙** |
| **Path B（CDP insertText + 直调 onClick）** | 走页面 axios 链，拦截器自动现签 client-data | **上墙**（本轮交付方案） |
| 页内裸 XHR/fetch（同构请求） | 拦截器也自动盖章，`web-sign-type=1` + 现签 | `status_code=0` **但不上墙**（缺活体 WSS） |
| Python 纯协议（无浏览器） | — | **结构性不可行** |
| 直接调 React `onSend(content)` | 有时根本不发 chat 请求 | 不上墙 |

> 关键修正：v2 认为「自动化带完整 client-data 仍可能不上墙/静默丢弃」——现已查明真因：那些失败案例是 **`document.hidden=true`**（调试时切标签页/真后台），而非 client-data 问题。Path B 在 `visible`（含 CDP 保活的最小化）下稳定上墙。

---

## 2. ticket-guard 要点

真 UI 发包常见头：

- `bd-ticket-guard-client-data`（**关键**，base64 JSON：`ts_sign` / `req_content=ticket,path,timestamp` / `req_sign` / `timestamp`）
- `bd-ticket-guard-ree-public-key`
- `bd-ticket-guard-version` / `web-version` / `web-sign-type`

页内 `securitySDK.secureProxy.getBdTicketGuardHeader({url, method})`：

- 能返回公钥等静态字段；
- **单独调用通常拿不到 `client-data`**（`signTime=0`，`web-sign-type=0`）；
- `client-data` 由业务 axios/secsdk 拦截器在真实发包链里生成。

踩坑：不可把 API 返回的整包 `{bdTicketGuardHeaders, timeCollect, extras}` 直接 `setRequestHeader`，否则会变成 `bdTicketGuardHeaders: [object Object]`。

---

## 3. Source → Sink（含广播真相）

```text
「与大家互动」编辑器 Enter / Path B 直调 onClick
  → 业务 onSend 链
  → o.ZP.get("/webcast/room/chat/", {params:...})
  → 拦截器追加 msToken / a_bogus / bd-ticket-guard-*（含现签 client-data）
  → GET /webcast/room/chat/?room_id=<长ID>&content=...&type=0&...
  → HTTP 200 + status_code=0 + msg_id  （仅“收单/存档”，≠ 广播）
  → 【广播真相】服务端需将此 HTTP 与该账号的**活体 WSS 会话状态**关联，才授权广播
  → 裸 HTTP 无活体 WSS 会话 → 收单但不广播（其他客户端收不到）
```

关键：消息**内容本身走 HTTP**（非 WSS）；WSS 只走 frontier `ack`/心跳帧。但服务端的广播判定依赖 IM SDK 常驻 WSS 会话——这是纯 HTTP 无法跨越的部分。

---

## 4. 可用脚本

目录：`server/data/reverse_runs/task_20260725_144506_2d55d021/repro/`

### 4.1 交付工具（推荐）

| 脚本 | 用途 |
|------|------|
| **`send_danmaku_pathb.py`** | **最终交付：Path B 无 UI 按钮点击发送，可无人值守（窗口可最小化）** |

```bash
# 单发
E:\aicode\.venv\Scripts\python.exe send_danmaku_pathb.py "你好" --room 994534518821
# 保活循环（每 30 秒一条，Ctrl+C 退出）
E:\aicode\.venv\Scripts\python.exe send_danmaku_pathb.py "弹幕{t}" --room 994534518821 --loop --interval 30
```

Path B 发送三步（`LiveDanmakuSender.send`）：
1. CDP 鼠标聚焦编辑器 + 三击全选 + 退格清空（Draft.js 需 trusted 事件，不可省）
2. `Input.insertText` 写入内容（更新 Draft.js 状态）
3. JS 直调发送按钮 `__reactProps.onClick`（省去按钮鼠标点击，走页面 axios 链）

### 4.2 本轮实验脚本（证据链，勿当日常工具）

| 脚本 | 验证的结论 |
|------|-----------|
| `test_broadcast_observer.py` | 裸 XHR 消息独立观察号收不到 → 广播需活体 WSS |
| `test_rawxhr_signtype.py` | 裸 XHR 也拿到 `web-sign-type=1` + 现签 client-data，与 UI 同构 |
| `compare_response_self_see.py` | 逐字段 diff：`content_self_see_status` 等业务字段全同（影子封禁证伪） |
| `reverse_order_verify.py` | UI先/裸XHR后，仍 UI 上墙裸XHR不上墙 → 与顺序/限频无关 |
| `capture_all_net_send.py` | UI 发送全量网络：仅 1 个 chat HTTP + 遥测，无额外广播请求 |
| `capture_wss_send.py` / `decode_frontier_frame.py` | WSS 帧全是 frontier `ack` 帧（`wss_msg_type:wrds/r`），无离散消息发送帧 |
| `hook_ws_send_stack.py` | WSS.send 调用栈指向 `8818.6125bf19.js` 传输层（异步边界截断） |
| `test_hidden_send_v2.py` | 强制 `document.hidden=true` → 不上墙（确认真实门槛是 hidden） |
| `test_minimized_override.py` / `test_send_2msgs.py` | 窗口最小化/切走 → CDP 保活仍 visible，连发多条均上墙 |

### 4.3 早期脚本（历史）

| 脚本 | 用途 |
|------|------|
| `send_via_keyboard.py` | CDP 聚焦 → 输入 → Enter（最接近手动） |
| `send_danmaku.py` | 基础 CDP 封装（`Cdp` / `find_live_tab` / `wait_visible`，被上面脚本复用） |
| `send_live_chat.py` | 本地/页内协议发（`status_code=0` 但不上墙） |

---

## 5. 踩坑

| 误判 | 真实情况 |
|------|----------|
| `status_code=0` = 发送成功上墙 | 仅接口收单/存档；广播需活体 WSS 会话（拿 `msg_id` 也不代表广播） |
| Cookie + a_bogus 即可协议复现上墙 | 不足；即使补齐 client-data（sign-type=1）仍不广播，缺活体 WSS |
| 直接 `fiber.onSend(text)` = UI 发送 | 常不触发真实请求（Draft.js 内容从 state 读，需 trusted 事件写入） |
| 无参 `getBdTicketGuardHeader()` 可复刻 UI 签名 | 单调返回 sign-type=0；true 的现签 client-data 由 axios/XHR 拦截器在真实发包链生成 |
| 发送按钮可 `btn.click()` | 该按钮是 **SVG 元素**，无 `.click()` 方法；需直调 `__reactProps.onClick` |
| 页面必须前台可见 | **不准**；真实门槛是 `document.hidden`，CDP attach 保活下最小化仍 visible（见 6.4） |
| 高频自动化 | 加速踢登录（`20003`）/ 验证码；须控频（建议 ≥30s 间隔） |

---

## 6. 纯协议可行性证据链（v3 完整实证）

> 本节取代 v2「未闭环项」。经系统性双向对照实验，纯协议不可行的原因已从推测升级为字段级/客户端级实证。

### 6.1 逐层排除（每条都有对照实验）

| 假设 | 实验 | 结果 | 脚本 |
|------|------|------|------|
| 403 是服务端收紧 | 直测 sdenv 签名 | **证伪**：403 是脚本指纹参数 bug（Chrome120 vs Edge150），签名本身正常 | — |
| 缺 client-data | 页内裸 XHR 抓请求头 | **证伪**：裸 XHR 被拦截器自动盖章，`web-sign-type=1` + 现签 `req_sign`，与 UI 同构 | `test_rawxhr_signtype.py` |
| room_id 过期 | 取当前 room_id 裸发 | **证伪**：正确 room_id 仍不上墙 | `test_rawxhr_correct_room.py` |
| 影子封禁（self_see 标记） | 逐字段 diff response | **证伪**：`content_self_see_status` 两边都=0，业务字段全同 | `compare_response_self_see.py` |
| 发送顺序/限频 | UI先/裸XHR后 双向对照 | **证伪**：无论顺序，永远 UI 上墙、裸XHR 不上墙 | `reverse_order_verify.py` |
| 缺某个额外广播请求 | UI 发送全量网络捕获 | **证伪**：仅 1 个 chat HTTP + 遥测，无额外请求 | `capture_all_net_send.py` |
| 消息走 WSS 离散发送帧 | 抓解全部 WSS 帧 | **证伪**：全是 frontier `ack` 帧，无消息发送帧；消息走 HTTP | `capture_wss_send.py` / `decode_frontier_frame.py` |

### 6.2 决定性正面证据

1. **独立观察号实证**（`test_broadcast_observer.py`）：裸 XHR 发的消息，另一个号在同房间（WSS 正常、实时收其他人弹幕）**收不到**。排除「仅发送页本地过滤」。
2. **切 WSS 实验**：切断直播页 WSS 后 UI 发送 HTTP 200 但不上墙；恢复 WSS 后上墙。
3. **双向顺序对照**：正向（裸XHR先）与反向（UI先隔8秒）结果一致，UI 上墙、裸XHR 不上墙。

**综合定论**：裸 HTTP 与 UI 请求在 HTTP 层（sign-type、client-data、22 query 参数、11 headers、响应字段）**完全等价**，服务端显式处理相同（都 `status_code=0`+`msg_id`），唯一区别是 UI 发送时页面 IM SDK 的**常驻 WSS 会话**向服务端注册了会话状态。广播判定 100% 依赖此会话状态，既不在 HTTP 请求也不在响应里。

### 6.3 IM SDK / frontier 协议定位（若要继续攻坚纯协议）

- 传输帧结构：`chunks/transport-schema-im.63ff9a29.js` —— `{method, payload, msg_id, msg_type, offset, need_wrds_store, wrds_version, wrds_sub_key, message_extra, tenant_id}`（字节 frontier 协议）
- 消息 protobuf schema：`chunks/live-schema-im.aa08852d.js`（各类 `Wrds*Message`）
- WSS 传输实现：`douyin_live/8818.6125bf19.js`（`e.send`）
- 纯 Python 复现需重写 IM SDK 客户端：① frontier WSS 建连握手（鉴权签名，未破解）② 维持会话（ACK+心跳）③ 发送时同步会话游标。工作量远超 a_bogus 复现，列为独立长期课题。

### 6.4 可见性门槛（v2 结论的修正）

| 场景 | `document.hidden` | 上墙 | 说明 |
|------|:-----------------:|:----:|------|
| 窗口在最前/获得焦点 | false | ✅ | — |
| **窗口最小化 / 切到别的应用** | **false**（CDP 保活） | **✅** | attach 模式 DevTools 保活渲染进程 |
| **本浏览器内切到别的标签页** | **true** | **❌** | 唯一失败态；`ensure_visible` 会尝试 JS 覆写纠正 |
| CDP 强制 `hidden=true` | true | ❌ | `test_hidden_send_v2.py` 实证 |

**结论**：`document.hidden` 才是真实门槛，不是「窗口前台可见」。无人值守时窗口可最小化，禁忌仅「浏览器内切标签页」。

---

## 7. 最终交付与无人值守指南

### 7.1 前置

1. 以调试端口启动浏览器并登录抖音：`--remote-debugging-port=9222`
2. 在该浏览器**打开目标直播间**（需存在「与大家互动」输入框）
3. 直播标签保持为**活动标签**（可最小化窗口/切到别的应用，但不要在浏览器内切到另一个标签页）

### 7.2 命令

```bash
cd server/data/reverse_runs/task_20260725_144506_2d55d021/repro
# 单发
E:\aicode\.venv\Scripts\python.exe send_danmaku_pathb.py "你好" --room <短号>
# 保活循环（{t}=时间戳尾号，防幂等拦截）
E:\aicode\.venv\Scripts\python.exe send_danmaku_pathb.py "弹幕{t}" --room <短号> --loop --interval 30
```

### 7.3 返回字段

`send()` 返回 `{ok, content, on_wall, trigger, visibility, attempts, tab_url}`；`on_wall=true` 为真上墙（以 `.webcast-chatroom___list` DOM 验收），`attempts` 为实际尝试次数（内置失败重试 1 次）。

### 7.4 可靠性边界

| 项 | 说明 |
|----|------|
| 窗口最小化/切走 | ✅ 可发（已实测多条） |
| 用别的号看同房间 | ✅ 互不影响 |
| 浏览器内切到别的标签页 | ❌ 会真 hidden，可能不上墙 |
| 发送频率 | ≥ 30s 间隔，高频触发 `20003`/验证码 |
| 登录态过期 | 需重新在调试浏览器登录 |

### 7.5 回归检查（站点升级时）

- [ ] 发送按钮选择器 `.webcast-chatroom___send-btn` 是否仍在
- [ ] 编辑器 `[contenteditable=true]` 是否仍为 Draft.js
- [ ] `__reactProps.onClick` 是否仍为发送入口
- [ ] `bd-ticket-guard-web-sign-type` 是否仍为 1
- [ ] 广播是否仍依赖活体 WSS（用 `test_broadcast_observer.py` 重验）

---

## 8. 基本信息

- **目标**：抖音 PC Web 直播弹幕发送
- **类型**：协议分析 + 浏览器自动化发送（纯协议不可行）
- **任务 ID**：`task_20260725_144506_2d55d021`
- **环境**：调试浏览器 `--remote-debugging-port=9222`；Python `E:\aicode\.venv\Scripts\python.exe`
