# toutiao_a_bogus — 今日头条 a_bogus 纯 Node 离线复现

> **新对话续写请先读 → [IMPLEMENTATION.md](./IMPLEMENTATION.md)**（架构、工作流、集成方式、待办、踩坑）

## 一句话状态（2026-07-21）

| 能力 | 状态 |
|------|------|
| 纯 Node 产出 `a_bogus` + `msToken` | ✅ `replay_bdms_offline.js`（`msToken` 来自 `localStorage.xmst` 缓存） |
| **稳定取 feed（推荐）** | ✅ `python stable_local_feed.py --no-refresh` — **无需开浏览器** |
| `msToken` 来源 | `mssdk` 响应头 `x-ms-token` ↔ `me[24].inner` ↔ **`localStorage.xmst`**，落盘 `mstoken_cache.json` |
| 长签对齐（Node→活体 180） | ⏳ 深度逆向进行中；见 `longsign_branch_evidence.json`（已证伪 me[23] 开关说） |
| 浏览器 | 仅**首次** / cache 失效时刷一次；日常纯本地 |

## 快速开始

```bash
cd cases/toutiao_a_bogus

# 首次（有后端+浏览器时跑一次，写入 mstoken_cache.json）
node refresh_env_snapshot.js
node replay_bdms_offline.js   # 会自动从 snapshot 导入 cache

# 之后：纯本地（不需要浏览器）
python stable_local_feed.py --no-refresh
```

## 核心文件

| 文件 | 说明 |
|------|------|
| [IMPLEMENTATION.md](./IMPLEMENTATION.md) | **交接文档（新对话必读）** |
| `replay_bdms_offline.js` | Node 离线签名核心 |
| `sign_abogus.py` | Python 封装 |
| `sign_and_validate.js` | 刷新环境 → 签名 → 验收 |
| `browser_env_snapshot.example.json` | 快照格式示例 |
| `raw/bdms.js` | JSVMP 算法载体 |

## 架构摘要

- 算法：`bdms.js` 内嵌 JSVMP（`HNOJ@?RC`），非抖音 WASM
- 签名链：`bdms.init` hook XHR → `send()` 后 URL 写入 `msToken` + `a_bogus`
- **不是** `ye(url)` 直接返回字符串

详细架构、禁止事项、待办清单见 [IMPLEMENTATION.md](./IMPLEMENTATION.md)。

## 证据文件

| 路径 | 说明 |
|------|------|
| `abogus_pairs.json` | 浏览器 input/output 配对 |
| `raw/` | 页面 bundle 快照 |
| `capture_abogus_hook.js` | 抓包 Hook |
