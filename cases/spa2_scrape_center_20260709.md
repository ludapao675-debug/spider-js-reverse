# spa2.scrape.center 分页请求逆向

- 日期：2026-07-09
- 类型：签名型（请求参数 token，SHA1 + Base64）
- 站点：https://spa2.scrape.center （Vue SPA，分页电影列表）

## 目标请求

```
GET /api/movie/?limit=10&offset=0&token=<token>
```

- `limit`：每页条数（列表页 `t.limit`，默认 10）
- `offset`：偏移量 = `(page-1) * limit`
- `token`：客户端生成的校验参数（服务端必校验，缺失/错误返回空或 500）

详情页：`GET /api/movie/{key}?token=<token>`，`token = gen(url, 0)`。

## 参数生成位置

- 列表页逻辑：`spa2_c2.js`（分页 chunk）
  `e = Object(i["a"])(this.$store.state.url.index, a)` → `this.$axios.get(url, {params:{limit, offset, token:e}})`
- 详情页逻辑：`spa2_c3.js`
  `a = Object(s["a"])(detailUrl, 0)` → `this.$axios.get(detailUrl, {params:{token:a}})`
- 生成函数本体：`spa2_c1.js` 模块 `7d92`（依赖 `3452`=CryptoJS）：

```js
function i() {                       // i(url, offset)
  var t = Math.round((new Date).getTime()/1e3).toString();  // 秒级时间戳
  var r = [].slice.call(arguments);                 // [url, offset]
  r.push(t);                                          // [url, offset, ts]
  var o = n.SHA1(r.join(",")).toString(n.enc.Hex);    // SHA1("url,offset,ts") hex
  var c = n.enc.Base64.stringify(n.enc.Utf8.parse([o, t].join(","))); // base64(sha1+","+ts)
  return c;
}
```

## 算法（一句话）

**token = base64( SHA1("url,offset,ts") + "," + ts )**，其中 `ts` 为秒级时间戳，`url` 即 `/api/movie`，`offset` 为分页偏移。

> 注意：token 把 ts 同时写入签名源与末尾，服务端可自解析 ts 并重算校验，属**无时间窗/可重放**型校验。

## 离线复现（Python）

见 `scratch/verify_spa2.py`：

```python
import time, hashlib, base64
def gen_token(url, offset):
    ts = str(int(round(time.time())))
    joined = ",".join([url, str(offset), ts])
    sha1_hex = hashlib.sha1(joined.encode()).hexdigest()
    return base64.b64encode((sha1_hex + "," + ts).encode()).decode()
```

## 验证结果

- page 1/2/3 均返回 `HTTP 200`，`count=104`，片名正确（霸王别姬 / V字仇杀队 / 黄金三镖客…）。
- 无 token → 空响应；token 错误 → 500。复现 token 100% 通过。

## 取证方式备注（本次踩的坑）

- **静态分析路径（最终采用）**：站点 JS 为 webpack 分块；`token` 字面量不在 `app.js` 引导里，而在 chunk（`spa2_c2.js`/`spa2_c3.js`）的请求构造处，真正算法在 `spa2_c1.js` 模块 `7d92`。用 `curl` 抓 HTML 取 `<script src>`（注意属性**无引号**，`src=/js/...`），再下载 chunk 用 Python 直接扫（ripgrep 默认跳过 gitignored 的 `scratch/`，导致 `search_content` 搜不到）。
- **浏览器路径（未走通，记录环境坑）**：`ch_cdp_start` 能起 Chrome（pid 5604/子进程 21956），但 `ch_listener_start` 需要先有 `browser_id`；而 BrowserRegistry 注册依赖页面操作接入，DrissionPage 连 9222 反复重试约 45s，触发 MCP 60s 超时。文档列出的 `ch_browser_list_tabs`/`ch_browser_current_tab`/`ch_cdp_detect_browsers` 在当前 MCP 实例**未注册**（文档与实现不一致）。建议后续用 `ch_page_navigate` 先在 BrowserRegistry 注册浏览器再起监听器。

## 失败坑点（固定格式）

- 误判 → 真实原因 → 识别信号 → 修复方式 → 可复用规则
1. 误判：`token` 是 AES 加密（经典 spa2 教科书版本）。真实原因：该部署版本改为 **SHA1+Base64**，无 AES。识别信号：bundle 里搜不到 `CryptoJS.AES.encrypt` 调用点，只有 `n.SHA1`/`n.enc.Base64`。修复：按 `7d92` 模块源码复现。规则：先验源码再套教科书，不同部署版本算法会变。
2. 误判：`search_content` 搜不到 `token` 说明没这参数。真实原因：ripgrep 跳过 gitignored 的 `scratch/`。识别信号：浏览器实测 `token=test`→500 证明参数存在。修复：用 Python 直接读文件扫描。规则：抓到本地的 bundle 用脚本扫，别依赖 ripgrep。
