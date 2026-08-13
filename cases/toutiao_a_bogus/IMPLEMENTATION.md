# toutiao_a_bogus — 实现交接文档（新对话续写必读）

> **案例路径**：`cases/toutiao_a_bogus/`  
> **工具链**：crypto-hunter-lite MCP + Node 离线 + 可选浏览器 tab  
> **最后验证**：2026-07-21 — 纯本地取数 ✅。长签：**递进模型**（活体 168→172→176→180 随行为/时间），非 `me[23]` 开关；`Function.prototype.call` hook 会压短签。证据：`longsign_vm_session_evidence.json`。§8 已按现签现用修正。

---

## 给新对话 AI 的开场指令（复制粘贴）

```
继续 cases/toutiao_a_bogus 今日头条 a_bogus 纯 Node 离线复现。

请先读：
1. cases/toutiao_a_bogus/IMPLEMENTATION.md（本文）
2. cases/toutiao_a_bogus/README.md

目标：纯 Node 产出 a_bogus + msToken，供协议脚本拼装；feed 数据用浏览器 unsigned fetch。

当前状态：
- ✅ node replay_bdms_offline.js 可产出 168/172 字符 a_bogus
- ✅ sign_and_validate.js 一键流水线通过
- ⚠️ 离线 vs 浏览器 oracle 字节未完全一致（LCS≈34；首页活体锚点多为 `5f5LfY3qV`，旧样本 `5fVLfY3qV`）
- ✅ 新鲜 Node 签立刻纯 HTTP 可取 feed（`stable_local_feed.py`）；未签名/过期签 → 200 空 body

前置：后端 http://127.0.0.1:27183 + 浏览器 tab 打开 toutiao.com 文章页。

验收：node sign_and_validate.js
```

---

## 1. 目标与边界

### 1.1 要做什么

| 层级 | 目标 | 状态 |
|------|------|------|
| L1 算法定位 | bdms.js JSVMP 负责 a_bogus | ✅ 完成 |
| L2 纯 Node 签名 | 无 CDP 运行时产出 `a_bogus` + `msToken` | ✅ 完成 |
| L3 浏览器 oracle | 同 URL 离线签名 vs 页面 XHR 格式对齐 | ⚠️ 部分（LCS~33） |
| L4 服务端可用 | HTTP 请求 feed 返回 JSON | ✅ `stable_local_feed.py` 现签立刻 GET |
| L5 纯 Python HTTP | 现签立刻 GET `signed_url` | ✅（过期/缺 msToken → 空 body） |

### 1.2 不做什么（易踩坑）

- **不要**调用 `ye(url)` 或 `bdms.init(url)` 期望返回 a_bogus 字符串 → 返回 `undefined`
- **不要**用 Python/requests 重放 `signed_url` 当验收标准
- **不要**在签名前预填 `msToken`（应由 XHR hook 在 `send()` 写入）
- **不要**用 plain object 冒充 XHR（必须 `XMLHttpRequest` + `prototype`）
- **不要**在已加载页重复安装 `Function.prototype.call` hook（会栈溢出）

---

## 2. 架构（已验证）

```
页面加载
  └─ sdk-glue.js 包装 XMLHttpRequest
       └─ bdms.js (JSVMP, magic HNOJ@?RC)
            └─ bdms.init({ aid:24, pageId:6457, paths:{ include:[.../feed] } })
                 └─ hook XHR.prototype.open / send
                      └─ send 后 URL 追加 msToken + a_bogus

纯 Node 复现链：
  browser_shim.js (垫片 + ENV_OVERRIDE)
    → vm.runInContext(bdms.js)
    → bdms.init(...)
    → patchInitEnv(browser_env_snapshot.json)  // 仅槽 [0,23,24]
    → new XMLHttpRequest(); open(url); send()
    → 读 responseURL / _url 中的 a_bogus
```

**关键结论**：`set 51` 捕获的是 `bdms.init` 本身（`__abogus_sign === bdms.init`，pc=10043），不是独立签名字符串函数。

---

## 3. 文件地图

### 3.1 主路径（生产用）

| 文件 | 职责 |
|------|------|
| `replay_bdms_offline.js` | **核心**：Node 离线签名入口 |
| `browser_shim.js` | 浏览器垫片 + 标准 XHR prototype |
| `raw/bdms.js` | 算法载体（勿删） |
| `browser_env_snapshot.json` | msToken 等（`init_me[24].inner`），**会过期** |
| `browser_fingerprint.json` | ENV_OVERRIDE（navigator/screen 等） |
| `env_snapshot_util.js` | 快照刷新 / 过期检测 / live token 对比 |
| `refresh_env_snapshot.js` | CLI：刷新快照 |
| `refresh_browser_fingerprint.js` | CLI：刷新指纹 |
| `sign_abogus.py` | **Python 集成入口** |
| `sign_and_validate.js` | **一键验收流水线** |
| `fetch_feed_via_browser.py` | Python：浏览器内拿 feed JSON |

### 3.2 验收 / 调试

| 文件 | 职责 |
|------|------|
| `validate_offline_browser.js` | 离线 vs 浏览器 XHR oracle |
| `validate_browser_unsigned_fetch.js` | 服务端可用性 oracle |
| `validate_offline_feed.py` | Python 验收封装 |
| `dump_ye_env.js` | 浏览器内 dump init_me |
| `probe_init_me.js` | 探测可 patch 槽位 |
| `sign_and_validate_report.json` | 最近一次完整验收报告 |

### 3.3 证据 / 遗留（非主路径）

| 文件 | 说明 |
|------|------|
| `abogus_pairs.json` | 浏览器抓取的 input/output 配对 |
| `replay_real_abogus.js` | 旧 IIFE harness，仅调试闭包 |
| `replay_sdk_glue_offline.js` | sdk-glue 实验，未完成 |
| `replay_xhr_offline.js` | 早期 XHR 尝试，无效 |
| `early_hook_*.js` / `capture_*.js` | 浏览器取证脚本 |

---

## 4. 环境前置

### 4.1 硬性依赖

```text
Node.js          >= 18（已在 v24 验证）
Python           3.x（推荐 E:\aicode\.venv\Scripts\python.exe）
crypto-hunter    后端 127.0.0.1:27183
浏览器 tab       https://www.toutiao.com/ 文章详情页（bdms 已加载）
```

### 4.2 启动浏览器（MCP）

```python
# MCP 工具链
ch_cdp_start(url="https://www.toutiao.com/article/7664136988722790964/", capture_profile="safe_capture")
# 卡死时：capture_profile="safe_capture"，勿 full 强行注入
```

### 4.3 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `CRYPTO_HUNTER_HOST` | 127.0.0.1 | 后端地址 |
| `CRYPTO_HUNTER_PORT` | 27183 | 后端端口 |
| `SNAPSHOT_MAX_AGE_MS` | 600000 | 快照过期警告阈值（10 分钟） |
| `ABOGUS_TIMEOUT` | 90000 | bdms vm 超时 |

---

## 5. 标准工作流

### 5.1 一键（推荐）

```bash
cd cases/toutiao_a_bogus
node sign_and_validate.js
# 或指定 URL
node sign_and_validate.js "https://www.toutiao.com/api/pc/list/feed?channel_id=0&max_behot_time=$(date +%s)&offset=0&category=pc_profile_recommend&aid=24&app_name=toutiao_web"
```

流水线步骤：刷新快照 → 刷新指纹 → 离线签名 → XHR oracle → unsigned fetch。

### 5.2 分步

```bash
# 1. 检查 msToken 是否过期
node refresh_env_snapshot.js --check

# 2. 刷新环境（签名前必做）
node refresh_env_snapshot.js
node refresh_browser_fingerprint.js

# 3. 离线签名
node replay_bdms_offline.js --refresh-snapshot "<feed_url_without_a_bogus>"

# 4. 验收
node validate_offline_browser.js
node validate_browser_unsigned_fetch.js
```

### 5.3 Python 集成

```python
# 方式 A：仅要 a_bogus 参数
import sys
sys.path.insert(0, "cases/toutiao_a_bogus")
from sign_abogus import sign_feed_url, sign_abogus

result = sign_feed_url(refresh_snapshot=True)
# result["a_bogus"], result["signed_url"], result["input_url"]

# 方式 B：要 feed 数据（必须浏览器）
# python fetch_feed_via_browser.py --refresh-env
```

```python
# 方式 C：嵌入现有 requests 脚本（仅拼参，不要直接 GET signed_url）
import requests
from sign_abogus import sign_abogus

base = "https://www.toutiao.com/api/pc/list/feed?channel_id=0&..."
signed = sign_abogus(base, refresh_snapshot=True)
# ⚠️ 以下在实测中返回空 body，勿当验收：
# requests.get(signed["signed_url"], cookies=..., headers=...)
```

---

## 6. 签名 URL 规范

### 6.1 输入 URL

- **不含** `a_bogus`
- **建议不含** `msToken`（由 hook 写入；若含 `test` 占位符会被 strip）
- 必含：`aid=24`, `app_name=toutiao_web`, feed 路径参数

### 6.2 输出

`replay_bdms_offline_out.json`：

```json
{
  "input_url": "...",
  "a_bogus": "168~172 字符 base64url",
  "signed_url": "含 msToken & a_bogus",
  "abogus_len": 168,
  "init_env_patched": 2
}
```

### 6.3 a_bogus 格式

- 长度：**168**（`pc_profile_recommend`）或 **172**（部分页面/category）
- 字符集：`[A-Za-z0-9_\-/=]+`
- URL 相关锚点：优先 `5f5LfY3qV`（首页 2026-07），兼容旧 `5fVLfY3qV`；离线/浏览器应对齐其一
- 长度：离线常见 **168/172**；首页浏览器 XHR 常见 **176**（`formatOk` 已收纳）
- 环境指纹块：约 80 字符公共段，离线与浏览器仍有差异

---

## 7. msToken 生命周期

```
mssdk.bytedance.com/web/common
  └─ Response Header: x-ms-token
       ├─ bdms.init._v[2][24].inner
       └─ localStorage.xmst   ←── 纯本地种子
            └─ mstoken_cache.json（落盘，默认可复用约 24h）
```

- 活体：`me[24].inner === x-ms-token`，并写入 `localStorage.xmst`
- Node：`init` 前 `localStorage.setItem('xmst', cache)` → bdms 读入 me[24] → 签出 URL 带 msToken
- **不需要每次开浏览器**；cache 失效时再 `refresh_env_snapshot` 一次或等 mssdk 真网轮换
- 旧路径 `browser_env_snapshot.json` 仍可 `--force-snapshot` 或自动导入 cache
- 探针验收：`node probe_xmst_seed_sign.js`（HTTP success + data>0）

---

## 8. 服务端可用性（重要）

> **2026-07-21 更新**：纯本地「现签立刻 GET」已跑通；下表以实测为准。旧结论「Node/Python signed_url 必空 body」已过时（那是**过期签 / 缺 msToken / 延迟重放**场景）。

| 调用方式 | HTTP | Body | 能否验收 |
|----------|------|------|----------|
| `python stable_local_feed.py --no-refresh`（Node 现签 → 立刻 GET） | 200 | ~300KB+ JSON，`message=success` | ✅ 推荐 |
| `node replay_bdms_offline.js` 产出后立刻 HTTP（同进程/同秒） | 200 | 有数据 | ✅ |
| 浏览器 XHR/fetch **未签名** feed（页面内） | 200 | ~400KB JSON | ✅ |
| 过期 `a_bogus` / 缺 `msToken` / 隔几分钟再打旧 signed_url | 200 | **空 body** | ❌ |
| 浏览器对**已签好的** URL 再 `fetch(signed_url)`（二次携带） | 200 | 常空 | ❌ 勿作验收 |

**结论**：

1. **协议取数（推荐）** → `stable_local_feed.py --no-refresh`（`xmst` 缓存有效时无需开浏览器）
2. **验证签名格式 / oracle** → `validate_offline_browser.js`
3. **浏览器侧兜底** → `fetch_feed_via_browser.py` / unsigned XHR
4. `a_bogus` 与 `msToken` **缺一不可**；现签现用

长签对齐（Node 168 vs 活体 180）见 §10 / `longsign_branch_evidence.json`，**不影响**当前短签取数可用性。

---

## 9. 已知 Bug 与修复记录

| 问题 | 根因 | 修复 |
|------|------|------|
| Node 签名后崩溃 | bdms 异步 XHR load 回调 | `process.exit(0)` 成功后立即退出 |
| hook 不生效 | XHR stub 返回 plain object | `browser_shim.installProperXhr()` |
| ye(url) 无输出 | ye 即 bdms.init，非签名字符串 | 改 XHR 链签名 |
| msToken 错位 | 签名前预填 msToken | `resolveInputUrl` 只删 a_bogus |
| oracle 读不到 a_bogus | 同步读 responseURL | 等 XHR `onload`（Promise） |
| Python 找不到 | Windows PATH 无 python | 用 `E:\aicode\.venv\Scripts\python.exe` |
| 指纹偏差大 | 垫片 env 与真机不一致 | `browser_fingerprint.json` → LCS 13→33 |

---

## 10. 待办（按优先级）

### P0 — 集成到业务

- [ ] 在真实爬虫/协议项目中 `import sign_abogus`，封装 `get_signed_feed_url()`
- [ ] CI/定时任务：签名前自动 `refresh_snapshot`（需常驻浏览器 tab 或 headless CDP）
- [ ] 明确哪些接口只需 a_bogus、哪些还要 Cookie/`__ac_signature`

### P1 — 提高 oracle 对齐 / 长签（176+/180）

- [x] 确认长度差不是 `pageId`（首页 HTML 亦为 `pageId:6457`）
- [x] 确认 bdms ~3s 后异步 `createElement(canvas)` + webgl；垫片假 PNG/少 extensions 与短签相关
- [x] 落地 `shim_abogus_harden.js`（合法 PNG、WebGL extensions≈34、OfflineAudio、UA-CH150）+ `replay_bdms_offline` 默认等待 `ABOGUS_ENV_WAIT_MS`
- [x] **2026-07-21 深度取证（见 `longsign_branch_evidence.json` / `longsign_vm_session_evidence.json`）**：
  - 活体签长**递进**：冷启动 **168** → 鼠标/滚动后 **172** → 多轮行为 **176** → 温页曾见 **180**（raw 约 124→128→132→134）
  - **证伪**「`me[23]` 控制长/短签」：长度爬升全程 `me23` 可为 false
  - **证伪**「缺 plugins」：Node 已 `plugins.length=3`
  - **新结论**：长签是环境/行为指纹块逐步加长，不是单分支开关；`Function.prototype.call` hook 会把活体压回 168（完整性敏感）
  - Node 曾派发空壳 `MouseEvent` **未能**抬升（空 `addEventListener`）
- [x] **EventTarget 基建（方案 A）已落地并验证**：`shim_event_target.js` → bdms 挂上 `mousemove/touch*/keydown/...` 共 ~8 类行为监听；派发/喂 `me[2]` 均成功，**长度仍恒 168**（`probe_event_target_len_out.json`）
- [ ] **主攻改为方案 B**：对照 176/180 vs 168 的 raw 尾块，定位多出来的指纹字段并补环境/注入
- [ ] 避免用 `Function.prototype.call` hook 做活体长签取证；改 XHR.open 只读或 debugger 文本断点
- [ ] 可选辅助：补齐 scroll/`isTrusted`/touch 字段；`patchInitEnv` 扩展鼠标队列（`init_me[2]` 现为 `__fn`）

### P2 — 纯 HTTP

- [x] Node/Python **现签立刻 GET** 可取 feed（`stable_local_feed.py`）— 见 §8
- [ ] 可选：curl-impersonate / tls-client（当前普通 requests 已够用，非阻塞）
- [ ] 过期 signed_url 重放仍空 body（预期行为，勿当 bug）

---

## 11. 验收标准（Definition of Done）

### 最低可用（当前已达成）

```bash
node sign_and_validate.js
# sign_and_validate_report.json:
#   ok: true
#   sign.abogus_len in [168, 172]
#   oracle.compare.anchor_match: true
#   unsigned_fetch.ok: true
#   unsigned_fetch.result.message: "success"
```

### 进阶（未达成）

- [ ] `oracle.compare.exact_match: true` 或 LCS > 80
- [ ] Python `requests.get(signed_url)` 返回 `message=success`
- [ ] 无浏览器依赖的签名（snapshot 可离线缓存 >24h 仍有效）

---

## 12. 与 crypto-hunter 的协作

| 任务 | MCP 工具 |
|------|----------|
| 启动浏览器 | `ch_cdp_start` |
| 读 Cookie | `ch_page_get_cookies` |
| 页面执行 JS | `ch_page_run_js` |
| 抓包验证 | `ch_listener_start` → `ch_listener_read` |
| dump 环境 | `ch_page_run_js` + `dump_ye_env.js` |

**踩坑日志**：`docs/mcp_pitfalls.md`  
**逆向流程**：`docs/reverse_skill_bridge.md`

---

## 13. 相关案例

- `cases/toutiao_acrawler/` — `_signature` / acrawler 垫片来源（`replay_real.js`）
- `abogus_pairs.json` — 浏览器实测 3 组 input/output

---

## 14. 变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-20 | XHR prototype 修复；bdms.init 签名链跑通 |
| 2026-07-21 | msToken 不预填；验收脚本；sign_abogus.py |
| 2026-07-21 | msToken xmst 缓存；`stable_local_feed` 纯本地取数；§8 修正 |
| 2026-07-21 | 长签深度取证：证伪 me[23]/plugins；活体180 vs Node168；`longsign_branch_evidence.json` |

---

## 15. 快速排错

```bash
# 快照过期？
node refresh_env_snapshot.js --check

# bdms 未加载？
# → 浏览器 tab 需在 toutiao 文章页，非 about:blank

# 签名空 / 长度不对？
# → 检查 browser_env_snapshot.json 是否存在 me[24].inner

# 后端连不上？
curl http://127.0.0.1:27183/api/health
# 或 MCP ch_health

# oracle a_bogus_len=0？
# → validate_offline_browser.js 必须等 XHR onload，勿同步读
```
