# Crypto Hunter Lite — MCP 踩坑日志 (Pitfalls)

> **强要求**:遇到 MCP 调用异常 / 结果不符预期 / 工具报 `not registered` / 页面 JS 返回 null 等，**先读本文件**，看是否已有同类问题与解法，**不要凭空重试或改写逻辑**。
> 本日志持续累积真实踩坑。新增请追加在最上面（带日期），保留「现象 → 根因 → 解法」三段结构。

---

## 2026-08-12 — `ch_debugger_get_scope` 里的闭包变量 ≠ `window` 全局变量

> 现场：猿人学 match/25（JSVMP token 生成，`window.call(now, "request", page)` 内部依赖闭包变量 `matchnumber`）。

- **现象**：`ch_debugger_get_scope` 在 `window.call` 内部断点处看到局部变量 `matchnumber`，随后直接在页面执行 `window.call(now, "request", page) `之外，另写 `window.x(now + String(p) + window.matchnumber)`，结果 `window.matchnumber === undefined`，token 计算全部失败。
- **根因**：`ch_debugger_get_scope` 读到的是**暂停帧的局部/闭包作用域**，这些变量只在该函数的执行上下文里存在，从来不会被赋值到 `window` 上——除非源码显式写了 `window.xxx = xxx`。看到 scope 里出现某个变量名，不能反推它是全局可访问的。
- **解法**：
  1. scope 只用来**确认输入依赖和调用约定**（例如确认 token 计算确实用到了 `matchnumber`、`now`、`page` 这几个入参/闭包变量），不要把闭包变量名直接当成 `window.xxx` 去拼接调用。
  2. 复现时优先直接调用**暴露在 window 上的入口函数**（如 `window.call(now, "request", page)`），让函数内部自己从闭包/模块作用域里取值，而不是自己在外部重建那些变量。
  3. 如果确实需要在外部拿到闭包变量的值，只能通过 `evaluateOnCallFrame`/`ch_debugger_side_capture` 在暂停帧内读取并回传，不能假设它已经或会被挂到 `window` 上。
- **举一反三**：这条对所有 JSVMP/混淆场景通用——`ch_search_loaded_scripts`、`ch_static_analyze` 看到的变量名同样只是词法层信息，不代表运行时可从 `window` 访问；能否从外部拿到值，只看源码是否显式导出，不看调试器有没有"看到"它。

---

## 2026-08-11 — Pytest 安全统一回归与显式 Edge E2E 边界

- **现象**：直接运行 pytest 或手工检查时，测试收集可能触发导入期副作用，或误连当前调试浏览器/后端，导致本地会话被干扰。
- **根因**：safe 与真实浏览器 E2E 的资源边界不同；未通过统一入口时，端口、外网访问与进程清理责任容易混淆。
- **解法**：
  - 安全统一回归：`D:\python_word\Scripts\python.exe scripts/run_regression.py --suite safe`
  - 显式 Edge E2E：`D:\python_word\Scripts\python.exe scripts/run_regression.py --suite e2e --cdp-port 9222`
- **边界**：safe 不连接 `9222` / `27183`、不访问外网；e2e 只清理测试自身记录的精确 PID、标签页和工件，禁止按进程名批量终止浏览器或 Python 进程。

### HeapProfiler live evidence（本次验证）

- CDP：`127.0.0.1:9222`；后端：`127.0.0.1:27183`；浏览器原有标签未导航或关闭。
- 测试记录：`browser_id=eb34643c-eb56-401f-a9b5-052880fc7403`，测试 `tab_id=C081E6998C29B3C339C008BD7127F5DB`，`capture_id=b9d3f8de98e6485f82bea7db8297128f`。
- 结果摘要：快照 `2,470,238` bytes，索引 `30,187` nodes，唯一搜索命中 `1`，Retainer 路径 `2`；采样、快照、索引、查询和 cleanup 均成功。
- 清理：测试标签关闭、capture 工件目录删除；原有 xueqiu 标签仍保留。不要把 Heap capture ID 当作长期证据引用，下一次运行会生成新 ID。

---

## 2026-08-11 — 定位门禁不认弱关键词 / run_js 不 await promise / 早期注入 reload 失效 / 大 bundle 搜索超时

> 现场：淘宝登录 RSA、猿人学 match/7（动态字体）、match/20（webpack+Rust wasm）三案例联调。

- **现象 1：`ch_search_loaded_scripts` 命中 25 条（page/getTime 等通用词）仍报 `positioning_required`**
  - **根因**：门禁按 task session 记录定位证据，且要求协议强指纹（字段名/常量/密文），弱关键词不算数；不传 `session_id` 的搜索命中不记入任务账本。
  - **解法**：用 `ch_cipher_search(query=已捕获的密文/sign 值, session_id=task_id)` 反查命中即解锁，最可靠；或在目标脚本上搜 `m.sign|pkg/index` 类专有指纹。
  - **边界**：每次 `ch_cdp_start` 新会话会重置门禁；先读 `docs/js_positioning_methods.md`。

- **现象 2：`ch_page_run_js` 里 `fetch().then()` 返回 null / 空对象；同步 XHR 设 `responseType='arraybuffer'` 抛 `InvalidAccessError`**
  - **根因**：run_js 不等待 promise 完成（await_promise 对链式 IIFE 不保证）；Chromium 禁止 document 同步 XHR 修改 responseType。
  - **解法**：文本 JSON 用同步 XHR（`xhr.open(GET, url, false)`）；二进制（wasm 等）用**异步 XHR + `wait_for` 轮询就绪标志**（先启动下载存 `window.__flag`，下一步 `wait_for="window.__flag === true"`）。
  - **边界**：fetch 可用但结果要等下一次调用取；大结果自动落盘 `run_js_dumps/`。

- **现象 3：`ch_page_inject_early` 注入后页面 reload，hook 不生效（`WebAssembly.instantiateStreaming` 仍是 native code）**
  - **根因**：`addScriptToEvaluateOnNewDocument` 注册不可靠（identifier 返回自动编号，reload 后脚本未执行）。
  - **解法**：放弃 reload 注入方案，改**当前文档手动重放**：异步 XHR 下载 wasm → 自建 imports 实例化 → fake webpack require 执行胶水模块 → 调 JS 包装导出。
  - **边界**：wasm 环境绑定（创建 `js_sys::Object`）时 Node 复现必 panic，浏览器内重放是唯一路径。

- **现象 4：`ch_search_loaded_scripts` 对 600KB+ 大 bundle 超时（38-60s），CDP 命令排队拖垮页面**
  - **根因**：服务端枚举全部已加载脚本源码做正则匹配，大 chunk（如 639KB webpack bundle）耗时长。
  - **解法**：`curl` 下载 bundle 本地 grep（`Get-Content -Raw` + `IndexOf`/正则），或 `ch_fetch_url(grep=...)` 服务端直连按行过滤；大文件只搜特征串不搜通用词。
  - **边界**：本地分析用 UTF-8 读取，避免 PowerShell 控制台代码页乱码（`chcp 65001` 或输出重定向到文件再读）。

---

## 2026-08-10 — MCP 工具数量与旧客户端不一致：先确认暴露 Profile

- **现象**：同一后端在不同编辑器里看到的工具数不同，或默认会话调用 Protobuf、WASM 底层、Source Map、验证码、高级动态、流程图、Session、Site Rules 等工具时提示 `not registered`。
- **根因**：工具暴露面由 MCP sidecar 启动时的 `CRYPTO_HUNTER_MCP_PROFILE` 固定，不是 FastAPI 后端的路由数量。`editor` 为 94 个精简核心工具；默认 `expert` 为 150 个，增加上述专项工具；`full` 为 200 个，仅用于旧客户端兼容，并含流程图工具、Session、Site Rules、窗口状态、日志导出和内置 AI 管理工具。
- **解法**：默认 expert 已包含专项工具，流程图工具仍使用 `full`；需要最小工具面时显式设置 `editor`。默认 expert 先用 `ch_list_recommended_tools` 发现当前可用工具，不要把 `ch_tool_index` 当作默认入口。修改 profile 后必须重启 MCP sidecar；只重启 FastAPI 后端不会刷新 `tools/list`。
- **边界**：`CRYPTO_HUNTER_MCP_AUTO_ROUTES` 只控制自动路由包装，不能替代 profile；自动包装不会让未被 profile 暴露的工具出现在客户端。

---

## 2026-08-10 — JSVMP 页面函数不要批量塞进一次 run-js；UA 用 target 级 CDP 覆盖

> 实测页：猿人学测试环境 `match/21`（页面脚本 `match3.js`）；仅记录工具行为，不保存登录 Cookie、token 或题目答案。

- **现象 1：单次 `window.call('1')` 约需数秒，三次 Promise 循环在工具超时前仍未返回**
  - **根因**：目标脚本把 `Date.now()` 改写为同步 XHR `/api/getTime`，JSVMP 的一次调用会多次触发该同步路径。`Runtime.evaluate` 超时只结束 CDP 等待，已经进入 V8 的脚本仍可能继续占用页面主线程。
  - **解法**：一次 `ch_page_run_js` 只执行一次 `window.call`，把页码循环、结果拼接和节流放在外部控制层。工具现会默认拒绝 `window.call + for/while/Promise.all/数组迭代器`，返回 `RUN_JS_HIGH_RISK_BATCH_REJECTED`；只有隔离标签页中的受控实验才显式传 `allow_long_running=true`。
  - **超时后**：看 `execution_may_continue=true` / `retry_safe=false`；先做轻量探针，仍无响应则新建替代标签页并关闭旧标签页，禁止自动重放原脚本。

- **现象 2：页面 JS 调用 `setRequestHeader('User-Agent', 'yuanrenxue')` 不报错，但服务端仍收到普通 Edge UA**
  - **根因**：当前 Chromium 会静默丢弃页面脚本设置的 User-Agent 请求头；修改 `navigator.userAgent` 也不能等价修改网络栈。
  - **解法**：使用 `ch_page_set_user_agent(browser_id=..., tab_id=..., user_agent='yuanrenxue')`，两个 ID 都必须显式提供，工具不会回退活动页。工具经 target 的持久 CDP session 调用 `Network.setUserAgentOverride` 并验证 `navigator.userAgent`。保存返回的 `restore_user_agent`，使用后 `clear=true` 恢复；后端重建后需显式传回该恢复值。
  - **边界**：该工具只覆盖传统 UA，不伪造 `Sec-CH-UA` 等 Client Hints。

- **现象 3：浏览器请求成功，把 token/Cookie/UA/Referer 交给 Python 重放仍报 token failed**
  - **根因**：目标请求还依赖动态业务头，例如本案的 `Accept-Time`；“受限 Header 脱离浏览器发包”不是只复制四个常见头。
  - **解法**：从 listener/暂停请求中复制目标请求实际发送的业务头、Cookie 与 form/query，并做字段差分。不要硬编码 hop-by-hop 头或浏览器自动维护的长度头。

---

## 2026-08-06 — 拼多多 reviews 54001：根因是 TLS ClientHello，不是 token；换 chrome_150 可本地过

> 权威细节：`cases/pdd_goods_comments/README.md`「难点与踩坑速查」；证据 `phase1_live_evidence.json` / `phase0_tls_diff.json` / `offline_new_account_evidence.json`

- **现象**：同枚 `0as` anti_content + 同 Cookie + 同公网 IP：浏览器 fetch=200，`curl_cffi` 本地=54001；全链 a3/ae4/a4/t.gif 仍拒。
- **根因**：服务端把业务请求与 **TLS ClientHello（JA3/JA4，尤其签名算法 0904/05/06）** 绑定。curl_cffi 全档 JA4 对不齐 Edge 151 / 现代 Chrome；H2 SETTINGS（Akamai）可对齐也不够。
- **解法**：
  1. 发包栈用 **`tls-client-python`** 的 `client_identifier="chrome_150"`（勿用旧 PyPI `tls_client==1.0.1`，止于 chrome_120）；
  2. 出票：缓存 webpack 45246 bundle + sdenv（`--dump-assets` 一次，之后 `--offline`）；
  3. 脚本：`cases/pdd_goods_comments/pdd_comments_local_tls.py`。
- **仍成立的纪律**：单号单日本地 54001 ≤2；连续翻页间隔建议 ≥8–10s；一触 54001 停，同号浏览器也会被加热。`{"data":[]}` 是软限形态，≠健康空页。
- **纠正旧结论**：2026-08-05 条目里「大厂风控 token 只能浏览器内发、本地必 54001」在本案已被推翻——**本地可以发，但必须换对 TLS 栈**；浏览器 RPC 仍是托底。

---

## 2026-08-05 — 当前标签卡死 / 断点清不掉：换新标签再关旧标签

> 规则同源：`AGENTS.md`「标签页替换恢复」、`server/mcp_tool_guide.py` `CAPTURE_STABILITY_POLICY.stuck_tab_or_breakpoint_flood_recovery`、`server/mcp_usage.md`

- **现象：当前标签 `ch_page_*` 超时无响应；或 Debugger 断点/暂停洪水，`ch_breakpoint_remove` / `ch_debugger_resume_until_idle` / `ch_debugger_clear_pause_queue` 清不掉，页面一直卡**
  - **根因**：断点和暂停状态绑在该 tab 的 Debugger session 上；卡死页上的 JS/暂停循环占满事件循环，继续在同一标签 resume/删断点往往无效或更慢。
  - **解法（强制顺序）**：
    1. 记下卡死 `tab_id` 与目标 URL；
    2. `ch_browser_new_tab(url=<目标网页>)` 在新标签打开网页并继续操作；
    3. `ch_browser_close_tab(tab_id=<卡死旧 tab>)` 关闭卡死标签，释放断点/暂停状态；
    4. 新标签优先保持 `capture_profile="safe_capture"`，必要时重启 listener。
  - **禁忌**：不要在同一卡死标签上反复 resume/盲删断点空转；标签页替换优先于重启整个浏览器。

---

## 2026-08-05 — 人工过安全验证后，重放请求必须重新抓"新增凭证"（拼多多 verifyauthtoken）

> 现场：`cases/pdd_goods_comments/verify_token_replay.py`

- **现象**：人工过 `psnl_verification.html` 后，页面自身请求恢复正常，但沿用旧抓包模板的本地重放仍被拒。
- **根因**：过验证后站点会下发**新的会话凭证**——拼多多把它写进 `localStorage.VerifyAuthToken`，并由 Axios 拦截器注入为 `verifyauthtoken` 请求头，URL 也追加 `is_back=1`。旧模板没有这两项。
- **解法**：任何"人工过验证"之后，**必须重新用 listener 抓一条页面自身请求做头部 diff**（`ch_extract_request` detail=full），并扫描 `localStorage/sessionStorage` 新增键，再更新重放模板。注意：本案中补齐后本地仍 54001（该头必要非充分，真正阻碍是协议栈/带外遥测层），但漏掉它一定失败。

---

## 2026-08-05 — sdenv 离线跑 webpack 加密模块的四个工程坑（拼多多 anti_content 实验）

> 现场：`cases/pdd_goods_comments/local_repro_experiment.py`（webpack 闭包 362 模块 502KB 离线生成成功）

- **坑 1：不要序列化真实 `__webpack_require__` 帮助函数**
  - **现象**：`String(req.d)` 拼进 bundle 后沙箱报 TypeError。
  - **根因**：`req.d/req.n` 内部引用 runtime 私有变量（如 `i.o`），脱离原 runtime 即失效。
  - **解法**：自实现 webpack 标准等价版 `d/n/r/o/nmd/p`（见实验脚本）；缺 `nmd` 会报 `nmd is not a function`。
- **坑 2：依赖 BFS 正则不能写死形参名**
  - **现象**：`module_not_bundled:60278`。
  - **根因**：各工厂 require 形参名不同（`r(…)`/`n(…)`），只匹配 `r\(\d+\)` 会漏。
  - **解法**：通配 `\w\((\d{1,6})\)`，误收的 ID 在 `req.m` 不存在自动跳过，只增不减。
- **坑 3：sdenv runner 只 await 主代码的「完成值」**
  - **现象**：异步生成明明成功（console 有日志），但 `eval_expression`/cookie 读到 undefined。
  - **根因**：`sdenv_runner.js` 对 `vm.runInContext` 返回值做 `then` 判断——外层 IIFE 不 return Promise 时完成值是 undefined，runner 不会等异步生成，提前读 cookie/eval。
  - **解法**：主代码外层 IIFE 必须 `return (async function(){...})();`。
- **坑 4：sdenv `output` 是 5000 字符头部截断 + console 噪声**
  - **现象**：console 打印的长 token 只剩尾部/整段丢失。
  - **解法**：大结果改走 **cookie 通道**（`document.cookie="__sdenv_ac="+val`，响应 `cookies` 字段不截断）或 `eval_expression`（配合坑 3 的 return Promise）。SDK 噪声日志会挤占 5000 配额，必要时 console 过滤只透传标记行。

---

## 2026-08-05 — 本地直调后端 `/api/browser/page/run-js` 时 `args` 不生效（`$args` 未定义）

> 现场：`cases/pdd_goods_comments/pdd_comments_rpc.py` RPC 桥首跑全失败（result 非 dict / ReferenceError）

- **现象：POST `/api/browser/page/run-js` 时在 body 里传 `args`，code 中引用 `$args.xxx` 报错或拿到 undefined**
  - **根因**：`$args` 结构化注入是 **MCP sidecar 层**（`ch_page_run_js`）做的预处理，后端路由 `api_browser_page_run_js`（server.py）只透传 `code`，根本不消费 `args` 字段。
  - **解法**：本地脚本直调该路由时自行拼前缀：`(() => { const $args = <json>; return <原表达式>; })()`（`$args` 是合法 JS 标识符）。或统一走 MCP 工具而非直调 HTTP。

---

## 2026-08-05 — 拼多多 anti_content：一次性环境绑定 token + webpack 模块直调 + 频率红线

> 案例：`cases/pdd_goods_comments/README.md`；任务 `task_20260805_091450_261c67f0`
> 站点：`mobile.pinduoduo.com` 商品评论接口 `POST /proxy/api/reviews/{goods_id}/list`

- **现象 1：捕获的活体 anti_content 本地重放必 54001，哪怕秒级新鲜 token**
  - **根因**：anti_content 是 RCF 风控 SDK（assets-rcf/*.js，760KB 混淆）生成的**一次性环境绑定 token**：服务端校验的不只是 token 本身，还绑定浏览器请求环境。同一枚现场生成的 token，浏览器内 fetch 通过、本地 curl_cffi(impersonate=chrome)+全套 Cookie 秒级重放即被拒。
  - **解法**：此类 token **优先**走能对齐 JA4/`0904` 的 TLS 栈本地发包（本案终局：`tls-client` `chrome_150`，见 2026-08-06 条目）；浏览器内 fetch RPC 作托底。定界仍先做「同 token 浏览器内 vs 本地」对照。**注意**：旧文写「只能浏览器内发」已过时。

- **现象 2：webpack 打包站点的加密生成函数无全局入口**
  - **根因**：anti_content 生成函数是 webpack 模块闭包（`react_goods_comments_*.js` 里 `(0,q.g)()`），window 上无任何 antiSpider 类全局。
  - **解法**：劫持 `__LOADABLE_LOADED_CHUNKS__.push`（配合临时 `Array.prototype.push` 包装）捕获 `__webpack_require__`，再按**中文字符串指纹**（如"获取风控参数"）在 `req.m` 全部工厂里定位模块 ID（本次为 45246），`req(id).g()` 即可直调生成 token（~90ms/枚）。

- **现象 3：连续快速验证十几枚 token 后，页面被重定向到 `psnl_verification.html` 安全验证页**
  - **根因**：多次 54001 风控失败累计触发账号级验证挑战，整个会话被拦。
  - **解法**：验证实验要克制——单轮对照实验最多 2~3 次请求，失败即停；触验证后必须**人工过验证**，禁止自动化绕过。
  - **2026-08-05 补充（账号级累计制实证）**：即使浏览器侧请求全部健康、间隔充分，当日**本地 54001 累计**达账号阈值后仍会升级验证（第二次触发发生在浏览器侧零失败时）。风控预算是**账号×天**维度，不是会话维度；升级链端点：`xg/pfb/a4` 指纹上报 → `phantom/obtain_captcha` → `intelligence_verify` 页 → 新 VerifyAuthToken 下发。**纪律：单账号单日本地失败请求 ≤2 次。**
  - **2026-08-05 补充（遥测判据实验终局）**：`th.pinduoduo.com/t.gif` 行为遥测是**明文 k=v 无签名**载荷（log_id=时间戳+base36 随机，dcf=pdd_vds.计数.随机），本地伪造服务端 200 接受——但**遥测配对不是业务接口通过条件**（前置遥测+全头对齐 reviews 仍 54001）。教训：大厂埋点流（t.gif 类）普遍弱校验可伪造，**不要把"能伪造埋点"误判为"能通过风控"**；真正的关联信号在指纹上报链（xg/pfb/a4 类加密端点）或连接画像。遥测捕获技巧：页面内 hook `XMLHttpRequest.prototype.send` + `sendBeacon` + `fetch` 三通道即可全量截获。
- **2026-08-06 补充（解混淆中间产物同样高价值）**：`ch_deobfuscate_auto` 对字符串数组工厂在文件尾部的样本会漏检（Tier1 正则/webcrack 前向引用失败），但**手动闭包解码拿到字符串数组 dump + 别名传播内联替换**（部分内联版）已足够支撑静态审计——不必等完整解混淆。实战：拼多多 RCF SDK 靠这两件中间产物完成 a4 指纹上报全链逆向（sign 算法 + TLV 编码链 + 108 字段明文）。
- **2026-08-06 补充（"加密"上报先验结构再下结论）**：高熵二进制上报载荷先检查是否有版本前缀（如 `0a`）——剥掉前缀后可能就是标准 base64+zlib（`eJ` 开头即 zlib magic 0x789c 的 base64）。拼多多 a4 实际是 `'0a' + urlsafe_b64(zlib(TLV))`，TLV 用 zigzag-varint 长度（0xF1 tag 的 varint 恰好是 `e2 03` 标记）。误判为强加密会高估工作量数倍。
- **2026-08-06 补充（CDP 调试浏览器会被风控 SDK 上报为 bot）**：解码拼多多 a4 指纹明文发现 `botD={bot:true,botKind:"headless_chrome"}` + `cdpProxy:true` + `hookFuncs` 枚举出注入的 hook——**挂 CDP 调试端口 + 注入脚本的浏览器，每次指纹上报都在自我举报**，这是账号反复触发风控的深层原因。教训：风控 SDK 场景下，解码指纹上报明文是诊断"为什么被拦"的第一优先级动作；需要低风控压力取数时优先无 CDP 的干净浏览器或 RPC 形态最小化 hook 面。

---

## 2026-08-05 — 最小化窗口导致 CDP 截图 / Runtime.evaluate 超时

> 现场：拼多多商品评价页（`mobile.pinduoduo.com`），浏览器由 cdp_launcher 启动后被最小化

- **现象：`ch_page_screenshot` 报「操作超时，可能是页面加载过慢或网络问题」（29s 超时），但 `ch_page_get_info` 显示页面 `ready_state=complete`、`is_alive=true`，一切正常**
  - 同时 `ch_page_get_info` 返回的 `window_state` 为 `minimized`，这是唯一异常信号。

- **根因：Chrome 窗口被最小化后，CDP 的截图与部分 Runtime.evaluate 路径会挂起直到超时**
  - 最小化状态下页面不参与合成渲染，`Page.captureScreenshot` 等依赖渲染管线的命令拿不到帧，表现为 29s 超时而非快速失败；页面本身并未卡死。

- **解法：截图/页面操作前先恢复窗口，再重试**
  ```python
  ch_browser_set_window_state(state="normal")   # 236ms 生效
  ch_page_screenshot(...)                        # 恢复后 200ms 成功（raw_cdp）
  ```
  - **经验法则：截图或交互类操作超时但 `ch_page_get_info` 显示页面健康时，第一时间检查 `window_state` 是否为 `minimized`；先 `normal` 再重试，不要怀疑网络或重启浏览器。**

---

## 2026-08-03 — 快手直播弹幕 WS 拉取：TLS 指纹 / liveStreamId / 帧类型 / kwfv1 四坑

> 正式案例：`cases/kuaishou_live_danmu/README.md`、`kuaishou_live_danmu.py`、`kuaishou_hxfalcon.py`、`kuaishou_cookie_manager.py`
> 站点：快手 PC 直播 `live.kuaishou.com`（弹幕为 protobuf over WebSocket 推送）

- **现象 1：Python 连上快手直播 WS、发了进房帧，但只收到点赞/在线人数帧，收不到弹幕**
  - **根因**：`liveStreamId` 取错。页面 `__INITIAL_STATE__` 里有**多处** `liveStreamId`（推荐位/旧会话），正则误取非当前开播会话的值；用错后进房只订阅到错误房间，只能收 310/101 等通用帧。
  - **解法**：必须取 `__INITIAL_STATE__.liveroom.playList[0].liveStream.id`（当前开播会话）。纯 HTTP 拉房间页 HTML 解析即可，无需浏览器。

- **现象 2：Python `websocket-client` 连快手 WS，发任意帧即被服务端断开；空连接却能存活**
  - **根因**：快手对 WS 做 **TLS/JA3 指纹校验**。Python 默认 TLS 指纹被识别为非浏览器，业务帧一到就断连。
  - **解法**：改用 `curl_cffi.Session(impersonate="chrome")` 的 `ws_connect`（伪造 Chrome TLS 指纹）。**经验法则：大厂的长连 WS 除了协议帧正确，还要过 TLS 指纹关；`curl_cffi impersonate` 是首选。**

- **现象 3：进房后长时间收不到文本弹幕（829），误以为实现有 bug**
  - **根因**：帧类型认知偏差。浏览器弹幕区滚动的多为**礼物帧 310**（含弹幕文本）与**进场帧 340**（昵称列表）；纯文本评论是 829，在游戏房很稀疏。只解码 829 会误判“收不到”。
  - **解法**：全类型解码 —— 829=文本评论、310=礼物(含文本)、340=进场/用户列表、101=在线人数、510=点赞、300=进房 ACK。文本在 829 的 `f1.f7.f1.f1`（非静态推断的 f3）。

- **现象 4：想纯本地生成访客身份 kwfv1，sdenv 跑 kwf SDK 报 `Failed to process fingerprint`，自造 did+匿名 kww 被风控 `result=400002`**
  - **根因**：kwfv1 是快手 **kwf 指纹 SDK（Brook JSVMP）** 采集真实设备指纹（canvas/WebGL/字体等）后生成的设备指纹。沙箱伪造指纹会触发服务端风控挑战（400002 + 验证码）。
  - **解法**：kwfv1 **无法纯本地复现**，只能从真实浏览器一次性采集（`/api/browser/page/cookies`）后缓存复用（`kuaishou_cookies.json`）。**经验法则：设备指纹类 Cookie（kwfv1/did）靠采集+缓存，不要试图本地伪造。**

- **现象 5：想捕获浏览器真实进房帧，但页面加载时 WS 已发包，hook 来不及装**
  - **根因**：进房帧在页面脚本执行早期就发出，普通 `ch_page_run_js` 注入 hook 已经错过。
  - **解法**：用 `ch_page_inject_early` 注入 `WebSocket.prototype.send` hook（`run_on_new_document=true`），再导航/重载页面，hook 先于页面脚本执行即可捕获完整进房帧字节。

---

## 2026-08-02 — CryptoJS WordArray 字节序：AES 解密首字节乱码（大端坑）

> 正式案例：`cases/bidcenter_search_pagination/README.md`、`repro.py`
> 站点：采招网 `search.bidcenter.com.cn`（响应体 AES-128-CBC 加密）

- **现象：Python 复现 AES 解密，首字节解出 `0x8d` 等非 JSON 字符（`UnicodeDecodeError: invalid start byte`），而浏览器前端 `method.AESDecrypt` 能正常解出 JSON**
  - 密钥/iv 从前端 `searchv16.js` 直接抄的 `words` 数组常量，算法（AES-128-CBC / ZeroPadding）也一致，却解错。

- **根因：CryptoJS `WordArray.words` 每个 int 是 32 位「大端」整数（最高有效字节在高位），转字节时用了小端 `struct.pack("<I", w)` 导致密钥/iv 字节顺序整体反转**
  - CryptoJS 内存布局：`words[i]` 的 4 字节顺序是 `(w>>24)&0xFF, (w>>16)&0xFF, (w>>8)&0xFF, w&0xFF`（大端）。小端（`<I`）会把它翻成 `w&0xFF, (w>>8)&0xFF, ...`，AES 密钥差之毫厘全盘错。
  - **这也解释了为什么请求层一次就通、只有解密层出错**：请求是明文 form-urlencoded，不涉及 WordArray；密钥转换错误只在解密侧暴露。

- **解法：WordArray → bytes 必须用大端 `struct.pack(">I", w)`**
  ```python
  def _words_to_bytes(words):
      return b"".join(struct.pack(">I", w) for w in words)
  KEY = _words_to_bytes([863652730, 2036741733, 1164342596, 1782662963])  # 16 字节
  IV  = _words_to_bytes([1719227713, 1314533489, 1397643880, 1749959510])  # 16 字节
  ```
  - 经验法则：**凡是把前端 CryptoJS `words` 数组搬进 Python/Node 做 AES/DES/RC4 复现，一律按大端拆字节**，不要想当然套小端。先拿一段已知明文（或浏览器内 `CryptoJS.AES.encrypt` 的 output）做往返验证再写进复现逻辑。

---

## 2026-07-28 — 米画师 stalls WASM 签名间歇性 403（HashMap 迭代顺序非确定性）

> 正式案例：`cases/mihuashi_stalls_list/README.md`
> 脚本：`cases/mihuashi_stalls_list/repro.py`、`sign_tool.mjs`（`--batch=N`）

- **现象 1：本地复现（每次 spawn node 签名）拉分页，间歇性 403，成功率约 37%**
  - **根因**：`M-S` 由 WASM 内部对含 Rust `HashMap` 的载荷序列化生成，key 迭代顺序受 `getrandom`（WebCrypto 随机）影响，仅约 **38%** 签名落入服务端认可的规范顺序（有效族），其余 62% 为**确定性无效**签名。
  - **解法**：403 即**重新签名**重试（重新掷随机），而非重发同一 M-S。实测修复后 25/25 页全成功。

- **现象 1b（重要）：为摊薄 node 启动改用单进程批量签名（`--batch=8`），成功率反而从 100% 掉到 80%**
  - **根因**：getrandom 种子在 **WASM 实例初始化时定一次（进程级偏置）**：同一 node 进程内多个签名共享种子、高度同命运（实测进程可 8/8 全无效）。批量把 `max_retries` 次**独立**试验退化为「批数」次同命运试验，0.62ⁿ 中的 n 从 25 退化到 ~3。
  - **解法**：必须【每次重试 spawn 全新 node 进程】才能拿到独立种子；`--batch` 仅用于诊断，严禁用于抓取。**教训：优化前先确认重试的独立性，别把相关试验当独立试验。**

- **现象 2：误判「时间戳奇偶性 100% 相关」**
  - **根因**：采样巧合。浏览器时间连续，不可能只在奇数秒发请求；统一控制 ts 来源后连跑 16 次证明奇偶零相关。
  - **解法**：控制变量法，别被小样本伪相关带偏；先用 `ch_extract_request` 看真实成功请求头（真实 m-t=1785220383 是纯 10 位秒且为奇数，直接证伪）。

- **现象 3：无效签名重发一直 403，怀疑网络/风控抖动**
  - **根因**：无效签名是**确定性**的（同串重放 18/18 全 403），重发同一 M-S 徒劳；而有效签名重放 7/10（服务端集群约 17% 随机拒）。
  - **解法**：用「同一签名串重放」消歧——全 403=我方签名无效需重签；时而 200/403=服务端随机重试可解。

- **现象 4：想靠 M-S 特征子串 `MGarRj`(有效)/`MGarFz`(无效) 本地预筛**
  - **根因**：该特征子串依赖具体被签 URL（`/api/v1/stalls`），换接口即失效。
  - **解法**：仅作诊断识别，**不硬编码进复现逻辑**；用「403 重签重试」保证通用性。

- **现象 5：PowerShell 跑 repro.py 报 ExitCode 1 + 一堆乱码「NativeCommandError」**
  - **根因**：`logging` 的 INFO 走 stderr，PowerShell 把 stderr 当错误记录渲染（GBK 乱码）；Python 实际 stdout 输出正确 JSON 且返回 0。
  - **解法**：忽略该噪声，看 stdout 的 JSON 即可；如需干净输出可把日志级别调高或重定向 stderr。

---

## 2026-07-25 — 抖音 PC Web 私信发送 / `--to` 解析 / 风控验证码

> 正式案例：`cases/douyin_web_im_send/README.md`
> 脚本：`server/data/reverse_runs/task_20260725_042005_7f84894b/repro/send_im_message.py`
> 任务：`task_20260725_042005_7f84894b`

- **现象 1：改包发送成功，但消息进错会话（一直在「脱飘」）**
  - **根因**：收件人由 protobuf 消息体 **f1=`conversation_id`**（`0:1:uidA:uidB`）决定，只改 text 不换 cid。
  - **解法**：`--to` 解析后 `rebuild_send_body(..., conversation_id=...)`；local 读 `contacts_cache.json`。

- **现象 2：模板改包报结构异常 / 特征对不上**
  - **根因**：`Network.getRequestPostData` 落盘偶发 **base64 文本**，被当二进制读。
  - **解法**：`as_bytes_maybe_b64()`；合法模板应接近 `\x08d` 且含 `hash.`。

- **现象 3：`SEND_MESSAGE_STATUS_INVALID_PARAM`**
  - **根因**：坏模板或 webid/device 与 identity 体系不一致（如误用 tea webid）。
  - **解法**：webid 用 Passport `identity_device_id`；browser 重抓活体模板。

- **现象 4：以为 `identity_security_token` / `hash.Gnrq` 可本地算法生成**
  - **根因**：二者是**服务端签发票据**；ticket 在 `web_protect` localStorage。
  - **解法**：Cookie HTTP 刷 identity；ticket 从 export/模板缓存；勿当 a_bogus。

- **现象 5：Python 带 Cookie 搜用户 / 打开 `/user/{抖音号}` 拿不到 uid**
  - **根因**：反爬 `_$jsvmprt` 空壳页 / `UserId不合法` / 空 user_list；无浏览器指纹。
  - **解法**：CDP 已登录页：昵称点会话或主页点「私信」；结果写入 contacts。

- **现象 6：`openImConversation(昵称/unique_id)` 无效果**
  - **根因**：该函数只接受 **conversationId 字符串**，不是昵称。
  - **解法**：先解析出 `0:1:...` 再调用 / 改包。

- **现象 7：conversation-item 上扫 React fiber 没有 cid**
  - **根因**：列表项 props 不含 cid；cid 在发送按钮 `imStore.curConversationId`。
  - **解法**：点开会话后读 `.e2e-send-msg-btn` fiber → `imStore`。

- **现象 8：网页突然要过验证码，怀疑「注入了验证码」**
  - **根因**：风控——CDP 连点、短时间多次 imapi、浏览器外 Cookie 打接口；**不是** `final_capture` 下发验证码。
  - **解法**：人工过验证；降频；优先 `browser`；少用裸 HTTP；暂停自动化。

- **现象 9：同 client_message_id 重放返回 OK 但无新消息**
  - **根因**：幂等。
  - **解法**：每次新 UUID；真送达看 UI。

- **现象 10：页面卡死 / `ch_page_run_js` timed out**
  - **根因**：重页面或 full 注入；标签不在 www.douyin.com。
  - **解法**：`capture_profile=safe_capture`；`ImCdp` 选 douyin 标签。

---

## 2026-07-24 — 抖音评论协议爬取 / 本地签延伸踩坑（续）

> 正式案例与用法：`cases/douyin_comment_crawl/README.md`  
> 算法终版：`cases/a_bogus/README.md`  
> 脚本：`server/data/reverse_runs/task_20260723_061837_889ab753/repro/crawl_video_comments.py`

- **现象 1：把 `verify_sdenv_signature_complete` 截获的长串当成业务 `a_bogus`**
  - **根因**：截到的是 SDK **遥测 strData**（常见 `magic:538969122`），不是 query 上的业务 `a_bogus`。
  - **解法**：以活体插桩 **func 150 leave** 或 `sdenv_local_sign.sign_a_bogus` 输出为准；遥测串只能当补环境存活信号。

- **现象 2：把 VM func 107 当独立 `encrypt(url)`**
  - **根因**：107 是 **XHR 钩子**（拼 `a_bogus`/`msToken` 进 query），不是可单独调用的签名核。
  - **解法**：本地签补丁 `D()`，按指纹暴露 **func 150**，调用 `__dy_sign150(1,0,8, query, '', UA, 6241, 6383, ver)`。

- **现象 3：sdenv 里 stub XHR `send` 后整段永不返回 / Python `TimeoutExpired`**
  - **根因**：空壳 `send` **同步**触发 `onreadystatechange` → 业务重入死循环；真发 mssdk 也易挂死。
  - **解法**：回调改 `setTimeout(0)`；业务签走 fn150 直调，不要依赖 stub 下的真实 append。

- **现象 4：签脚本「超时失败」，最小 `console.log` runner 也要几十秒**
  - **根因**：仓库外 `sdenv-main` **冷 `require` ≈ 40–50s**，不是逻辑写坏。
  - **解法**：签超时给到 **≥150s**；接受评论爬取首页冷启动可到 ~2 分钟，后续页约 15–25s。

- **现象 5：`requests` 组 Cookie 头报 `UnicodeEncodeError: 'latin-1'...`**
  - **根因**：HTTP Header 必须 latin-1；抖音 Cookie 偶含中文等非 ASCII。
  - **解法**：组装 `cookie_str` 时跳过无法 latin-1 编码的项（`crawl_video_comments.py` 已做）。

- **现象 6：msToken 缓存总 miss，每次 `ms_via=local_random`**
  - **根因**：Python 3.10 `datetime.fromisoformat` 对部分带 `+08:00` 的写法解析失败，异常被吞。
  - **解法**：缓存统一写 UTC（`+00:00`）；读取兼容旧格式。真 token 优先浏览器 `localStorage.xmst`。

- **现象 7：以为 `comment/list` 必须带 query `X-Bogus`，或只要 a_bogus 不要 Cookie**
  - **根因**：旧双签印象；活体评论请求常**不带** query `X-Bogus`，但要登录 Cookie + `a_bogus` + `msToken` + `verifyFp`/`uifid`。
  - **解法**：以 `ch_listener_read` 样本为准；本版 secsdk 头未还原，实测仍可 `status_code=0`。

- **现象 8：短链 `v.douyin.com` 解析挂死 / 分享口令抽不出 id**
  - **根因**：短链跳转偶发极慢；口令是带文案的整段文本。
  - **解法**：短超时 + 失败时浏览器导航拿 `/video/<id>`；正则从口令抽 URL（脚本已支持）。

- **现象 9：想靠多进程并发狂签加速矩阵爬**
  - **根因**：单 Cookie + **每页 cursor 必重签**；硬并发易风控，且 Node/sdenv 更吃资源。
  - **解法**：先单号顺序 + 随机休眠；号池/常驻签程是下一阶段，不是硬并发。

- **现象 10：页面卡死仍用 `capture_profile=full` 强注**
  - **根因**：高侵入 Hook 触发 debugger/白屏/超时（见 AGENTS 注入降级规则）。
  - **解法**：立刻改 `safe_capture`；证据走 listener / `ch_injection_evidence`，不要只看 Console。

---

## 2026-07-24 — 抖音 a_bogus 逆向与 sdenv 沙箱补环境实战踩坑全纪录

- **现象 1：`sdenv` 补环境瞬间抛出 `ReferenceError: process is not defined` 导致 JS 执行中断**
  - **根因**：`sdenv-extend` 内部使用 `Proxy` 接管全局对象 `globalThis` / `window`。当 Webpack / 混淆代码检测 `process` 存在性时，Proxy 的 `get` 钩子由于未在 `target` 中找到该键，便主动抛出 `ReferenceError`，中断了后续 JS 的初始化链。这**并非** `bdms.js` 本身自带的反爬死循环，而是沙箱代理逻辑与浏览器真实表现的差异。
  - **解法**：通过 `sdenv` 的 `globals` 参数显式注入模拟的浏览器端 `process` 对象（typeof 为 object 但不包含 Node 特质）：
    ```json
    "globals": {
        "process": {"env": {}, "version": "", "platform": "browser", "versions": {}, "browser": True}
    }
    ```

- **现象 2：`core-js` Polyfill 在 Node.js V8 中触发 `TypeError: Cannot assign to read only property 'toString'`**
  - **根因**：`bdms.js` 依赖的 `core-js` 在初始化阶段会尝试重写内置函数的 `toString` 属性（如 `Function.prototype.toString`）。在 Chrome 浏览器的 V8 中该属性被允许重写，但在 Node.js 环境下 `Function.prototype.toString` 默认是不可写（`writable: false`）且只读的，导致强行赋值报 `TypeError` 崩溃。
  - **解法**：在 `bdms.js` 执行前注入 compatibility patch 脚本，利用 `Object.defineProperty` 强制将 `Function.prototype.toString` 的 `writable` 修改为 `true`：
    ```javascript
    try {
        var desc = Object.getOwnPropertyDescriptor(Function.prototype, 'toString');
        if (desc && !desc.writable) {
            Object.defineProperty(Function.prototype, 'toString', {
                writable: true, configurable: true, value: desc.value
            });
        }
    } catch(e) {}
    ```

- **现象 3：`sdenv_runner.js` 传入 `eval_expression` 被忽略，导致 `eval_result` 恒为 `None`**
  - **根因**：查看 `server/sdenv_runner.js` 源码发现，`main()` 函数内部仅执行 `vm.runInContext(input.js)`，完全未实现 `input.eval_expression` 的读取和评估逻辑。传参 `eval_expression` 是无效的。
  - **解法**：不要依赖 `eval_expression`，而是在 `input.js` 末尾直接拼接测试与检查逻辑，把 Post-Execution 的验证表达式（如枚举新增 `window` 键、尝试调用 `window.bdms.init()`）直接作为 JS 的一部分一同传入执行。

- **现象 4：`try/catch` 包裹 `bdms.js` 导致 `sdenv` 误报 `ok: true`（假成功）**
  - **根因**：为了捕获长堆栈和错误，如果把整个 `bdms.js` 简单放入 `try { ... } catch(e) { console.log(...) }`，`sdenv_runner` 在 `runInContext` 时便不会收到未捕获异常，从而将响应标记为 `ok: true`。但此时 `window.bdms` 可能因中途崩溃并未成功挂载。
  - **解法**：在 auto-env 或单元测试判断中，**禁止仅凭 `ok: true` 判定成功**，必须验证业务挂载点（如 `window.bdms` 是否存在、或是否输出了特定的成功的 `CRAWLER_FOUND` / 自动化提取的 `a_bogus` 结果）。

- **现象 5：DrissionPage `page.cookies` API 调用报错 `AttributeError: 'function' object has no attribute 'as_dict'` / `TypeError: got an unexpected keyword argument 'as_dict'`**
  - **根因**：在不同版本的 DrissionPage 中，`page.cookies` 是一个直接调用的方法（`page.cookies()`），不带有 `as_dict()` 方法或 `as_dict=True` 关键字参数。当传入不支持的参数或将其当属性访问时会报错。
  - **解法**：采用兼容性高的类型判断与字典转换写法：
    ```python
    cookies_val = page.cookies()
    if isinstance(cookies_val, dict):
        browser_cookies = cookies_val
    elif isinstance(cookies_val, (list, tuple)):
        browser_cookies = {item.get('name'): item.get('value') for item in cookies_val if isinstance(item, dict)}
    else:
        browser_cookies = {}
    ```

- **现象 6：活体调用搜索接口返回 `status_code: 2483, 请先登录`**
  - **根因**：抖音搜索等敏感 Web API 对匿名无 Cookie 或未登录凭证的请求进行了风控升舱，即便签名 `a_bogus` 正确，依然会校验账号 Token 绑定态。
  - **解法**：在验证纯加签算子有效性时，应使用不需要强制登录态的公开接口（如 `/aweme/v1/web/tab/feed/` 推荐流），或者先登录获取真实 session 后再调用搜索接口。

---

## 2026-07-23 — Vue3 框架登录页纯 JS 赋值未发包与动态 Header/Body AES 加密闭环

- **现象**：在私募排排网（`dc.simuwang.com`）等基于 Vue3/Nuxt3 搭建的页面上，使用 `ch_page_run_js` 执行 `input.value = '13800138000'` 给表单赋值后点击“登录”，页面没有向后端发送 POST 请求（监听器日志无包）。
- **根因**：Vue3 的双向绑定受 `_valueTracker` 机制管理，直接修改 DOM input 的 `.value` 属性不会触发 Vue 内部的 Reactive State 更新，提交表单时组件校验仍认为输入框为空，从而静默拦截了发包逻辑。
- **解法**：
  1. 自动化赋值脚本需完整派发 `input` 与 `change` 事件并刷新 tracker：
     ```javascript
     function triggerInput(el, val) {
         if (!el) return;
         el.value = val;
         let tracker = el._valueTracker;
         if (tracker) tracker.setValue('');
         el.dispatchEvent(new Event('input', { bubbles: true }));
         el.dispatchEvent(new Event('change', { bubbles: true }));
     }
     ```
  2. 此类复杂页面可配合手动操作触发表单，一旦触发后：
     - 用 `ch_fetch_url(grep="...")` 服务端拉取主 bundle（如 `AvPs6KuV.js`），找到 `uXpFetch` 框架与 `Crypto.encrypt` 函数；
     - 发现 Header 中的 `X-Requested-With` 来源于 Cookie `8hIn9IA` 的密文；
     - 结合 `ch_breakpoint_set_xhr` + `ch_debugger_get_scope` 获取运行时密钥 `814a43980a8952c35b75d1502c61ca84` 及 IV `5b75d1502c61ca84` 完成 AES-128-CBC 复现。

---

## 2026-07-22 — 真实验证码页面的只读取证边界

- **现象**：JNU CAS 页面可能同时展示网易易盾验证码和密码加密表单；房天下登录页可能只先展示“请完成安全验证”，滑块内容尚未进入稳定 DOM。
- **根因**：登录表单、验证码组件和第三方安全验证层是不同证据源；脚本加载、页面可达或拖拽 API 返回成功，都不能单独证明验证码通过。
- **解法**：真实案例先只做页面身份、脱敏 DOM/脚本指纹和截图取证；`inspect/plan` 的 `action_executed` 必须为 false、`verdict` 保持 `pending/uncertain/unsupported`。只有当前 attempt 绑定的显式验证标记才允许 `ok=true`，不要为了显露控件而在 dry-run 中 hover、刷新或拖动。

## 2026-07-22 — 易盾滑块「拖完没松手自己回弹」（已修 CDP 松手）

- **现象**:`ch_captcha_solve` 滑块会动，但看起来没松手就弹回。
- **根因**:
  1. 仅改 ddddocr 缺口距离不够，松手链路才是主因。
  2. 易盾页上 `tab.ele` / Actions 常报 `element not found`（同数美），只能走 CDP 轨迹。
  3. 旧 CDP 轨迹终点立刻 `mouseReleased`，易盾常当成未松手/校验失败回弹；DrissionPage#569 也提到松手前需额外位移。
- **解法**:
  1. CDP 轨迹终点：**停顿 + 零位移 move → 再 mouseReleased**。
  2. Actions 路径同样加 `wait + right(0) + release`（其它站点可用）。
  3. 易盾拖前再 hover，防触发式拼图在 OCR 期间收起；手柄固定 `.yidun_slider`。
  4. 重启 `server.py` 后看 diagnostics 含 `yidun_cdp_trajectory_release_fix`。

---

## 2026-07-22 — 暨南 CAS 易盾滑块：通用 capture 失败 / 一刀切拖拽不过（已修快路径）

- **现象**:`ch_captcha_solve` 能找到候选但 capture 无 `drag_distance`；手工算出约 91px 后 `page_drag_element` 接口 ok，但 `NECaptchaValidate` 仍空。
- **根因**:校园 CAS URL 无易盾域名，通用 session capture 易失败；易盾校验分段 pointer 轨迹，不是单次整体偏移。
- **解法**:
  1. DOM probe（`img.yidun_bg-img` / `.yidun_jigsaw` / `.yidun_slider`）+ **易盾快路径**（CDP 取图 → ddddocr → 轨迹拖拽）。
  2. **缺口距离直接用 `ddddocr.slide_match` 的 `target[0]`**，不做 display/natural 缩放。
  3. 跳过易卡死的 CaptchaExecutor verify（同数美）。
  4. 改 `auto_domain.py` / `auto_bridge.py` 后须**重启 `server.py`**。
  5. 单元测试：`tests/server/test_captcha_auto_domain.py`（`recognize_yidun_fast` mock）。

---

## 2026-07-21 — 数美页 `ch_captcha_solve` 卡 120s / tab.ele 找不到（已修）

- **现象**:数美注册页 dry_run 跑满超时；`tab.ele('.shumei_captcha_slide_btn')` 报找不到，但 JS `querySelector` 能找到。
- **根因**:DrissionPage `run_js`/`ele` 在该页不可用；Detector 全表 `eles` 默认 10s；session 扫描再叠加卡死。
- **解法**:
  1. Detector `eles(..., timeout=0)` + 数美 rule。
  2. Hunter `patch_tab_run_js_via_cdp`；数美走 **CDP 取 bg/fg URL + ddddocr** 快路径。
  3. 求解前 `page_hover` 显露拼图；锁外识别避免卡死浏览器 API。
  4. 重启后端；MCP 需 Reload 才见 `ch_captcha_solve`。

---

- **现象**:调用 `/api/captcha/solve` 后，`ch_page_get_info` 等全部超时；solve 本身也 120s 无响应。
- **根因**:`solve_domain_via_registry` / `solve_via_registry` 在 `registry._lock` 内跑完整 OCR/DOM，锁被长时间占用。
- **解法**:锁内只 `_resolve_tab`；识别与拖拽移出锁。重启后端生效。MCP 侧若无 `ch_captcha_solve`，需 Reload sidecar。

---

- **现象**:以前要设一堆 `CRYPTO_HUNTER_CAPTCHA_*` 才能调 `ch_captcha_solve`。
- **现状**:默认已开启 domain 求解 + 允许拖拽；包路径自动探测 `third_party` / `F:\AICode\AI-Reverse\网页\auto_yanzhengma`。
- **用法**:连上浏览器后直接 `ch_captcha_solve()`；先试可加 `dry_run=true`。
- **关闭**:`CRYPTO_HUNTER_CAPTCHA_ENABLED=0` 或 `SOLVER=off`；禁止拖拽：`ALLOW_AUTO_EXECUTE=0`。
- **仍需**:`pip install -e ".[captcha]"`（ddddocr 等）；改 MCP 后 Reload sidecar。

---

## 2026-07-21 — `ch_page_hover` 报 `name 'text' is not defined` / `tab.actions` 悬停超时（已修）

- **现象**:
  1. MCP 调 `ch_page_hover(selector=".shumei_captcha_slide_btn")` 立刻失败：`name 'text' is not defined`。
  2. 后端直调 `/api/browser/page/hover` 且 `human_like=false` 时偶发「同步操作超时 30s」或耗时 12~22s 才落到 CDP。
- **根因**:
  1. sidecar 里 `ch_page_hover` 曾错接到 `/api/browser/page/input`，并把未定义的 `text` 塞进 body。
  2. DrissionPage 内置 `tab.actions` 会等待页面文档加载；卡顿页上易挂死。官方用 `Actions(tab)` 则不等待。
  3. `tab.ele()` 找不到时返回 **`NoneElement`**：`elem is not None` 仍为 True，但 `bool(elem)` 为 False；误判后对假元素 `scroll.to_see` / `move_to` 会长时间挂起。
- **解法（已落地）**:
  1. `ch_page_hover` 改调 `POST /api/browser/page/hover`；拟人失败回退 CDP JS。
  2. `_get_actions` 优先 `Actions(tab)`；水平拖拽主轴用 `hold → right/left → release`。
  3. 统一 `_is_real_ele(elem)`（`bool(elem)`）判断真实元素，避免 NoneElement 假阳性。
  4. **改 `mcp_service.py` 后必须在 Cursor MCP 面板 Disable→Enable（或 Reload Window）**；只重启 `server.py` 不够。当前若仍报 `name 'text' is not defined`，说明 sidecar 进程还是旧代码。
  5. 验收：`tests/server/test_mcp_page_hover_wiring.py`；数美注册页 hover 后拼图显露。

---

## 2026-07-21 — `ch_page_scroll` 立刻 500：`timeout_sec` 重复传参（已修）

- **现象**:调用 `ch_page_scroll(scroll_y=...)` / `scroll_to_bottom=true` 立刻失败；表面文案像超时，summary 实为 `__main__._run_sync_with_timeout() got multiple values for keyword argument 'timeout_sec'`。
- **根因**:`api_browser_page_scroll` 把方法参数 `timeout_sec` 与 `_call_browser_method(..., operation_timeout_sec=...)` 一起塞进 `_run_sync_with_timeout(method, ..., timeout_sec=operation_timeout_sec, **kwargs)`，kwargs 里再带同名 `timeout_sec` 撞名。
- **解法（已落地）**:`_call_browser_method` 先闭包 `method(*args, **kwargs)`，再只把 `operation_timeout_sec` 交给 `_run_sync_with_timeout`。临时绕过：用 `ch_page_run_js` 执行 `window.scrollBy(0, N)` 触发无限流加载。
- **验收**:头条首页下滑后 listener `q=list/feed` 可见带 `a_bogus`/`msToken` 的 XHR（例 `5656.1872` / `5656.1917`）。

---

## 2026-07-20 — Debugger 动态断点链路不稳定（已修）

- **现象**:
  1. `set-breakpoints` 返回 `ok:true` 但 `set_count=0`（尤其 urlRegex 含 `\\.js` 或同列反复 set/remove）。
  2. `wait_paused` 反复返回同一旧快照；或导航噪声抢走目标断点。
  3. `evaluate_expressions` 多条结果互相覆盖；大对象被截成 1000 字符。
  4. `pending-scopes` 一读就清空，证据丢失。
- **根因**:
  1. CDP 对部分 `\.` 转义 urlRegex 返回空 `breakpointId`；失败未透出 errors。
  2. `wait_paused` 每轮 `start_seq=pause_sequence-1`，永远命中队列最新旧快照。
  3. `custom_results` 用表达式前 100 字符当 key。
  4. `get_pending_scopes` 只支持消费型读取。
- **解法（已落地）**:
  1. `_normalize_url_regex`：`\.` → `[.]`；列号失败自动回退 `column=0`；`set_count=0` 时 `ok=false` + `errors[]`。
  2. `wait_paused` 支持 `after_pause_seq` / `reason_contains` / `breakpoint_id`；HTTP 外层固定 baseline；默认不再反复吐旧快照。
  3. `/*label*/` 唯一 key + `custom_expressions`；序列化上限 8000。
  4. `pending-scopes?consume=false` peek；新增 `clear-pause-queue` / `resume-until-idle`。
  5. 验收：`tests/server/test_debugger_stability_fixes.py`；活体冒烟 `tests/server/smoke_debugger_stability_live.py`。
  6. MCP：`ch_debugger_wait_paused` 新增过滤参数；`ch_debugger_clear_pause_queue` / `ch_debugger_resume_until_idle` / `ch_debugger_pending_scopes`。
  7. **2026-07-20 续**：`set_breakpoints` / `set_xhr_breakpoint` 前 `_ensure_debugger_ready`（CDP 探活 + Debugger.enable）；`eval_results.eval_warnings` 检测 `$wV`/`NO_wV`；XHR 断点默认拒绝 `behavior_report` / `cactus.jd.com`（`allow_hook_pollution=true` 可强制）。

---

## 2026-07-19 — 文档导航登录 POST 经 302 后 listener 丢 body

- **现象**:清华身份页等表单 `POST /security_check` → 302 → `GET /f/login`；`ch_listener_read` / `ch_extract_request` 只剩最终 `GET`，`post_data` 为空；`ch_cipher_search` 能在 `redirectResponse.url` 看到 `security_check`。
- **根因**:CDP 重定向链复用同一 `requestId`；续段 `Network.requestWillBeSent` 覆盖了首跳的 `url`/`method`/`postData`。另：`filters.url_include` 曾未归一成 `url_contains`。
- **解法（已落地）**:
  1. 续段前写入 `redirect_chain` + `original_*`；空 `postData` 不覆盖已有 body。
  2. `target_hit` 对各跳取 OR；过滤器支持 `url_include` 别名，并匹配 `redirectResponse.url`。
  3. lean/headers/extract 暴露 `original_request_url` / `original_method` / 保留的 `post_data`。
  4. 验收：`tests/server/test_browser_runtime_listener.py::ListenerRedirectPreserveTests`。

---

## 2026-07-19 — CallMcpTool 超时但 GetMcpTools / 本地 stdio 正常

- **现象**:Cursor Agent 调 `ch_health` / `ch_task_create` 报 `Timed out waiting for connection to user-crypto-hunter-lite::mcpScope:...`；`GetMcpTools` 仍显示 ready，但工具描述卡在旧英文（如 `return cleanup state`）；本机用 newline-JSON 直连同一 `mcp_service.py` 的 initialize / tools/list / tools/call **全部成功**。
- **根因**:
  1. Agent 走的是 Cursor 内部 MCP 租约/IPC；工具目录可读缓存（`~/.cursor/projects/.../mcps/.../tools/*.json`），真实 `tools/call` 仍要活 stdio 会话。
  2. `mcp.json` 用相对 `python` + **中文路径** args（`F:\\AICode\\逆向工具\\...`），Windows 下易与 Cursor MCP utility/agent 通道打架；工作区日志里也有 `cwd=<empty>`。
  3. stdio 协议是**换行 JSON**；若 httpx/MCP INFO 打到 stdout，会污染管道（本仓库已强制 stderr + quiet）。
- **解法（已落地）**:
  1. `~/.cursor/mcp.json` 改为绝对 Python312 + ASCII 启动器 `%USERPROFILE%\\.cursor\\crypto-hunter-mcp\\run_mcp.py`（内部 chdir+runpy 到真实 `server/mcp_service.py`），并设 `PYTHONUTF8` / `CRYPTO_HUNTER_MCP_STDIO_QUIET=1`。
  2. `mcp_service.main` 增加 `_configure_stdio_runtime`：UTF-8 + 日志只进 stderr；可选 `--transport streamable-http --port 27184` 作 HTTP 兜底。
  3. User Settings 打开 `cursor.agent.legacyMcpMode: true`（Cursor 已知 agent MCP 通道兜底）。
  4. 改完后在 Cursor MCP 面板 **Disable→Enable** `crypto-hunter-lite`（或 Reload Window）；不要只重启后端。
  5. 本地验收：`python %USERPROFILE%\\.cursor\\crypto-hunter-mcp\\run_mcp.py --help` 后，用 newline-JSON 调 `tools/call ch_health` 应返回 `health_level=healthy`。

---

## 2026-07-19 — 解混淆可读性不等于线上算法（已加活体闸门）

- **现象**：雪球 `jquery.deob.js` 的 `kf.z` 能读出四段字符串拼接，但活体 `md5__1038` 是七段；将前者当公式会生成“代码可读、协议错误”的假结论。
- **根因**：静态解混淆只能恢复候选路径，无法证明该脚本是目标请求实际执行路径，也无法自动补齐运行时闭包、Cookie 与设备状态。
- **解法**：`ch_deobfuscate_js` 现在默认返回 `live_validated:false`、`source_provenance`、`deobfuscation_quality`、`conflict_warning`。有活体 I/O 时传 `live_evidence={js_code, eval_expression, expected_output}`，生产结论改用 `live_evidence.cases` 至少两条样本；只有全部样本通过 `live_validation.status == "validated"` 才可采信，任一输出不符会标记 `rejected_by_live`。不要直接执行整包解混淆源码，须提供最小候选复现代码。

---

## 2026-07-18 — 雪球 md5__1038 实战：工具问题总册（修代码用）

- **现象**:瑞数站上 Debugger pause 洪水、挑战期 listener 原型 hook 易卡页、匿名 WAF 脚本不在 `document.scripts`、deob 四段式与活体七段不符、断点 locals 读不出但 condition 侧写可以。
- **根因**:见专册（按 Issue 拆开，含复现、仓库改动点、验收标准）。
- **解法 / 专册**:[`scratch/xueqiu_md5_1038_20260718/TOOLING_REVIEW.md`](../scratch/xueqiu_md5_1038_20260718/TOOLING_REVIEW.md)
  - 搜 `XQ-TOOL-01`…`XQ-TOOL-10`
  - P0：`01` side_capture、`02` 挑战期禁原型 hook、`03` `ch_find_runtime_script`
  - **不要**把该专册里的算法段落当「还没解」——签名已离线；专册只指导**修工具**。

## 2026-07-19 — 挑战页监听与运行时脚本定位的通用修复

- **现象**:验证/反爬挑战页中启用 listener 的 XHR/fetch 原型 hook 后，页面可能持续 loading；关键 WAF 源码是匿名动态脚本，`document.scripts` 找不到；普通断点又会被 `debugger;` 噪声淹没。
- **根因**:基础 `safe_capture` 的降级不覆盖 listener 自己的新文档原型注入；DOM 脚本枚举不等于 Debugger 运行时脚本表；需要局部变量时不应让目标执行真正暂停。
- **解法**:
  1. `ch_listener_start(hook_mode="auto")` 默认只读探测验证态；命中或探针异常时返回 `effective_hook_mode="cdp_only"`，仍保留 CDP Network 事件，禁止强制 `prototype`。
  2. `ch_find_runtime_script(marker=...)` 从 Debugger 缓存的实际源码定位匿名/eval/blob 脚本，并返回 `script_id`、1-based `line_number`、0-based `column_number`；需在脚本运行前启动 Debugger。
  3. `ch_debugger_side_capture(...)` 通过返回 `false` 的条件断点把表达式结果写入受限页面缓存，命中点不暂停；无关 `debugger;` 继续由自动放行策略恢复。

## 2026-07-17 — 页面卡死/无限 debugger 时必须切换 safe_capture

- **现象**:页面白屏或持续 `loading`，Console 被注入日志刷屏，反复出现 `debugger;`，`ch_page_run_js` 超时，甚至 MCP/后端也变慢；手动打开 DevTools 点几次 Resume 后页面才恢复。
- **根因**:强风控页面会校验 AMD/WAF/响应链和原生函数身份；`full` 注入的页面级原型改写、Response 解码包装、Webpack/DOM/Worker 扫描可能与站点初始化竞争，站点自身 debugger 暂停又会放大卡顿。
- **解法（AI 编辑器强制顺序）**:
  1. 第一次恢复必须调用 `ch_cdp_start(..., include_base_script=True, capture_profile="safe_capture")`；已有浏览器优先 attach，不要在同一故障实例上继续 full 强行注入。
  2. 网络证据用 `ch_listener_start` → `ch_listener_read`/`ch_extract_request`，注入证据用 `ch_injection_evidence` → `ch_get_entry` → `ch_get_entry_context`；safe_capture 关闭的是 Console 回显，不是日志采集。
  3. `safe_capture` 稳定后仍缺少运行时证据，再用隔离浏览器实例启用 `capture_profile="full"`。

## 2026-07-16 — ch_sdenv_verify_code 曾是「幽灵工具」（文档有、MCP 无）

- **现象**:`ch_list_recommended_tools` / `mcp_usage.md` / `next_actions` / capabilities 都推荐 `ch_sdenv_verify_code`，调用却报 `not registered`；AI 只能改用 `ch_sdenv_run_code` 或直接打 HTTP。
- **根因**:
  1. 后端 `/api/sdenv/verify-code` 一直存在，但 `mcp_service.py` **从未定义** `def ch_sdenv_verify_code`。
  2. `denied_routes` 又把该路由禁止自动生成薄封装（假定「已有手写工具」），缺口无法被 auto-routes 补上。
  3. 旧 prompt 还写成 `ch_sdenv_verify_code(code=...)`，真实参数名是 **`js_code`**。
- **解法（已修）**:
  - 手写 `@mcp.tool`：`ch_sdenv_verify_code` → `POST /api/sdenv/verify-code`（含 `super_env` / `auto_fix` / `max_retries`，`payload.code` 兼容映射到 `js_code`）。
  - 与 `ch_sdenv_run_code` 分工写进 `mcp_tool_guide` / `mcp_usage.md`：verify=比对+可选修码；run=单次执行。
  - 重启 MCP sidecar 后 `list_tools` 应能看到该工具名。

## 2026-07-16 — ch_page_run_js 可靠性增强（大结果落盘 + json 模式 + 超时明确化）

- **背景**:之前 `ch_page_run_js` 长返回值被序列化吞成 `result:null`、超时也返回 `null`、且返回样板（browser/tab 全量快照）噪音大。
- **已修复（后端 + MCP 双层，已真实页面验证）**:
  1. **大结果自动落盘**:执行结果序列化后 > 16KB，自动写入 `server/data/run_js_dumps/runjs_<ts>_<rand>.json`，响应只回 `result_stashed=True` + `result_file`（绝对路径）+ `result_preview`（前 512 字符）+ `result_bytes`，彻底告别「大对象被吞成 null」。
  2. **`return_mode='json'` 模式**:`ch_page_run_js(code=..., return_mode='json')` 会在页面内 `JSON.stringify` 最终值后再返回，后端解析回对象并视情况落盘。用于规避 CDP `returnByValue` 对复杂/大对象静默丢值（等价于以前手搓 `window.__x = JSON.stringify(...)` 再读，但现在内置且更稳）。
  3. **读回工具**:`ch_read_run_js_result(file=<result_file>)` 读取落盘文件（仅接受文件名，路径穿越安全，自动取 basename）。
  4. **超时明确化**:JS 执行超时（含 DrissionPage/CDP 超时）现在返回 `{ok:False, timed_out:True, error:"...超时..."}`，**不再是静默 `result:null`**。
  5. **样板精简**:run-js 响应不再带 browser/tab 全量快照，仅留 `browser_id`/`status` 与 `tab_id`/`title`/`url`。
- **用法示例**:
  - 大对象 / 复杂结果：`r = ch_page_run_js(code="getHugeThing()", return_mode="json"); if r.get("result_stashed"): full = ch_read_run_js_result(file=r["result_file"])`
  - 超时兜底：`timeout_sec` 设大些；若仍超时，看 `timed_out` 字段区分「真超时」与「逻辑返回 null」。

## 2026-07-16 — Steam 登录公钥获取被风控（接口已换 + 严格 CORS）

- **现象**:想拿真实 RSA 公钥做本地复现。后端 `httpx`(带 session cookie)请求、页面内 `fetch(credentials:'include')`、`$J.ajax` 全被 Akamai 拦——重定向回登录页 HTML 或 `Failed to fetch`,拿不到 JSON。
- **根因**:
  1. 旧接口 `/login/getrsakey/` 已被新版 `IAuthenticationService/GetPasswordRSAPublicKey/v1/?account_name=...` 取代（新版 React 登录页，全局 `CLoginPromptManager`，输入框 id 是 `«r4»`/`«r5»` 这类 React 生成值）。
  2. `api.steampowered.com` 与 `store.steampowered.com` 是**同站跨子域**，公钥接口配了 CORS 白名单，但只接受「不携带凭证」的请求；`credentials:'include'` 触发更严格 CORS（需服务端回 `Allow-Credentials`）→ 被拦。
- **解法（经 MCP 在页面上下文内完成，最稳）**:
  - `ch_page_run_js`（`as_expr=true`，`args` 注入 account）执行：
    `fetch('https://api.steampowered.com/IAuthenticationService/GetPasswordRSAPublicKey/v1/?account_name='+$args.acct)` —— **默认 credentials，不带 `include`**。
  - 返回真实 RSA-2048 公钥：`publickey_mod`（512 hex）、`publickey_exp`（`010001`）、`timestamp`。
  - 等价做法：先 `ch_listener_start` → `ch_page_navigate` 登录页 → 填表 → `ch_page_click`（文本「登录」）→ `ch_extract_request` 抓 Steam 原生发起的 `GetPasswordRSAPublicKey` / `PollAuthSessionStatus` 真实请求（落盘在 `server/data/listener_dumps/`）。
- **验证**:页面内用真实公钥 `RSA.getPublicKey(mod,exp)` + `RSA.encrypt(pw,pub)` 算出 Steam 接受的 `encrypted_password`（344 base64 = 2048-bit）。算法 = 标准 RSA PKCS#1 v1.5，与本地复现脚本完全等价。

## 2026-07-16 — MCP 工具报 "tool does not exist or is not registered"

- **现象**:连续调用 `ch_page_run_js` 等报该错，即便之前能用。
- **根因**:MCP sidecar（stdio）与后端 `server.py`（127.0.0.1:27183）连接异常 / sidecar 抖动。
- **解法（按项目安全顺序重启后端，不要批量杀进程）**:
  1. `netstat -ano | findstr :27183` 拿 PID。
  2. `Get-CimInstance Win32_Process -Filter "ProcessId=<pid>"` 确认命令行是本项目 `server.py`。
  3. `taskkill /PID <pid> /F`。
  4. 用 **venv** 重启（系统 Python310 缺 uvicorn）：`d:\python_work\venv\Scripts\python.exe server.py`（后台重定向日志）。
  5. 后端 `LISTENING` 恢复后 MCP 通道**自动重连**，无需重启 IDE 里的 MCP server。
- **注意**:重启后端会重置浏览器会话，需重新 `ch_page_navigate`。
- **注意（新增 MCP 工具 / 改了 mcp_service.py 后）**:若报 `not registered` 的是一个**新工具**（如本次新增的 `ch_read_run_js_result`，或 `ch_page_run_js` 新增的 `return_mode` 参数），光重启后端**不会**让旧 sidecar 暴露新工具定义——必须**在 IDE 里重载（restart）该 MCP server**（sidecar 重新 import `mcp_service.py`）。后端自动重启只解决「后端挂了」型 not registered；「代码改了但 sidecar 没重载」型需手动重载 MCP server。

## 2026-07-16 — ch_page_run_js 返回 result:null 但 ok:true

- **现象**:代码明显执行了（耗时数秒），但 `result` 是 `null`，无 `error` 字段。
- **根因（两种）**:
  1. 返回值序列化丢失：长字符串 / 大对象经 CDP `Runtime.evaluate` 返回时可能被吞。
  2. `as_expr=false`（语句模式）**不注入 `$args`** → 代码里用 `$args.xxx` 直接 `ReferenceError: $args is not defined`（被 try/catch 捕获后返回 JSON，但整体返回值仍可能 null）。
- **解法（已内置修复，优先用内置）**:
  - 大结果 / 复杂对象：直接 `ch_page_run_js(code=..., return_mode='json')`。后端会把 > 16KB 结果自动落盘到 `server/data/run_js_dumps/`，回 `result_stashed=True` + `result_file`，再用 `ch_read_run_js_result(file=...)` 读全量。等价于以前手搓 `window.__x = JSON.stringify(...)`，但现在内置且更稳。
  - 需要结构化参数时务必 `as_expr=true` + 传 `args={...}`，在 code 里引用 `$args`（现在 `args` 注入与 `return_mode` 互不冲突）。
  - 同步函数不要用 `await_promise=true`（避免等待未 resolve 的包装返回 null）。
  - 若返回 `result_null:True`：是逻辑真的返回了 null/undefined，不是被吞；若想要大结果请用 `return_mode='json'`。
  - 若返回 `timed_out:True`：是真超时，调大 `timeout_sec`，不要当 null 误判。

## 2026-07-19 — ch_page_run_js：IIFE + return_mode=json → result undefined

- **现象**:`ok:true`，`result` 为 `{type:"undefined"}` / 空，代码其实跑过。
- **根因**:旧版 json 包裹把已是 IIFE 的 code 再塞进 `(function(){ IIFE })()`，内层执行了但**没有 return**，`__r === undefined`，`JSON.stringify(undefined)` 也是 `undefined`。
- **解法（已修 sidecar）**:
  - 表达式 / IIFE（以 `(` 开头）改为 `const __r = (code); return JSON.stringify(__r ?? null);`
  - 多语句仍走内层 function，**必须自己写 `return ...`**
  - 推荐写法：`return_mode="json"` + `code="(() => ({a:1}))()"` 或 `(() => { const o={a:1}; return o; })()`
  - 工具描述与 `ch_list_recommended_tools` / `ANTI_PATTERNS` 已同步这条规则；改完需**重载 MCP sidecar** 才能看到新 description。

## 2026-07-22 — ch_page_run_js：async/await + return_mode=json → result={}

- **现象**:`(async () => { ... return obj })()` 配 `return_mode=json` 得到空对象 `{}`。
- **根因**:旧版同步包裹 `JSON.stringify(Promise)` → `"{}"`，再被解析成 `{}`。
- **解法（已修）**:检测到 `async`/`await` 时改为 `(async () => { const __r = await (...); return JSON.stringify(__r ?? null); })()`，并强制 `await_promise=true`。不必再手写 `.then` + `window.__x`。

## 2026-07-22 — ch_search_loaded_scripts：total_scripts=0

- **现象**:页面已加载大量脚本，但搜索返回 `total_scripts=0` / `matches=[]`。
- **根因**:只依赖 `Debugger.scriptParsed` 索引；页面先于 `Debugger.enable` 加载时 Chrome **不会重放**已解析脚本事件，索引为空。
- **解法（已修）**:索引为空时自动枚举 `document.scripts`，外部脚本由服务端拉源码搜索；返回 `fallback_used=true`，命中带 `source=runtime_ext|runtime_inline`。合成 `script_id` 不能直接 `ch_script_get_source`，请用 `script_url` + `ch_fetch_url`。

## 2026-07-16 — 浏览器 JS 大数运算慢触发 run-js 超时

- **现象**:`ch_page_run_js` 跑 RSA-2048 素数生成，25s 后返回 null。
- **根因**:纯 JS BigInt 做 Miller-Rabin + 2048-bit 素数生成超过后端 run-js 超时。
- **解法**:等价性证明用 **RSA-1024** 自生成测试密钥对即可（算法相同，PKCS#1 v1.5 与密钥长度无关）；或显式设 `timeout_sec`（如 45）。

## 2026-07-16 — BigInt 与 number 混用报错

- **现象**:`TypeError: Cannot mix BigInt and other types`。
- **根因**:扩展欧几里得算法里 `e = 65537`（number）与 BigInt 做 `%` / `/` 运算混用。
- **解法**:指数直接用 BigInt 字面量 `65537n`；欧几里得全程用 BigInt 除法 `a/b` 与取模 `a%b`。

## 通用 — PowerShell 下 Python 输出被吞

- **现象**:PowerShell 管道（`Out-String` / `Get-Content`）吞掉 Python print，退出码失真。
- **解法**:结果重定向到文件（`> file 2>&1`）用 `read_file` 读；或脚本内 `flush=True` 增量写盘；或绕过 stdout 直接写结果文件。

## 通用 — 后端必须用 venv 启动

- 系统 `C:\Users\er354\AppData\Local\Programs\Python\Python310\python.exe` **缺 uvicorn**；后端须用 `d:\python_work\venv\Scripts\python.exe server.py` 启动。
- 验证：`d:\python_work\venv\Scripts\python.exe -c "import uvicorn"` 应输出版本号（如 0.30.1）。

---

（新增踩坑请保持「现象 → 根因 → 解法」结构，追加在最上面并带日期。）

---

## 2026-07-31 sdenv 子系统修复与加强记录

### 现象 6：eval_expression 参数未生效

- **问题**：Python 端通过 IIFE 追加到 JS 末尾的求值表达式，依赖 console.log 标记回传结果，但在 try/catch 包裹场景下标记可能丢失
- **根因**：Node runner 未独立处理 `input.eval_expression` 参数，全靠 Python 端拼接 IIFE
- **解法**：两个 runner（sdenv_runner.js / sdenv_fallback_runner.js）新增显式 `eval_expression` 求值，结果通过 `result.eval_result` 结构化字段返回；Python 端 `_extract_eval_result()` 优先读该字段，其次兼容 console 标记
- **涉及文件**：`server/sdenv_runner.js`、`server/sdenv_fallback_runner.js`、`server/sdenv_code_verifier.py`

### 现象 7：try/catch 误报成功（ok:true 但业务对象未初始化）

- **问题**：将整段 JS 放入 try/catch 后，异常被吞掉，sdenv 返回 `ok:true` 但 `window.xxx` 未挂载
- **根因**：`success = ok and not error_msg` 判定过于宽松，未检查 eval 结果
- **解法**：当 `eval_expression` 被设置但 `eval_result` 为空且 logs 含 `eval:error:` 标记时，强制 `success=False`，`error_type="EvalError"`
- **涉及文件**：`server/sdenv_code_verifier.py` run_in_sdenv()

### 现象 8：Proxy 过度拦截 typeof process 抛 ReferenceError

- **问题**：sdenv-extend Proxy 对 globalThis 的 get 钩子，在检测 `process` 时直接抛错而非返回 undefined
- **根因**：外部 sdenv-main 的 Proxy 实现缺陷（不可直接修改）
- **解法**：在 `_build_super_env_bootstrap()` 中预注入 `process`（含 env/version/platform/nextTick/on/off/once/emit）和 `module/exports` 模拟对象，仅在 `typeof` 守卫下生效
- **注意**：UMD 打包库可能因此误走 CommonJS 分支，遇到"函数找不到"优先排查此处
- **涉及文件**：`server/sdenv_code_verifier.py` _build_super_env_bootstrap()

### 现象 9：冷启动超时（45s 默认不够）

- **问题**：sdenv-main 首次 require 需 40-50s，默认超时 45s 经常撞墙
- **解法**：默认超时调至 60s，subprocess 缓冲从 +30 调至 +45；超时错误增加"疑似冷启动超时"诊断提示
- **涉及文件**：`server/sdenv_code_verifier.py`

### 本次新增能力

- **智能 Runner 路由**：`_select_sdenv_runner(js_code, prefer="auto")` 根据代码特征自动选择 fallback（<1s 启动，适合无 DOM 轻量任务）或 sdenv-main（完整 JSDOM）
- **环境覆盖扩展**：按需注入 WebSocket/Worker/SharedWorker/IndexedDB 空壳，防止 ReferenceError
- **错误分类细化**：TypeError:NullPropertyAccess/NotAFunction、ReferenceError:MissingImport/MissingGlobal、SyntaxError:InvalidJSON/StrictMode 等 7 个子类型
- **三级输出校验**：精确匹配 → JSON 结构匹配 → 长度匹配（适配 RSA 等随机填充算法）
