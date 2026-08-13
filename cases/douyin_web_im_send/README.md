# 抖音 PC Web 私信发送协议复现（2026-07-25）

> 任务：`task_20260725_042005_7f84894b`  
> 目标：`POST https://imapi.douyin.com/v1/message/send`（`application/x-protobuf`）  
> 交付：三模式发送 + `--to`（昵称/抖音号）解析 + 本地 Cookie 复现  
> 运行证据目录：`server/data/reverse_runs/task_20260725_042005_7f84894b/`  
> 关联：`a_bogus` / `msToken` 复用 `task_20260723_061837_889ab753`（见 `cases/a_bogus`、`cases/douyin_comment_crawl`）  
> MCP 踩坑总表：[`docs/mcp_pitfalls.md`](../../docs/mcp_pitfalls.md) 顶部「2026-07-25 — 抖音 Web 私信」

---

## 1. 结论摘要

| 项 | 结论 |
|----|------|
| 端点 | `POST imapi.douyin.com/v1/message/send`，Body=`application/x-protobuf` |
| 消息类型 | 内层 JSON：`aweType=700` + `text` |
| 会话 ID | `0:1:{较小uid}:{较大uid}`（单聊）；改包时替换消息体 **f1** |
| `identity_security_token` | **服务端签发**；`GET passport/safe/get_identity_security_token/?scene=web_im`（只要 Cookie） |
| `hash.Gnrq...` ticket | **服务端签发**；缓存在 `localStorage['security-sdk/s_sdk_sign_data_key/web_protect']` |
| `a_bogus` / `bd-ticket-guard-*` | 对本接口**非强依赖**（本会话可通）；仍建议带上以降低画像差异 |
| `msToken` | query 常带；可从 Cookie/`xmst` 缓存/本地 mint |
| 三模式 | `browser` / `api` / `local` 均已实测 200/`OK` |
| `--to` | 昵称（私信列表）/ 抖音号（主页点私信）/ 字面 `0:1:...`；写入 `contacts_cache.json` |

**关键验证样本：**

- 昵称 api：`validation/send_api_last.json`（`--to 卫辉现代技校`，cid 切到 `0:1:76604171249:748557...`）
- 昵称 local：`validation/send_local_last.json`（contacts 缓存命中，200/OK）
- 早期 cookie-only 链：`validation/cookie_only_chain.json`

---

## 2. 实现原理（Source → Sink）

```text
目标请求 imapi /v1/message/send
  → protobuf 外壳（f1=100, f3=1.1.3, f4=hash ticket, f8=消息包…）
  → 消息包 f8 / 100：
       f1 = conversation_id（0:1:uidA:uidB）  ← 决定发给谁
       f4 = {"aweType":700,"text":"..."}
       f5/f8 = client_message_id / stime 等
  → 顶层 f15 KV：identity_security_token / fp / webid …
  → Query：msToken、a_bogus、verifyFp/fp（可选）
  → Header：Cookie +（可选）bd-ticket-guard-*
```

### 2.1 改包策略（不是从零组包）

1. 抓一条**活体** `message/send` 作为模板：`requests/message_send_body.bin`
2. `im_protobuf.rebuild_send_body` 只刷新：
   - 正文 text
   - `client_message_id`（UUID）
   - `s:stime`
   - `identity_security_token`
   - `hash` ticket（可选）
   - **`conversation_id`（可选，按 `--to` 解析结果写入）**
3. 用 sdenv `sign_a_bogus` 签 URL，再 `http_post_send`

### 2.2 identity / ticket 来源

| 材料 | 刷新方式 | 是否必须浏览器 |
|------|----------|:--------------:|
| Cookie | 登录态导出 | 首次要 |
| `identity_security_token` | Passport HTTP，仅 Cookie | 否 |
| hash ticket | localStorage web_protect / 模板 f4 / `--export-materials` | 导出时要 |
| `msToken`/`fp`/`ua` | 缓存或 Cookie | 否（可降级） |
| `bd-ticket-guard-*` | 页内 `securitySDK.secureProxy.getBdTicketGuardHeader` | 导出时要 |

### 2.3 `--to` 解析链路

```text
--to 输入
  ├─ 已是 0:1:uid:uid → 直接用
  ├─ contacts_cache 命中 → 用缓存 conversation_id（local 无浏览器）
  ├─ 像抖音号（无中文、字母数字._-）
  │     → 打开 /user/{unique_id} → 点「私信」
  │     → 从发送按钮 React fiber 的 imStore.curConversationId 读取
  └─ 否则当昵称关键词
        → 打开私信面板 → 点匹配会话 → 读 curConversationId
```

读当前会话 ID 的可靠方式（已验证）：

```js
// .e2e-send-msg-btn → __reactFiber* → memoizedProps.imStore.curConversationId
```

实测：

| 目标 | conversation_id |
|------|-----------------|
| 达人-脱飘甄选 | `0:1:4180764687073364:7485574577269277756` |
| 卫辉现代技校免费技能培训基地 | `0:1:76604171249:7485574577269277756` |
| 当前登录 uid（myself） | `7485574577269277756` |

---

## 3. 三模式说明

| 模式 | 浏览器 | 行为 | 适用 |
|------|:------:|------|------|
| **browser** | 要（自动化） | CDP 拟人 `Input.insertText` + 点发送；走完整页面 SDK | 最像真人、风控压力相对小 |
| **api** | 要（取材料） | 浏览器取 Cookie/token/ticket/guard → Python POST | 稳协议 + 少 DOM |
| **local** | **不要** | Cookie + 材料缓存 + Passport 刷新 identity + sdenv 签 → POST | 批量/无人值守（需先缓存联系人） |

### 用法

```bash
cd server/data/reverse_runs/task_20260725_042005_7f84894b/repro

# 浏览器自动化（按昵称）
E:\aicode\.venv\Scripts\python.exe send_im_message.py "你好" --mode browser --to 卫辉现代技校

# API（调试浏览器开着）
E:\aicode\.venv\Scripts\python.exe send_im_message.py "你好" --mode api --to 卫辉现代技校

# 导出材料 / 联系人（给 local 用）
E:\aicode\.venv\Scripts\python.exe send_im_message.py --export-materials --to 卫辉现代技校
E:\aicode\.venv\Scripts\python.exe send_im_message.py --export-contacts --to 卫辉现代技校

# 纯本地
E:\aicode\.venv\Scripts\python.exe send_im_message.py "你好" --mode local --to 卫辉现代技校 ^
  --cookie-file ../runtime_scopes/cookie_only.txt
```

`--conv` 仍可用，语义等同昵称关键词（兼容旧调用）。

---

## 4. 文件地图

| 路径 | 用途 |
|------|------|
| `repro/send_im_message.py` | CLI 入口（三模式 + `--to`） |
| `repro/im_cdp.py` | Edge CDP attach / 拟人输入点击 |
| `repro/im_protobuf.py` | protobuf 改包（含 conversation_id） |
| `repro/im_resolve.py` | 昵称/抖音号 → conversation_id + contacts 缓存 |
| `repro/replay_message_send.py` | 早期改包/依赖消融实验 |
| `requests/message_send_body.bin` | 活体 protobuf 模板 |
| `runtime_scopes/materials_cache.json` | ticket/xmst/cookie/guard/identity |
| `runtime_scopes/contacts_cache.json` | `--to` → conversation_id 映射 |
| `runtime_scopes/cookie_only.txt` | 仅 Cookie（敏感，勿提交） |
| `runtime_scopes/message_send_pb.json` | 模板结构解析 |
| `validation/send_*_last.json` | 最近一次各模式结果 |

签名依赖（仓库内另一任务）：

`server/data/reverse_runs/task_20260723_061837_889ab753/repro/sdenv_local_sign.py`

---

## 5. 踩坑记录（误判 → 真实原因 → 信号 → 修复 → 规则）

### 坑 1：以为只要 Cookie 改 text 就能随便换人发

- **误判**：模板改字就能发给任意会话。  
- **真实原因**：收件人由 protobuf **消息体 f1 = conversation_id** 决定；不换 cid 会一直发到模板原会话（如「脱飘」）。  
- **信号**：UI 里消息出现在错误会话；或 meta 里 `old_conversation_id` 未变。  
- **修复**：`--to` 解析后 `rebuild_send_body(..., conversation_id=...)`。  
- **规则**：换人必换 `0:1:...`；local 必须 contacts 命中或字面 cid。

### 坑 2：`Network.getRequestPostData` 落盘成 base64 文本

- **误判**：模板文件开头是 `CGQQ...` 当二进制用，改包全挂。  
- **真实原因**：CDP 偶发把 body 以 base64 字符串返回并被当 latin1 写入。  
- **信号**：文件不以 `\x08d` 开头，且 `b"hash."` 也不在前缀。  
- **修复**：`as_bytes_maybe_b64()`；合法模板应接近 `\x08d` + 含 `hash.`。  
- **规则**：读模板先校验魔数/特征，再改包。

### 坑 3：page_xhr / 误用 tea `webid` → `SEND_MESSAGE_STATUS_INVALID_PARAM`

- **误判**：随便塞设备/webid 字段。  
- **真实原因**：identity 相关 device_id / webid 与 token 体系不一致会判非法参数。  
- **信号**：响应业务错误码 INVALID_PARAM，非 HTTP 4xx。  
- **修复**：webid 用 Passport 返回的 `identity_device_id`；坏模板重新 browser 活体抓。  
- **规则**：身份字段跟 identity_token 同源刷新。

### 坑 4：`identity_security_token` / hash ticket 当成本地可算签名

- **误判**：像 `a_bogus` 一样本地算法生成。  
- **真实原因**：二者均为**服务端签发票据**；ticket 落在 web_protect localStorage。  
- **信号**：localStorage 有 `hash.Gnrq...`；Passport 可刷新 identity。  
- **修复**：Cookie HTTP 刷 identity；ticket 从缓存/模板/export。  
- **规则**：分清「本地可签」与「服务端票据」。

### 坑 5：纯 HTTP（Python urllib）解析抖音号 / 搜用户失败

- **误判**：带 Cookie GET `/user/{unique_id}` 或 search API 就能拿 uid。  
- **真实原因**：服务端返回 `_$jsvmprt` 反爬壳 / `UserId不合法` / 空 `user_list`；无浏览器指纹。  
- **信号**：HTML 几乎空 body + jsvm；API `status_code=2`。  
- **修复**：解析必须走**已登录 CDP 页**：列表点选或主页点「私信」。  
- **规则**：用户解析禁止裸 HTTP；结果写入 `contacts_cache.json` 供 local。

### 坑 6：`openImConversation` 不是按昵称开会话

- **误判**：`openImConversation("卫辉...")` 或 `{unique_id:...}` 能开聊。  
- **真实原因**：源码是 `setConfig(IMStatusStore,{conversationId:e})`，参数必须是 **cid 字符串**。  
- **信号**：调用「成功」但 UI/cid 不变。  
- **修复**：先解析出 `0:1:...` 再 open / 改包。  
- **规则**：先 cid，后 open。

### 坑 7：React fiber 扫 conversation-item 拿不到 props

- **误判**：列表 DOM 上一定有 conversationId。  
- **真实原因**：当前构建列表项 fiber 链无可用 cid；真正 cid 在**发送按钮** imStore。  
- **信号**：`fiber: []`；点开会话后 send-btn 可读。  
- **修复**：点会话 → 读 `.e2e-send-msg-btn` imStore。  
- **规则**：取 cid 盯发送按钮 store，别死磕列表项。

### 坑 8：抖音号与昵称搞混 / 打开自己的主页

- **误判**：`A15670585218` 一定是对方账号。  
- **真实原因**：该号在本会话探测中打开后像是**当前登录号**（昵称「哈哈11」、uid=myself）。  
- **信号**：`/user/{id}` 的 RENDER_DATA 只有 myself uid。  
- **修复**：发「卫辉…」用昵称 `--to 卫辉现代技校`；抖音号必须先确认是对方 unique_id。  
- **规则**：`--to` 抖音号先人工确认，再写入 contacts。

### 坑 9：高频自动化 / 裸 Cookie 打接口 → 页面弹出验证码

- **误判**：以为注入了「强制验证码脚本」。  
- **真实原因**：平台风控——CDP 连点、短时间多次 imapi 发送、浏览器外带 Cookie 打 search/profile，画像异常。  
- **信号**：网页突然要过滑块/验证；并非 `final_capture` 逻辑写入验证码。  
- **修复**：降频；优先 `browser`；少用裸 HTTP；验证出现后人工通过并暂停自动化。  
- **规则**：协议复现测试要控频率；验证码当风控信号，不当注入故障。

### 坑 10：`ch_page_run_js` / 后端超时与 live 标签页卡顿

- **误判**：MCP 整体挂了。  
- **真实原因**：标签停在重页面（如 live）或 full 注入过重；评估超时。  
- **信号**：`timed out` / `backend_available=false`。  
- **修复**：`capture_profile=safe_capture`；直连 `ImCdp` 选 `douyin.com` 标签；必要时换干净标签。  
- **规则**：页面卡死先降级 safe_capture，勿 full 硬刚。

### 坑 11：同 `client_message_id` 重放显示 OK 但不产生新消息

- **误判**：以为发送失败。  
- **真实原因**：幂等：同一 cid 重放返回 OK。  
- **信号**：HTTP 200/OK 但 UI 无新气泡。  
- **修复**：每次改包生成新 UUID。  
- **规则**：验证「真送达」看 UI/新 message id，不单看 OK。

---

## 6. 风控与安全说明

1. `final_capture.user.js` / `safe_capture` 是采集 Hook，**不会主动下发验证码**。  
2. 验证码来自抖音风控策略，与异常频率、环境不一致强相关。  
3. `materials_cache.json` / `cookie_only.txt` / contacts 含登录态，**禁止提交 Git**。  
4. 本案例仅用于本人账号下的协议分析与复现验证，勿用于骚扰/群发。

---

## 7. 可复用规则（给下次）

1. 私信换人 = 换 `conversation_id`，不是换 Cookie 账号名。  
2. 服务端票据（identity/ticket）与本地签（a_bogus）分开处理。  
3. 用户解析走 CDP；结果落 contacts，local 只读缓存。  
4. 模板先校验二进制特征，再改包。  
5. 验证闭环：`HTTP OK` + UI/会话正确 + 多样本（不同 text/cid）。  
6. 风控抬头：降频、改 browser、停裸 HTTP。

---

## 8. 回归检查清单

站点升级时优先核对：

- [ ] `imapi.douyin.com/v1/message/send` 是否仍 protobuf + aweType 700  
- [ ] 会话 ID 是否仍 `0:1:lo:hi`  
- [ ] Passport `get_identity_security_token` scene=`web_im` 是否可用  
- [ ] web_protect localStorage 路径是否变更  
- [ ] 发送按钮 class / `imStore.curConversationId` 是否仍可从 fiber 读取  
- [ ] `data-e2e="conversation-item"|"im-entry"|"msg-input"` 是否仍存在  

---

## 9. 基本信息（模板字段）

- **目标名称**：抖音 PC Web 私信发送  
- **目标类型**：协议复现（protobuf + 票据 + 可选 a_bogus）  
- **日期**：2026-07-25  
- **任务 ID**：`task_20260725_042005_7f84894b`  
- **环境**：Edge `--remote-debugging-port=9222`；后端 `127.0.0.1:27183`；Python `E:\aicode\.venv\Scripts\python.exe`；CDP `safe_capture`
