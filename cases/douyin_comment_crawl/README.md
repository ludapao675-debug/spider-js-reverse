# 抖音 PC Web 评论协议爬取与 a_bogus 本地签（2026-07-24）

> 任务：`task_20260723_061837_889ab753`  
> 目标：纯协议拉取 `/aweme/v1/web/comment/list/`，本地生成 `a_bogus`，Cookie/`msToken` 可缓存后关浏览器复用。  
> **项目踩坑日志（MCP 总表）**：[`docs/mcp_pitfalls.md`](../../docs/mcp_pitfalls.md) 顶部「2026-07-24 — 抖音评论协议爬取 / 本地签延伸踩坑」

---

## 1. 结论摘要

| 项 | 结论 |
|----|------|
| `a_bogus` | bdms VM **func 150** 直调可本地生成（sdenv）；~188–192 字符；**每页 query（含 cursor）必须重签** |
| `msToken` | 会话级；活体来自 `localStorage.xmst` / mssdk；纯 sdenv **不能**稳定自产；用浏览器导出后缓存即可 |
| Cookie | 登录态 `sessionid` 等 Expires 约 **60 天**；脚本默认缓存 **1440h**；风控/踢登可提前失效 |
| 评论接口 | Cookie + `a_bogus` + `msToken` + `verifyFp`/`uifid` 即可；本版**未**还原 `x-secsdk-web-signature`，实测可通 |
| 浏览器 | **首次** attach Edge 导出 Cookie/`xmst`；之后 `--cache-only` **可关浏览器**纯本地爬 |

**实证：**

- 200 条：`comments_7661571300523085094_20260724_120231.json`
- 350 条（纯缓存）：`comments_7641900467982732582_20260724_140651.json`，`session_via=cache`，无 ERROR

---

## 2. 脚本与路径

| 文件 | 作用 |
|------|------|
| `.../repro/crawl_video_comments.py` | 评论爬取 CLI（短链/口令、分页、随机休眠、JSON 落盘） |
| `.../repro/sdenv_local_sign.py` | 本地 `a_bogus` + `msToken` 组装 |
| `.../runtime_scopes/douyin_cookie_cache.json` | Cookie + xmst 本地缓存 |
| `.../runtime_scopes/mstoken_cache.json` | msToken 缓存 |
| `.../runtime_scopes/comments_<aweme_id>_<ts>.json` | 评论结果 |

根目录（相对仓库）：

`server/data/reverse_runs/task_20260723_061837_889ab753/`

算法细节见：`cases/a_bogus/README.md`（99B→148→双 SM3 XOR→130 Base64）。

---

## 3. 评论爬取用法

### 3.1 环境

```text
Python: d:\python_work\venv\Scripts\python.exe
后端:   http://127.0.0.1:27183（仅刷新 Cookie 时需要）
Edge:   --remote-debugging-port=9222 attach（仅首次/刷新 Cookie）
```

### 3.2 首次导出 Cookie

```bash
cd server/data/reverse_runs/task_20260723_061837_889ab753/repro
d:\python_work\venv\Scripts\python.exe crawl_video_comments.py --refresh-cookie
```

会写入 `runtime_scopes/douyin_cookie_cache.json`（含 `cookie_str`、`xmst`、`UIFID`、`s_v_web_id` 等）。

### 3.3 纯本地爬评论（可关浏览器）

```bash
# 视频链接或分享口令均可；短链自动跳转
d:\python_work\venv\Scripts\python.exe crawl_video_comments.py ^
  "https://v.douyin.com/xxxx/" 350 ^
  --cache-only --page-size 20 --delay-min 1.8 --delay-max 4.2
```

常用参数：

| 参数 | 含义 | 默认 |
|------|------|------|
| `--cache-only` | 只用本地 Cookie，不连浏览器 | 关（默认也优先读缓存） |
| `--refresh-cookie` | 强制从 Edge 刷新缓存 | 关 |
| `--page-size` | 每页条数 | 10（最大 20） |
| `--delay-min/max` | 页间随机休眠（秒） | 1.5 / 4.5 |
| `--cookie-max-age-hours` | 缓存最长小时数 | 1440（≈60 天） |

### 3.4 输出 JSON 结构

```json
{
  "aweme_id": "...",
  "source_url": "...",
  "requested": 350,
  "got": 350,
  "fetched_at": "...",
  "pages": 18,
  "session_via": "cache",
  "comments": [
    {
      "cid": "...",
      "text": "...",
      "digg_count": 0,
      "create_time": 1784865289,
      "ip_label": "山东",
      "reply_comment_total": 0,
      "user_id": "...",
      "nickname": "...",
      "unique_id": "..."
    }
  ]
}
```

说明：极少数条目 `text` 为空（表情/图片评等），属业务数据，不是接口失败。

### 3.5 接口要点

- 路径：`GET https://www.douyin.com/aweme/v1/web/comment/list/`
- 翻页：响应 `cursor` / `has_more`；请求里 `cursor` 变则 **必须重签 a_bogus**
- 成功：HTTP 200 且 `status_code == 0`
- Header：`Cookie`（latin-1 安全子集）、`Referer: /video/<id>`、PC UA

---

## 4. 逆向心得（可复用）

### 4.1 动态优先、别猜算法

1. 用 listener 确认目标接口与参数位置（`a_bogus` / `msToken` 在 query）。
2. XHR 断点或插桩拿到 Call Stack：业务签在 bdms 钩子链，不是 secsdk `webSignUrl`（后者管 `x-secsdk-web-signature`）。
3. VM 插桩确认 **func 150 leave == 活体 a_bogus**；func 107 只是 XHR 钩子，不能当 `encrypt(url)`。

### 4.2 sdenv 本地签是工程解，不是纯算法解

- 补丁 `D()`，按 `vm_func_fingerprints.json` 暴露 150。
- 必备补环境：`process` 浏览器态、`Function.prototype.toString` 可写、`global`/`globalThis`。
- **不要**把遥测 `strData`（`magic:538969122`）当成业务 `a_bogus`。

### 4.3 msToken ≠ a_bogus

| | a_bogus | msToken |
|--|---------|---------|
| 变化 | 几乎每请求（跟 query） | 会话级，可复用很久 |
| 本地 | fn150 稳定 | mssdk `/web/r/token` 在 sdenv 易挂/只回遥测 |
| 正确来源 | 本地签 | `localStorage.xmst` 或活体 append |

路径：`浏览器 xmst` → `sign_a_bogus(ms_token=...)` → `localStorage.setItem('xmst')` 进 bdms → 缓存文件。

### 4.4 Cookie 与「关浏览器」

- sdenv 有 API 模拟，**没有**你的登录态数据。
- 「纯本地」= 本地签 + **已缓存 Cookie/xmst**，不是零依赖。
- 登录 Cookie Expires ≈ 60 天；脚本缓存默认对齐；服务端仍可提前作废。

---

## 5. 踩坑记录（误判 → 真因 → 信号 → 修法）

### 坑 1：页面卡死仍用 full 注入

- **误判**：多试几次 full 注入。
- **真因**：高侵入 Hook 触发 debugger/白屏。
- **信号**：loading、Console 刷屏、`ch_page_run_js` 超时。
- **修法**：`capture_profile=safe_capture`；证据走 listener / injection_evidence。

### 坑 2：业务 XHR 空壳 send 同步回调死循环

- **误判**：sdenv 挂了、bdms 坏了。
- **真因**：stub `send` 同步调 `onreadystatechange` → 重入。
- **信号**：`require(sdenv)` 后整段永不返回；Python `TimeoutExpired`。
- **修法**：回调 `setTimeout(0)`；或只 stub 非 mssdk 请求。

### 坑 3：`sdenv-main` 冷启动 ~45s

- **误判**：脚本逻辑超时/写坏了。
- **真因**：`require('../../sdenv-main/sdenv-main')` 冷加载很慢。
- **信号**：最小 `console.log` runner 也要几十秒才出结果。
- **修法**：签超时给到 **150s**；接受首页慢，后续页约 15–25s。

### 坑 4：Cookie 头含中文导致 `latin-1` 编码失败

- **误判**：网络挂了、签名错了。
- **真因**：`Cookie` 头必须 latin-1，部分 Cookie 值含中文。
- **信号**：`UnicodeEncodeError: 'latin-1' codec can't encode...`
- **修法**：组 `cookie_str` 时跳过无法 latin-1 编码的项。

### 坑 5：Python 3.10 `fromisoformat` 不吃 `+08:00` 写法不当

- **误判**：缓存总是 miss → 每次 `local_random`。
- **真因**：时间解析异常被吞掉。
- **修法**：统一存 UTC `+00:00`；读时兼容旧格式。

### 坑 6：短链 `v.douyin.com` 直连易挂

- **误判**：解析失败就不能爬。
- **真因**：短链跳转偶发极慢/挂死。
- **修法**：短超时；失败时用浏览器导航拿 `/video/<id>`；口令里正则抽 URL。

### 坑 7：评论接口参数体系误判

- **误判**：只要 a_bogus，或必须 X-Bogus。
- **真因**：`comment/list` 活体常**不带** query `X-Bogus`；要 Cookie + a_bogus + msToken + verifyFp/uifid。
- **修法**：以 listener 样本为准，不要抄旧双签印象。

### 坑 8：以为矩阵狂并发即可

- **误判**：多进程同时签会快很多。
- **真因**：单 Cookie + 每页必签；硬并发易风控，且 Node/sdenv 更吃资源。
- **修法**：先单号顺序批跑 + 随机休眠；号池是下一步。

---

## 6. 性能（实测）

| 场景 | 耗时 |
|------|------|
| 冷启动第 1 页 | ~2 分钟（主要 sdenv require） |
| 后续每页 | ~15–25s（签 12–18s + 休眠 2–4s） |
| 200 条 / 页 20 | ~3.3 分钟 |
| 350 条 / 页 20 / cache-only | ~8.5 分钟，接口全程正常 |

加速方向（未做）：常驻 Node 签程、跳过冷 require。

---

## 7. 未完成 / 下一阶段

1. 多视频列表批爬 + 断点续跑  
2. 多 Cookie 号池矩阵  
3. secsdk `x-secsdk-web-signature` 本地化（当前非刚需）  
4. 纯 Python 算法还原 a_bogus（研究向）  
5. 常驻签名服务降延迟  

---

## 8. 快速自检清单

- [ ] `douyin_cookie_cache.json` 存在且未超 `max_age_hours`  
- [ ] `--cache-only` 日志出现 `会话来源: cache`  
- [ ] 每页 `status_code=0` 且 `got` 递增  
- [ ] 连续失败 → `--refresh-cookie` 后重试  
- [ ] 不要把 `local_random` 的 msToken 当活体真值用于强校验场景  
