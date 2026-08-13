# ctbpsp.com 翻页(recommand)数据请求逆向

- 日期：2026-07-09
- 类型：WAF + 客户端加密响应 + 客户端反爬令牌（vaptcha/易盾）
- 站点：https://ctbpsp.com/#/ （中国公共采购服务平台 SPA，Vue + Element-UI）

## 目标请求（已确认）

```
GET /cutominfoapi/recommand/type/5/pagesize/10/currentpage/<N>?province=&industry=
```

- 翻页参数 `currentpage=<N>` 是**路径段**（不是 query，也不是 `pageNum`）。
- `type=5` 固定（推荐/中标类型），`pagesize=10` 每页条数。
- `province=&industry=` 两个空 query 参数**必须存在**（缺失 → 源站 `参数验证失败`）。
- 来自 `app.91665be0.js`：`getrecommand` → `oe("type/5/pagesize/10/currentpage/"+currentpage)` →
  `se({method:"get",url:"/cutominfoapi/recommand/"+e})`。

## 防护链路（已逐层验证）

1. **安恒 WAF（`acw_tc` + `type__1017`）**：裸 HTTP 被拦成挑战页 `function M(){var GH=[...]}`。
   浏览器访问后自动：`acw_tc`(httpOnly) 写入 Cookie → 307 重定向补 `type__1017=` 后重发。
   `type__1017` 由 WAF 挑战脚本计算，单次会话有效。
2. **数美反爬（`gdxidpyhxdE` / `ssxmod_itna` / `ssxmod_itna2` / `__snaker__id`）**：SPA 加载后由 SDK 写 Cookie。
3. **响应加密**：源站返回 `Base64(DES-ECB, key="1qaz@wsx", PKCS7)` 的密文字符串，
   SPA 用 `X()` 解密。已离线复现解密（pycryptodome）：
   ```python
   from Crypto.Cipher import DES
   pt = DES.new(b"1qaz@wsx", DES.MODE_ECB).decrypt(base64.b64decode(cipher))
   # 去 PKCS7 填充后 = {"success":true,"dataList":[...],"totalPage":N}
   ```
   （`X` 源码：`x.a.DES.decrypt({ciphertext:x.a.enc.Base64.parse(e)}, key="1qaz@wsx3e"(取前8字节), {mode:ECB, padding:Pkcs7})`）

## 当前卡点（未解决）

源站对 recommand 做**参数/令牌校验**，缺少则固定返回：
```
{"success":false,"data":null,"errorMessage":"参数验证失败"}
```
经对比捕获证实：**SPA 自身在自动化会话里的 recommand 响应也是 `参数验证失败`**（与我方请求完全一致），
原因是客户端 `window.vaptchaObj` 在当前会话**不存在**（`{exists:false}`），
取不到 `window.vaptchaObj.getVerifyResult().token`（顶象/易盾 vaptcha 令牌）。

→ 翻页数据要真正拿到，必须解决**客户端 vaptcha 令牌的生成/提取**（独立于本请求的下一个逆向任务）。

## 本地复现脚本（已落地 scratch/）

- `scratch/ctbpsp_connect.py`：连接 MCP 浏览器(port 取自 ch_cdp_start)，页面注入同源 fetch 抓取
  `recommand` 各页，再用 `DOMStorage`(不依赖 JS 主线程) 读回，DES 解密。
  → 完整跑通到"拿到密文 + 解密"，停在 vaptcha 令牌校验。
- `scratch/ctbpsp_final.py`：浏览器顶层导航 API（自动过 WAF 补 `type__1017`），读 `tab.html` 解密。
- `scratch/ctbpsp_capture.py` / `ctbpsp_vaptcha.py`：请求/响应/令牌对比探测脚本。

运行：先 `ch_cdp_start` 起浏览器拿 `port`（如 9223），再
`python scratch/ctbpsp_connect.py 9223`。

## 误判点（固定格式）

- 误判 → 真实原因 → 识别信号 → 修复方式 → 可复用规则
1. 误判：翻页用 `pageNum`/`page` query 参数。真实原因：`currentpage` 是路径段（`type/5/pagesize/10/currentpage/N`）。
   识别信号：静态读 `app.91665be0.js` 的 `getrecommand`。规则：先静态定位入口再下结论。
2. 误判：带全量 WAF Cookie 的纯 HTTP 能复现。真实原因：安恒 WAF 还校验 `type__1017`(307重定向补) 且
   源站还要 vaptcha 令牌。识别信号：urllib 带 Cookie 仍返回挑战页/参数验证失败。
   规则：WAF Cookie ≠ 够，需会话级 WAF 证明 + 反爬令牌。
3. 误判：hook 注入导致页面 `tableId/$refs` TypeError。真实原因：站点自身 Element-UI bug，
   干净浏览器同样冻结。识别信号：A/B（inject_hook_first_pack=false 仍冻）。规则：先 A/B 排除自身注入。
4. 误判：SPA 的 recommand 一定成功。真实原因：自动化会话无 `window.vaptchaObj`，SPA 自己也被 `参数验证失败`。
   识别信号：hook 同时抓 SPA 响应与我方响应，二者一致。规则：以实际响应为证据，不假设站点"正常"。

## 下一步（待用户确认）

- 选项 A：深入提取/复现 vaptcha(`window.vaptchaObj.getVerifyResult().token`) 令牌，打通真实数据。
- 选项 B：以"请求结构 + DES 解密 + WAF 会话"作为本请求复现交付，vaptcha 令牌另立任务。
