# 猿人学第 9 题：js 混淆 - 动态 cookie 2

> 逆向完成于 2026-08-07 | 目标：`https://match.yuanrenxue.cn/match/9`

## 题目要求

- 使用爬虫脚本请求全部 5 页数据，计算加和并提交
- 提醒 1：发送第 5 页时 UA 必须为 `yuanrenxue`，否则不返回数据
- 提醒 2：请求携带 sessionid（答案按用户不同）

## 答案

**26,292,369**（50 个数字加和）

| 页码 | 数据 | 小计 |
|------|------|------|
| 1 | 453813, 777542, 568193, 545968, 624130, 590114, 416633, 588242, 121304, 244802 | 4,930,741 |
| 2 | 777632, 442655, 752325, 507572, 477930, 741274, 239221, 676308, 582687, 766514 | 5,964,118 |
| 3 | 549724, 403398, 793102, 512558, 119135, 713375, 853460, 242088, 717962, 294225 | 5,199,027 |
| 4 | 716424, 687199, 857810, 515347, 331839, 105500, 339821, 600850, 111553, 287575 | 4,553,918 |
| 5 | 321745, 171632, 135509, 512128, 725855, 870940, 946879, 657968, 837368, 464541 | 5,644,565 |

## 核心机制（source-to-sink）

```
数据接口 GET /api/question/9?page=N&pageSize=10&kw=
  ├─ 校验 Cookie: m（动态 cookie，4 秒刷新）
  ├─ 校验 UA：第 5 页要求 User-Agent == "yuanrenxue"
  │
  ├─ m 无效 → 返回 {"data": "var $a=[...混淆JS...]"}（39-60KB）
  │     └─ 页面 eval($a) → $c 生成新 m 写入 document.cookie → reload 重试
  ├─ m 有效 + UA 不符（仅第 5 页）→ 返回 ["请","将","UA","改","为","yuan","ren","xue","哦"]
  └─ m 有效 + UA 正确 → 返回 {"data": [10 个数字]}
```

### 关键组件

1. **`/static/new_match/question/9/udc.js`（719KB，jsjiami.com.v5 混淆）**
   - 定义全局 `decrypt` 函数（m 生成核心）
   - `setInterval(..., 4000)` 每 4 秒刷新 m cookie
   - 页面内 `window.request`/`window.match1` 实际为 undefined（防御性调用）

2. **服务器下发的 `$a` 预检代码（每次请求动态生成，含时间戳）**
   - `$b = base64 解码器`（$a 数组元素为 base64 编码字符串）
   - `$c = m 生成函数`，`setInterval($c, 4000)` 持续刷新
   - 核心调用：`decrypt(时间戳)` → 拼接 `'m=' + (m-1) + res + 后缀`
   - 写 `document.cookie = 'm=...'`（无 expires → 会话 cookie）

3. **页面内联脚本（match/9 L683-751）**
   - `req(np)`：`window.request&&window.request()` + `d.m=window.match1`（undefined 被 $.param 跳过）
   - `res.data instanceof Array ? render : eval(res.data)+reload`

## 校验逻辑（踩坑后确认）

- **m 有效性 = 生成时刻 + 请求侧环境强绑定**：m 编码了页面环境信息（UA/时间戳），
  本地直接复用 cookie 值请求会被拒（即使 m 新鲜、UA 一致）
- **正确姿势（页面内活体 + 毫秒级桥接）**：
  1. 页面内 `fetch 接口` → `eval($a)` 刷新 m（页面环境生成）
  2. 同一 JS 调用内把 m 传给本地桥接服务（`http://127.0.0.1:8765/?m=...`）
  3. 本地立即请求（<100ms），第 5 页用 `User-Agent: yuanrenxue`
- **页面翻页天然失败**：翻页请求返回 $a → eval → 2 秒后 reload → 回到第 1 页（页面设计如此，靠"预检→reload→第 1 页成功"自愈）

## 本地复现要点

- udc.js 可在 Node 环境直接执行（stub document.cookie/window/navigator/location/setInterval）
- `$a` 代码在 Node 中缺 `decrypt`（由 udc.js 提供），需先 eval udc.js
- Node 生成的 m 格式正确但服务器拒绝 → 必须页面内生成（环境指纹绑定）

## 取证记录

- browser_id: `04366b81-eb6c-4e27-bc23-6edab50785c9`（attach 9222）
- 数据接口：`/api/question/9`（非 /api/match/9）
- 动态 cookie：`m`（约 360-380 字符，URL 编码，`...==r` 结尾）
- 混淆家族：jsjiami.com.v5（udc.js）+ 自定义字符串数组混淆（$a 响应）

## 复现脚本

- `repro/q9_bridge.py`：本地桥接（收 m → 请求第 5 页，UA=yuanrenxue）
- 页面脚本：`fetch → eval($a) → 传 m 到桥接 → 返回数据`
