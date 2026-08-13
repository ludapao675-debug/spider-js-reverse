# 快手 PC 直播弹幕（WebSocket 推送）逆向（2026-08-02）

> 任务类型：JS 加密参数逆向 + 协议复现（弹幕拉取，非发送）
> 目标直播间：`https://live.kuaishou.com/u/3xdw2ep3jh6k9y4`（示例）
> 环境：调试浏览器 `--remote-debugging-port=9222`（attach 模式接管）
> Python：`E:\aicode\.venv\Scripts\python.exe`

---

## 0. 核心结论（实证）

快手 PC 直播**弹幕不是 HTTP 轮询接口**，而是 **protobuf over WebSocket 长连接推送**。

完整链路：

```
HTTP  GET live.kuaishou.com/live_api/liveroom/websocketinfo
        ?caver=2&liveStreamId=<内部ID>   （游客态 __NS_hxfalcon 签名非强制）
      → { data: { token, websocketUrls: [wss://...] } }

WS    连 websocketUrls[0] → 发 SocketMessage{ payloadType=200(CS_ENTER_ROOM),
        payload=CSWebEnterRoom{token, liveStreamId, ...} }
      → 收 SocketMessage{ payloadType=SC_WEB_ENTER_ROOM_ACK } + 持续
        SocketMessage{ payloadType=829(SC_COMMENT_ZONE_RICH_TEXT) / SC_COMMENT }
        → 内层 WebCommentFeed{ id, user, content, ... }
```

**关键修正（实测）**：`websocketinfo` 接口**强制校验** `__NS_hxfalcon` 签名。
- 页面真实请求带完整 `HUDR_...$HE_...` 签名 → 返回 `result:1` + `token`。
- 裸 fetch（不带签名）→ 返回 `result:2`（参数错误/签名缺失）。
- 早期"裸 fetch 返回 token"为误判（命中缓存或混记）。
→ 弹幕拉取**无法纯 Python 独立复现**，必须生成有效 HUDR 签名。

---

## 1. 参数逆向

| 参数 | 来源 | 可逆性 |
|------|------|:------:|
| `liveStreamId` | 直播间短号（`3xdw2ep3jh6k9y4`）→ 页面/接口映射的内部 ID（如 `ySbf5SizaMY`） | ✅ 可从页面或 HTTP 响应取 |
| `caver` | 固定 `2`（签名算法版本） | ✅ 常量 |
| `__NS_hxfalcon` | HUDR/SIG4 双重段签名（`$HE_`=BLAKE2s+CTS+异或拼接；`HUDR_`=ChaCha 变体加密载荷），**纯算法可复现**（社区已有开源实现 amagi） | ❌ 接口强制校验 |
| `token` | `websocketinfo` 响应返回（动态，每次进房不同） | ✅ 接口返回 |
| `websocketUrls` | 同上 | ✅ 接口返回 |

### 1.1 `__NS_hxfalcon` 签名定位与算法还原（已定位 · 已破解 · 纯算法可复现）

> ⚠️ **结论修正（2026-08-02 网络深度搜索后）**：此前判断"算法在 HUDR 原生 realm、纯本地不可复现"是**误判**。
> 根因：`$encode` 的真实实现是 `this.realm.global["$encode"]`，HUDR 的 `prototype.call` 只是把调用转发给 realm；
> 但 realm 里注入的 `<script>` 本身包含的就是**纯 JS 算法**（ChaCha/BLAKE2s/LFSR），并非 native 代码。
> 社区已完整纯算法还原——开源库 `ikenxuan/amagi` 提供了 TypeScript 实现，CSDN 也有纯 Python 还原。

- 签名函数：`app.*.js` 内 `h(a)`，`a = {url, query:{caver}, form:{}, requestBody:{}}`
- 调用：`f.I.call("$encode", [t, {suc: e=>e({signResult, signInput}), err}])`
- `__NS_hxfalcon` 由两段拼接：`HUDR_<base64url>$HE_<hex>`
- **`$HE_` 段算法**（纯 JS，常量全公开，`primitives.ts` / `he.ts`）：
  1. `hashField = xor( hexToBytes( b2sa(signInput+"HUDR_"+hudrBody)[:8] ), [45,211,69,192] )`
  2. `b2sa = utf8Bytes( blake2s( input ) )`（BLAKE2s 变体，IV/SIGMA 固定）
  3. `cts`：LFSR 状态机，种子 `'Vuz4fCHxn1CO'`，逐字节 `value ^ (result+3)` 变换
  4. preHex 拼接：`4B54` + `cda9` + `ab` + startupRandom(LE6) + random48(LE6) + `0100000001` + (count^3131873467)(LE4) + hashField + (timestamp^3360347992n)(LE6) + `9b563eda7b563e` + LRC
  5. `finalHex = transformKuaishouHeHex(preHex, LRC(preHex))`（末字节为 key 流式异或）
- **`HUDR_` 段算法**（纯 JS，`hudr.ts`）：
  1. 载荷：`[45,61,0,2]` + infoCache(`[68,0]+scriptCount LE4`) + `[112,0]+count LE4` + `[114,1]+len LE2+SECS.s码点数组` + `[115,0]+secsCount LE4`
  2. 每字节异或 `0x23`
  3. **ChaCha 变体加密**：key=`[4183807412,394484062,1106561997,2378328696,630790222,2546784104,2891127470,1922531795]`，nonce=`[2215853858,1643070585,1849059804]`，20 轮 quarterRound
  4. Base64URL 编码（`+/=` → `-_.`）
- **SECS.s**：`window.SECS.s`，本质是**调用栈尾巴字符串**（非固定值），由 HUDR 注入时 `new Error().stack` 截取；复现时可用占位/真实栈尾巴。
- **复现可行性**：全部为纯 JS 常量 + 标准算法（BLAKE2s/ChaCha/LFSR），**纯 Python 可完整复现**，无需浏览器、无需原生桥。
- 参考实现：`https://github.com/ikenxuan/amagi`（`packages/core/src/platform/kuaishou/sign/` 下 `he.ts`/`hudr.ts`/`primitives.ts`/`state.ts`/`helpers.ts`）。

---

## 2. WebSocket 协议（protobufjs 编译产物）

快手 WS 帧为**两层 protobuf 包装**：

### 2.1 外层 `SocketMessage`（script 1251，`liveRoom.*.js` 依赖）

```protobuf
message SocketMessage {
  int32  payloadType = 1;   // varint，消息类型
  bytes  payload     = 2;   // length-delimited，内层消息二进制
}
```

`payloadType` 映射（script 1251 实测）：

| 名称 | 值 | 方向 |
|------|:---:|------|
| `CS_ENTER_ROOM` | 200 | C→S 进房订阅 |
| `SC_WEB_ENTER_ROOM_ACK` | (见 1251 表) | S→C 进房确认 |
| `SC_COMMENT` / `SC_COMMENT_ZONE_RICH_TEXT` | 829 等 | S→C 弹幕推送 |

### 2.2 内层 `CSWebEnterRoom`（script 1242-1246，进房请求）

```protobuf
message CSWebEnterRoom {
  string token          = 1;
  string liveStreamId   = 2;
  uint32 reconnectCount = 3;
  uint32 lastErrorCode  = 4;
  string expTag         = 5;
  string attach         = 6;
  string pageId         = 7;
}
```

业务代码实际发送（`liveRoom.*.js`）：

```js
f({ type: "CS_ENTER_ROOM",
    payload: { liveStreamId: i, token: o,
               pageId: Q().session.get("kslive.log.page_id") } })
```

### 2.3 内层 `WebCommentFeed`（script 1204-1225，弹幕消息）

```protobuf
message WebCommentFeed {
  string id         = 1;
  WebCommentUser user = 2;   // 含用户信息（昵称/头像等）
  string content    = 3;     // ★ 弹幕文本
  string deviceHash = ...;
  SenderState senderState = 7;
  ...
}
```

弹幕文本 = `WebCommentFeed.content`（field 3）。

---

## 3.5 密钥/加密字段下发审计（实测结论）

**用户质疑**：是否还有其他请求返回了加密字段或密钥，可用于本地复现？

**审计方法**：监听器抓全量直播页请求（154 条 / 277KB dump），对全部响应体做密钥类字段扫描。

**结论：没有任何接口下发密钥或加密字段。**

- 扫描关键词：`secret / secretKey / publicKey / encryptKey / privateKey / aesKey / rsaKey / encrypt / cipher / iv / salt / nonce / hmac / decrypt` —— 响应体命中 **0 条**。
- 全部 `live_api` 接口（`classify` / `simple` / `interestMask/list` / `emoji/gift-list` / `liveroom/reco` / `baseuser/userLogout` / `liveroom/recall` / `liveroom/websocketinfo`）响应均为业务数据，**无密钥常量**。
- `websocketinfo` 响应实测为 `{result:1, token, websocketUrls}` —— `token` 仅是 WS 连接凭证（动态，每次进房不同），**非签名密钥**。
- app.js bundle 内 `secret / secretKey / publicKey / secret` 等关键词字数 **0** —— 签名密钥**不以字符串常量形式存在于前端 bundle**，而是硬编码为 ChaCha key/nonce、BLAKE2s IV、各 XOR 掩码等**数值常量**（见 1.1 节），由 HUDR 注入脚本携带。

**推论**：快手 PC 直播的 HUDR 签名**无接口下发密钥**——所有算法参数均为前端硬编码常量（社区已提取完整）。因此纯本地算法复现**有完整入口**（参考 amagi 实现）。"无接口下发密钥"≠"不可本地复现"，二者不矛盾：密钥不是传输得来，而是逆向提取的硬编码常量。

---

## 3. Source → Sink

```text
直播间页面加载
  → 业务调用 P.uZ({liveStreamId})  （liveRoom.*.js）
  → HTTP GET /live_api/liveroom/websocketinfo?caver=2&liveStreamId=...&__NS_hxfalcon=...
  → 响应 { token, websocketUrls }
  → new WebSocket(websocketUrls[0])
  → WS.send( SocketMessage{200, CSWebEnterRoom{token, liveStreamId}} )
  → WS.onmessage: SocketMessage{829, WebCommentFeed{content}}  ← 弹幕
```

---

## 4. 本地复现脚本（协议级骨架）

`repro_kuaishou_danmu.py`：Python（websocket-client + 手写 protobuf wire format），
实现了 WS 连接 + 进房帧编码 + 弹幕解码的完整协议栈。

```bash
E:\aicode\.venv\Scripts\python.exe repro_kuaishou_danmu.py --room 3xdw2ep3jh6k9y4 --lsid ySbf5SizaMY --count 20
```

流程：
1. `fetch_websocketinfo()`：GET `websocketinfo`（**需带有效 `__NS_hxfalcon` 签名**，否则返回 `result:2`）。
2. `encode_socket_message()`：手写 protobuf 编码 `SocketMessage{200, CSWebEnterRoom}`。
3. 连 WS，发进房帧，监听 `onmessage`，对 `payloadType∈弹幕类` 的帧解码 `WebCommentFeed.content`。
4. 心跳保活（快手 WS 需定期发心跳帧，否则断连）。

> ✅ **复现边界（实测 + 社区验证）**：`__NS_hxfalcon` **纯算法可本地生成**（社区已有完整开源实现）。
> - ✅ "本地生成的肯定可以复现" —— **成立**。算法本体是纯 JS（BLAKE2s + CTS/LFSR + ChaCha 变体 + 异或拼接），密钥/常量硬编码在 HUDR 注入脚本里（ChaCha key/nonce、BLAKE2s IV、XOR 掩码均已公开）。
> - ✅ 没有任何接口下发密钥/加密种子（见 3.5 节审计）——密钥来自逆向提取的硬编码常量，非传输获得。
> - ✅ 可行路径：**纯 Python 实现签名算法**（参考 amagi 的 `he.ts`/`hudr.ts`/`primitives.ts`），无需浏览器、无需原生桥。
> - 脚本可作为"签名已解决后"的弹幕拉取骨架（WS 连接 + protobuf 编解码已完整实现）；下一步是把签名算法补进 `fetch_websocketinfo()`。

> 注：外层 `SocketMessage.payloadType=1 / payload=2` 为快手标准结构；若实测握手失败，
> 优先排查 WS 握手是否需带特定 header/子协议（快手 WS 通常 Accept 任意 Origin）。

---

## 5. 踩坑

| 误判 | 真实情况 |
|------|----------|
| 弹幕是 HTTP 轮询接口 | 否，纯 WebSocket 推送（无 `/rest/.../commentList` 之类接口） |
| `__NS_hxfalcon` 游客态不校验 | 实测强制校验：裸 fetch 返回 `result:2`，必须带有效 HUDR 签名 |
| 快手签名走 Web Crypto | 否，HUDR 走自研纯 JS 算法（BLAKE2s + CTS/LFSR + ChaCha 变体），主线程 `window.crypto.subtle` 无调用 |
| 主线程可枚举 WebSocket | 否，WS 挂在 Vue/模块闭包内，`window` 上无实例 |
| `$encode` 文本断点能定位业务签名 | 否，`$encode` 在通用 uuid/crypto 库也出现，断点误命中框架层（AGENTS.md 警示的"框架层迷路"）；且残留断点会导致 `tab_connected:false`、JS 注入通道失效 |
| `__NS_hxfalcon` 在 HUDR 原生层不可本地复现 | 误判。算法是纯 JS（ChaCha/BLAKE2s/LFSR 硬编码常量），社区 amagi 已纯算法还原，`window.Jose`/`$encode` 暴露为 `undefined` 只是闭包封装，不代表原生层 |
| 其他接口下发密钥/加密种子 | 否，154 条请求审计：响应体密钥类字段命中 0，`websocketinfo` 仅返回 token（WS 凭证非密钥）；密钥实为前端硬编码常量（ChaCha key/nonce 等），非接口下发 |

---

## 6. 遗留 / 边界

- **发送弹幕**：快手弹幕**发送**大概率走独立签名/鉴权（需登录态 + HUDR 签名），纯协议可行性待验证（参考 douyin_web_live_chat 的"广播需活体会话"结论，快手可能同理）。
- **WS 握手细节**：外层 `SocketMessage` 的 field number（1/2）基于快手标准结构推断，已写进脚本；若连不通优先排查握手 Query/header。
- **心跳帧结构**：`CS_HEARTBEAT` 的 payloadType 与内容需从 `liveRoom.*.js` 动态确认（脚本内置占位心跳，可按需补）。
- **登录态弹幕**：登录后 `websocketinfo` 可能启用 `__NS_hxfalcon` 强校验，届时需复用浏览器原生 `$encode`（保活浏览器方案）。

---

## 7. 基本信息

- 目标：快手 PC Web 直播弹幕**拉取**（WebSocket 推送）
- 类型：协议分析 + 纯 Python 本地复现（游客态）
- 日期：2026-08-02
- 归档依据：本目录仅保留 `README.md`（逆向结果与证据归档）；过程脚本 `kuaishou_hxfalcon.py`、`repro_kuaishou_danmu.py` 已于 2026-08-03 按用户要求删除（属逆向过程的测试文件，非最终交付物）。

---

## 8. 最终逆向结论（2026-08-03 收尾）

### 8.1 已攻克（实证闭环）

1. **`__NS_hxfalcon` 纯算法可本地复现（result:1 验证通过）**
   - 推翻最初"原生层不可复现"的误判——算法本体是纯 JS（BLAKE2s 变体 + CTS/LFSR + ChaCha20 变体 + 异或拼接），所有密钥/常量硬编码在前端注入脚本（ChaCha key/nonce、BLAKE2s IV、XOR 掩码均已公开）。
   - 纯 Python 实现见删除前的 `kuaishou_hxfalcon.py`，关键函数：`generate_hxfalcon` / `build_sign_input` / `sign_live_api_url` / `build_sign_headers`。
   - 验证：用真实 `kwfv1` cookie + 格式化 JS 栈 `SECS.s` 占位串，实战请求 `websocketinfo` 返回 `result:1`（签名校验通过）。

2. **`kww` 是第二个必带签名头（缺则 result:2）**
   - 快手 `live_api` 强制要求 `__NS_hxfalcon` + `kww` 双签名头。
   - 纯本地复现路径：直接复用浏览器 cookie 中的 `kwfv1`（作为 kww 值）；匿名路径为 AES-128-CBC（key=IV=`K8wm5PvY9nX7qJc2`，加密 `时间戳|随机串` + `###ssrd`）。

3. **没有任何接口下发密钥/加密种子**
   - 154 条直播页请求响应体密钥类字段扫描 **0 命中**；`websocketinfo` 仅返回 `token`（WS 凭证，非签名密钥）。
   - 密钥全部来自逆向提取的前端硬编码常量（见 1.1 节），与"无接口下发密钥"不矛盾。

4. **WebSocket 协议结构已厘清**
   - 外层 `SocketMessage`：**field1=payloadType(int32)，field3=payload(bytes)**（由真实心跳帧 `08 01 1A 07 08 C9 F1 CB 9A FC 33` 证实：`1A` = field3<<3|2）。
   - 进房帧 `CS_ENTER_ROOM` payloadType=200；弹幕推送 `WebCommentFeed` payloadType=829。
   - 内层 `WebCommentFeed`：field1=id、field3=content（弹幕文本）。

### 8.2 已攻克（2026-08-03 端到端闭环成功）

**完整链路已全部打通，实测成功拉取弹幕文本。** 关键突破按时间顺序：

1. **进房帧二进制捕获**：`ch_page_inject_early` 注入 `WebSocket.prototype.send` hook（`run_on_new_document=true`），导航到新直播间时 hook 先于页面脚本执行，捕获 `payloadType=200` 进房帧完整字节。
2. **编码逐字节比对 PASS**：Python 编码与浏览器真实进房帧 100% 一致（270 字节），证明 protobuf 编码正确。`CSWebEnterRoom` 包含 **field 7=pageId**（原代码遗漏）。pageId 格式 `<random>_UHI_<timestamp>` 或 `<random>_<timestamp>`。
3. **断连根因 = TLS 指纹**：对照实验（空连接存活/发任意帧即断）+ `curl_cffi`（Chrome TLS impersonation）成功，而 Python `websocket-client` 失败，定位到快手对 WS 做 **TLS/JA3 指纹校验**。**必须用 `curl_cffi.Session(impersonate="chrome")`**。
4. **签名可复用**：`__NS_hxfalcon` 非一次性 nonce，浏览器签名可直接复用请求 `websocketinfo`（result:1）。HUDR 段跨房间恒定，仅 `$HE_` 段随 URL+时间戳变化。
5. **token 确定性**：token 由 did+房间推导（同 did 同房间恒同 token），浏览器与 Python 可共存（多端同 token 不互踢）。
6. **payload 需 gzip 解压**：服务端推送 payload 是应用层 gzip 压缩（`1f 8b` 开头），解压后再解 protobuf。
7. **829 真实结构修正**：弹幕文本实际在 `f1.f7.f1.f1`（README 旧推断的 `WebCommentFeed.f3` 是脚本静态推断，与运行时不符）。
8. **liveStreamId 提取坑**：必须取 `__INITIAL_STATE__.liveroom.playList[0].liveStream.id`（当前开播会话）；页面其它位置的 `liveStreamId` 是推荐位/旧会话，用错后进房只能收到点赞/在线帧、收不到弹幕。
9. **全弹幕帧类型**：829=文本评论、310=礼物（含弹幕文本）、340=进场/用户列表、101=在线人数、510=点赞、300=进房 ACK。主脚本已全部解码输出。

### 8.3 最终工作流（完全本地化，已验证）

**只需一个参数（直播间短号），其余全自动：**

```bash
python kuaishou_live_danmu.py --room nezha6969 --count 15 --timeout 45
```

自动化链路（均无需手工干预）：
1. **Cookie**：`kuaishou_cookie_manager.py` 优先读本地缓存 `kuaishou_cookies.json`，缺失时才从已连接浏览器一次性采集（含 kwfv1）。
2. **liveStreamId**：`resolve_lsid()` 纯 HTTP 拉直播间页面，解析 `__INITIAL_STATE__.liveroom.playList[0].liveStream.id`。
3. **签名**：`kuaishou_hxfalcon.py` 纯 Python 生成 `__NS_hxfalcon`（kww=kwfv1）。
4. **token**：`fetch_websocketinfo()` 用 curl_cffi（Chrome TLS）请求，`result=1` 拿 token + ws_url。
5. **进房拉弹幕**：`DanmuCapture.run()` 连 WS、发进房帧、心跳保活，解码 829/310/340 全类型。

**实测输出（御御直播间，45s）**：抓到进场昵称、礼物、文本弹幕等 15 条，如「别信他们的话不要肝神卡，要肝面码」「主播，下次不能出斯凯吗」。

### 8.4 进房帧二进制解析

```
08 C8 01         # field 1 (payloadType) = 200 (CS_ENTER_ROOM)
1A F0 01         # field 3 (payload) = 240 bytes

# CSWebEnterRoom 内层:
0A C0 01 <token> # field 1: token (192 bytes)
12 0B <lsid>     # field 2: liveStreamId (11 bytes)
3A 1E <pageId>   # field 7: pageId (30 bytes) ← 关键字段
```

### 8.5 829 弹幕帧结构（gzip 解压后，实测）

```
f1: zone 消息
  f1(str) = 房间会话 ID（<lsid>_<timestamp>）
  f7: 消息容器
    f1 (repeated): 单条消息
      f1(str) = ★ 弹幕文本
      f2(msg) = 用户信息（f1=user_id）
```

### 8.6 __NS_hxfalcon 纯 Python 本地复现（2026-08-03 完成）

**签名算法已完全本地复现，不再依赖浏览器**。实现：`kuaishou_hxfalcon.py`（移植自开源 amagi，逐环节验证）。

**算法结构**：`HUDR_<base64url>$HE_<hex>`
- **HUDR 段**：载荷 `[45,61,0,2] + infoCache(scriptCount) + count + SECS.s(栈尾100字符) + secsCount` → 逐字节 XOR 0x23 → ChaCha20 变体（key/nonce 硬编码，counter 从 1 起，非标准常量）→ Base64URL（`+/=` → `-_.`）
- **$HE 段**：`hashField = xor(cts(b2sa(signInput + "HUDR_" + hudrBody))[:4], [45,211,69,192])`；b2sa = BLAKE2s 变体（定制 IV，hash[0]^=0x01010120）；cts = LFSR 流变换（种子 `Vuz4fCHxn1CO`）；preHex = 固定头 + startupRandom(LE6) + random48(LE6) + count^3131873467(LE4) + hashField + timestamp^3360347992(LE6) + 固定尾 + LRC；最终末字节为 key 流式异或
- **signInput**：`pathname + sorted("key=value") 直接拼接`（排除含 `__NS` 的 key，无分隔符）
- **kww**：有 kwfv1 直接复用；无则 AES-128-CBC(key=IV=`K8wm5PvY9nX7qJc2`) 加密 `时间戳|8位随机` + `###ssrd`

**验证结果**：
- 本地生成签名与浏览器捕获签名结构一致（HUDR 段首尾字节高度吻合，长度完全一致）
- 线上实测：连续 3 次签名请求 `websocketinfo` 全部 `result=1`（count 递增 101/102/103 均通过）
- 全链路：纯 Python 签名 → token → WS 进房 → 弹幕拉取 ✓

**使用方式（仅需 Cookie，完全无浏览器）**：
```python
from kuaishou_live_danmu import fetch_websocketinfo, DanmuCapture
info = fetch_websocketinfo(room, lsid, cookie="did=...; kwfv1=...")  # 签名自动生成
cap = DanmuCapture(room, lsid, info["token"], info["websocketUrls"][0], cookie=cookie)
danmu = cap.run(count=20, timeout=30)
```

### 8.7 仍存在的限制

- **Cookie 依赖**：仍需浏览器的一次性 Cookie（did/kwfv1）作为访客身份；纯匿名路径（自造 did + AES kww）返回 `result=400002`（did 需与指纹记录匹配）。
- **依赖包**：`pip install curl_cffi`（必须，提供 Chrome TLS 指纹）；匿名 kww 需 `cryptography`（可选）。
- **SECS.s 栈尾**：本地构造的伪栈尾已被服务端接受（不验证具体内容），若未来服务端收紧校验需从真实浏览器提取。

