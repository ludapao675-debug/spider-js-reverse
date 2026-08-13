# 拼多多移动端商品评论接口逆向（anti_content）

> 日期：2026-08-05 | 更新：2026-08-06 | 状态：**双交付成立**（①浏览器 RPC ②本地 tls-client `chrome_150` + sdenv 离线出票）

## 难点与踩坑速查（必读）

> 下面是终局结论；后文按时间线展开的日记里，早期「纯本地已证伪」已被 **2026-08-06 Phase1 / 换号离线** 推翻，以本节为准。

### 真正难点（54001 根因）

| # | 难点 | 结论 | 证据 |
|---|------|------|------|
| 1 | **TLS ClientHello 通道绑定** | curl_cffi 必 54001；`tls-client` **`chrome_150`** 可过。差在 JA4 / 签名算法 `0904–0906`，不是 token 算法 | `phase1_live_evidence.json`、`tls_fp_compare.json`、`phase0_tls_diff.json` |
| 2 | anti_content（`0as`）环境指纹 | 同 token：浏览器 fetch=200、curl_cffi=54001 → token 非纯自包含，但 **换对 TLS 栈后可本地发** | C1/C2、同 IP 金标准 |
| 3 | 账号级风控预算 | 本地 54001 **按账号×天累计**；达阈值后浏览器也会 54001 / `psnl_verification`；连续翻页间隔不够会「污染」浏览器 | 熔断纪律 ≤2 次/日；换号实验 page2→浏览器也 54001 |
| 4 | CDP 自曝 | a4 明文 `botD=bot:true` / `cdpProxy` / `hookFuncs` → 调试会话易升级验证（B 类风险，解释账号不稳，**不解释**同 token 双通道分裂） | `a4_decoded_payload.json` |

### 已排除的假难点（别再烧预算）

Cookie 缺项 · `verifyauthtoken`/`is_back`（必要非充分）· 公网 IP（同机对照）· 单靠 H2 SETTINGS（Akamai 可对齐仍拒）· 本会话 H3（reviews 为 h2）· t.gif 遥测伪造（能 200 但 reviews 仍拒）· 单独 a3/ae4/a4 注册（success≠放行业务）

### 工程踩坑清单

| 坑 | 现象 | 解法 |
|----|------|------|
| 旧 `tls_client==1.0.1` | 只有到 chrome_120，无 0904 | 用 **`tls-client-python`**，profile=`chrome_150` |
| `all_domains` Cookie | 非 latin-1 → curl/tls header 崩 | 只收 `pinduoduo.com` / `yangkeduo.com` 域 |
| `/api/browser/page/run-js` | 后端无 `$args` | 本地拼接 `const $args=...`（MCP 层才有注入） |
| sdenv 大 bundle | output 截断 / 超时 | cookie/`eval_expression` 取 token；timeout≥180；冷启动可 ~130s |
| webpack runtime 序列化 | `req.d` 引用私有 `i.o` | 自实现 d/n/r/nmd/o，勿序列化真 runtime |
| 解混淆漏检 | 字符串数组在文件尾 | 手动闭包 dump + 别名内联仍可静态审 a4 |
| a4「加密」误判 | 高熵载荷 | 剥 `0a` 前缀 → urlsafe_b64+zlib+TLV，非强加密 |
| 软拦形态 | `{"data":[]}` 无 error_code | ≠ 健康空页；连续 ≥2 次当软限熔断；与 54001 区分 |
| 连续翻页 | page1 过、page2 54001 | 间隔建议 **≥8–10s**；一触 54001 全停，勿用同号浏览器复测 |

### 交付形态（当前）

1. **纯本地（主）**：`--dump-assets` 一次 → `--offline` + sdenv 出票 + `chrome_150` 发包（`pdd_comments_local_tls.py`）
2. **多账号 GUI（编排）**：`python pdd_comments_gui.py` — Cookie 保存并激活 → 子进程调 CLI；翻页间隔随机 13–45s；出票**直调本地 sdenv**（`server/sdenv_runner.js` + Node，**不需要** 27183）。需已有 `webpack_45246_bundle.js`。调试回落 HTTP：`CRYPTO_HUNTER_SDENV_HTTP=1`。
3. **浏览器 RPC（托底）**：`pdd_comments_rpc.py` / Extension 骨架（消 CDP 自曝）
4. **换号离线实证（2026-08-06）**：uid=`8806803917643` page1 **n=10**；page2 54001 后账号加热 → `offline_new_account_evidence.json`

### 关联踩坑日志

跨案例可复用条目见 `docs/mcp_pitfalls.md`（verifyauthtoken、sdenv webpack、RPC `$args`、账号累计制、a4 结构、CDP bot 自曝等）。**chrome_150 突破 54001** 以本案 README 本节为权威。

---

## 目标

- 页面：`https://mobile.pinduoduo.com/goods_comments.html?goods_id=976241093684`
- 接口：`POST https://mobile.pinduoduo.com/proxy/api/reviews/{goods_id}/list?label_id=0&page=N&size=10&enable_video=1&enable_group_review=1&pdduid=...`
- 加密参数：`anti_content`（header `anti-content` + body 字段双带，约 550 字符，`0as` 前缀，URL-safe 自定义字母表）

## 请求结构（活体样本 request_id=19764.127/206）

```
Headers: anti-content: 0asWfq... (与 body 同值)
         content-type: application/json;charset=UTF-8
         cookie: api_uid/_nano_fp/jrpl/njrpl/dilx/PDDAccessToken/pdd_user_id/pdd_user_uin/pdd_vds
Body: {"name":"goodsCommentListAxios","anti_content":"0asWfq..."}
```

响应：`{data: [{comment,name,time,pictures,review_id,...}], exps, ...}`，被风控时返回
`{success:false, error_code:54001, verify_auth_token:"..."}`。

## 定位结论（定位门禁已过）

| 环节 | 位置 |
|------|------|
| 参数注入点 | `react_goods_comments_*.js`：`e.next=5,(0,q.g)(); l={name:"goodsCommentListAxios",anti_content:e.t0}` |
| 生成函数 | **webpack 模块 `45246` 导出 `g()`**（1069 个工厂中按源码指纹"获取风控参数"唯一命中） |
| header 复制 | `react_pdd_*.js` Axios 拦截器：`r["anti-content"] = data.anti_content` |
| SDK 本体 | `static.pddpic.com/assets-rcf/b9216582_*.js`（760KB 混淆，SubtleCrypto.digest(SHA-256) + 指纹上报 `xg/pfb/a3|a4` 换 `jrpl/dilx`） |
| 预签名池 | `localStorage['anti_pre_sig']`（5 条逗号分隔短签，RCF SDK 维护） |

## 实验记录（关键事实）

1. **重放不可行**：捕获的活体 anti_content，3 分钟后本地 curl_cffi(impersonate=chrome) + 全套 Cookie 重放 → 54001。
2. **秒级重放也不可行**：RPC 现场生成 token（<1s）立即本地发请求 → 仍 54001。同 token 在浏览器内 fetch 则通过（page=10 拿到 10 条评论）。→ **服务端校验绑定浏览器请求环境，token 本身不是纯自包含**。
3. **webpack runtime 可劫持**：`__LOADABLE_LOADED_CHUNKS__` + `Array.prototype.push` 探针捕获 `__webpack_require__`，`req(45246).g()` 可直调生成 token（~90ms）。
4. **频率红线**：短时间内多次生成/验证失败后，整个会话被重定向到 `psnl_verification.html`（安全验证页，需人工验证）。

## 复现文件

- `pdd_comments_local_tls.py`：**纯本地交付（chrome_150 + sdenv）**。一次性 `--dump-assets` 后，`--offline` 无浏览器翻页；`--token-only` 只测出票。用法：
  ```
  python pdd_comments_local_tls.py --dump-assets
  python pdd_comments_local_tls.py --offline --token-only
  python pdd_comments_local_tls.py --confirm-local --offline --pages 2 --start_page 45 --interval 5
  ```
- `pdd_comments_rpc.py`：浏览器内 fetch RPC（托底 / Extension 演进）。
- `phase1_utls_live.py` / `phase1_live_evidence.json`：V0=54001 / V1=200 判据证据。
- `repro.py` / `fast_replay.py`：curl_cffi 负向证据（勿再当交付跑）。
- `comments_local_881388350961_p43.json`：本地栈冒烟 20 条（page 43–44，浏览器出票时代）。
- `webpack_45246_bundle.js` / `session_offline.json`：离线出票资产（含 Cookie，勿提交远端）。

## 闭环验证结果（人工过安全验证后，2026-08-05 下午）

- 会话恢复：探针重装 `installed:45246`，page=11 探测 200 + 10 条（0.39s）。
- 多样本：page=12/13/14/15 全部 200 + 10 条/页，累计 40 条，单次 0.77~0.89s，限速 5s 下零风控。
- 结论：**本地复现以"浏览器内 fetch 闭环"形态成立**；纯本地发包路线已被实验证伪（环境绑定 token 必 54001）。

## 经验沉淀

- 后端 `/api/browser/page/run-js` 路由**不支持** `args` 注入（`$args` 替换只在 MCP sidecar 层）；本地直调该路由须自行拼接 `const $args = {...};` 前缀。
- 频率红线：连续失败请求会升级触发 `psnl_verification.html` 安全验证页；脚本须限速（≥3s）+ 风控熔断。

## sdenv 纯本地复现实验（2026-08-05 晚，local_repro_experiment.py）

回答"能否纯本地复现"的判据实验（风控预算 4 次请求内）：

1. **webpack 闭包整体搬运成功**：BFS dump 模块 45246 依赖闭包（362 模块 / 502KB）+ 自实现 mini webpack runtime（d/n/r/nmd/o 等价实现，勿序列化真实 runtime——内部引用私有变量 `i.o`）。
2. **sdenv 离线生成 token 成功**：bundle + super_env + 活体 Cookie 提交 `/api/sdenv/run-code`，生成合法 `0as` token（580~644 字符）。**token 计算层已被 sdenv 完全解决，无需手写补环境。**
3. **判据对照**（同一枚离线 token）：
   - C1 本地 curl_cffi(impersonate=chrome) + 全套 sec-*/UA 一致头 + 活体 Cookie → **54001 拒**
   - C2 同 token 浏览器内 fetch → **200 + 10 条**
4. **结论**：阻碍不在 token 计算，而在**服务端对请求通道的交叉校验**（浏览器内发即通过，本地全头一致仍拒）。剩余可疑变量：SDK 指纹上报链（xg/pfb/a3|a4 真实上报未发生）或 HTTP/2 协议栈深层指纹（curl_cffi 未完全等效真 Chrome）。

sdenv runner 工程要点：主代码外层 IIFE 须 `return` 异步 Promise（runner 只 await 完成值）；output 有 5000 字符头部截断；大结果走 cookie 通道或 eval_expression（runner 在 await 后求值）。

**纯本地复现成本评估**：还差"通道层"——要么完整还原 RCF SDK 指纹上报链（上报接口本身也有 anti_content，递归依赖），要么换真实 Chrome 协议栈（如 DrissionPage 无头代发）。当前最稳形态仍是浏览器内 fetch 闭环。

## 三变量深入检测（2026-08-05 深夜，cookie/上报链/协议栈定界）

### Cookie 审计结论（排除）

- pinduoduo.com 域共 10 个 cookie，唯一 HttpOnly 的 `PDDAccessToken` 已包含在 CDP 全量导出中，C1 发送的 cookie 与浏览器一致 → **cookie 不是根因**。

### 意外发现：`verifyauthtoken` 头（必要非充分）

- 页面真实请求（request_id=19764.593）携带 `verifyauthtoken: JpoWSUV3...` 头，值来自 **`localStorage.VerifyAuthToken`**（人工过 psnl_verification 后写入，Axios 拦截器注入），且 URL 带 `is_back=1`。
- 判据实验（verify_token_replay.py）：sdenv 离线 token + verifyauthtoken 头 + is_back=1 本地重放 → **仍 54001**。→ 该头是必要非充分条件。
- 对照：浏览器内 fetch 不带该头也通过（C2/C2'），说明它不是通过的决定因子。

### 协议栈定界实验（protocol_stack_probe.py）

- impersonate=chrome110（实测走 **HTTP/3**）→ 仍 54001。
- 结合 impersonate=chrome（H2）同样被拒 → **排除 HTTP/2 帧参数这一特定变量**；结论升级为：**一切非真 Chrome 协议栈（curl_cffi 系）本地发包均被拦**。

### 最终定界表

| 变量 | 实验 | 结论 |
|------|------|------|
| token 算法 | sdenv 离线生成 + 浏览器内发通过 | ✅ 已解决 |
| Cookie（含 HttpOnly） | CDP 全量导出比对 | ✅ 无缺失 |
| verifyauthtoken 头 / is_back 参数 | 补齐后本地仍 54001 | ✅ 排除（必要非充分） |
| HTTP/2 vs HTTP/3 / 指纹档位 | chrome/chrome110(H3) 均拒 | ✅ 排除特定协议版本 |
| **真 Chrome 网络栈整体**（QUIC 帧细节/连接级信号/带外遥测） | 唯一未控制变量 | ❌ **真正阻碍** |

剩余可能机理（无法在纯 HTTP 客户端层验证）：QUIC 传输层指纹细节、SDK 带外遥测关联（th.pinduoduo.com/t.gif 埋点流）、或网关级连接画像。**工程结论：纯本地复现到此为止不可行；可行形态只有真实浏览器代发（现闭环方案）**。

### 指纹上报链定位结论（ck3）

- 监听证据（lst_8e9110d2e62f4b81）：每条 reviews 请求伴随多条 `th.pinduoduo.com/t.gif` 遥测 POST（555~1447 字节，带 jrpl cookie）；RCF SDK 本体（b9216582_*.js）每 ~10s 一次心跳（console 日志 + 上报）。
- `jrpl/dilx` 是长期 cookie（30 天有效期，值自会话开始未变），并非每次上报动态轮换——即"上报换 cookie"模型不成立，上报是**遥测/行为流**而非凭证发放。
- 因此本地重放缺失的带外信号 = 与目标请求时序配对的 t.gif 遥测流 + SDK 心跳；服务端很可能做"请求-遥测"关联校验。要补齐须同步伪造 t.gif 流（载荷含行为事件，逆向成本高）。

## 风控触发链完整捕获（2026-08-05 深夜，会话第二次触安全验证）

计划"本地实现遥测"的抓包窗口内，意外捕获到 54001 升级为安全验证的**完整端点序列**（lst_a9ddb08a210142a5）：

1. `POST /proxy/api/xg/pfb/a4`（6257 字节）——**指纹上报核心端点**（a3|a4 即此处），与验证触发同秒发出
2. `POST /proxy/api/api/phantom/obtain_captcha?pdduid=...`（2029 字节）——请求验证码挑战
3. `intelligence_verify_*.css/js` 加载——智能验证页资源
4. `POST /proxy/api/api/phantom/ba/dt/cg?pdduid=...`——验证配置
5. `client.message.yangkeduo.com:16482/16483/api/phantom/rwubvs`——phantom 长连通道（CORS OPTIONS 失败，疑似本地网络拦截）
6. 新 `VerifyAuthToken=I8fMBfbT...` 下发 → 重定向 `psnl_verification.html`

**含义**：
- `xg/pfb/a4` 端点证实了"指纹上报链"真实存在且参与风控决策——本地遥测伪造路线的目标端点已明确，但载荷 6257 字节为加密二进制，逆向成本高。
- 触发原因复盘：当日本地 54001 累计已达账号阈值（三变量实验 3 次 + 遥测预备），**即使浏览器侧请求全部健康也会被升级验证**——风控是账号级累计制，不是会话级。
- **熔断纪律（修订）**：单账号单日本地失败请求预算 ≤2 次；任何判据实验前先想清楚"失败是否消耗预算"。

## 恢复方案（2026-08-05 深夜第二次人工过验证后已恢复）

- 恢复验证：探针重装 `installed:45246`，浏览器内 fetch page=23 → 200 + 10 条（0.22s）。
- 闭环脚本 URL 已对齐页面真实请求（补 `is_back=1`）。
- 后续纪律：不再做任何本地发包实验（纯本地路线已证伪完毕，无新信息可换）；仅维持浏览器内 fetch 闭环取数形态。
- 遥测伪造（t.gif + xg/pfb/a4）仅在用户明确要求"必须纯本地"时再立项，预计工作量 ≥ 数日（载荷加密逆向）。

## 遥测本地实现实验（2026-08-05 深夜，用户立项，已执行完毕）

### t.gif 遥测：纯本地伪造成功 ✅

- 页面内 hook XHR.send 捕获 9 条活体 t.gif 载荷（telemetry_samples.json）：**明文 URL-encoded k=v，无加密无签名**。
- 字段结构 31 个全部可本地构造，关键生成规则已定位：
  - `log_id` = 13 位毫秒时间戳 + 16 位 base36 随机（源码 `react_pdd_*.js`：`r+(0,h.A)(16)`）
  - `dcf` = `pdd_vds` cookie + `.` + 递增计数 + `.` + 随机数
  - `cookie_fp`/`storage_fp` = `_nano_fp` cookie 值
- 本地重放 1 条 → **服务端 200 接受**（telemetry_local_replay.py）→ t.gif 端点不校验协议栈。

### 终极判据：遥测配对 + reviews 全本地 → 仍失败 ❌

local_full_repro.py 时序：前置 t.gif(200) → sdenv 离线 token → reviews 全头对齐（含 verifyauthtoken/is_back）→ **54001**。

**结论（最终版）**：t.gif 行为遥测不是 reviews 请求通过的必要条件；剩余阻碍收敛到 `xg/pfb/a4` 指纹上报链（6KB 加密载荷，RCF SDK 生成）或连接级画像。纯本地复现的唯一未验证路径只剩完整逆向 RCF SDK 指纹上报，工作量 ≥ 数日且大概率仍有更深层校验。

**工程决策（终局）**：维持浏览器内 fetch 闭环为唯一交付形态。遥测伪造脚本留档：`telemetry_local_replay.py`（载荷生成器可复用）、`local_full_repro.py`（完整本地流水线，若未来破解 xg/pfb/a4 可直接续接）。

## 行业横向对比（2026-08-05 网络检索）

**结论：不是孤例，别人同样遇到且同样卡在 0as 新版 SDK，而旧版 SDK 场景有人纯本地成功。**

| 来源 | 场景 | SDK 特征 | 结果 |
|------|------|---------|------|
| CSDN（2026-04）code_ninja_0 | m.pinduoduo.com 推荐页 `query_tf_goods_info` | `0ar` 前缀、422 字符、SDK 仅访问 24 个环境属性、无需登录 | ✅ Node VM 补环境纯本地通过 |
| 影刀社区（2025-01） | 商家端订单备注接口 | 扒 JS 补环境（Node 12.18.1）+ requests | ✅ 纯本地通过（商家端） |
| 看雪 thread-283125 | 小程序 anti_content | — | ⚠️ 原文明确：**"调用环境生成的 anti_content 长度与真机不同 → 无法使用，过不了服务器检测"**——直接印证环境绑定现象（长度差即环境差） |
| GitHub keycodingpace/pinduoduo-1 | 列表/搜索页 | — | ⚠️ 需带 `AccessToken` 登录头或 IP 质量足够好 |
| 拼多多开放平台官方文档 | 风控验证码接入 | — | 官方机制：验证通过后下发 `verifyAuthToken`——与本案例 `psnl_verification` + `VerifyAuthToken` 头完全一致 |

**差异根因**：本案例是 `0as` 前缀 / 583 字符 / b9216582 RCF SDK（新版），相比成功案例的 `0ar`（422 字符、24 属性轻量采集）是更高风控档位——服务端对 token 内嵌指纹做交叉校验（与 xg/pfb/a4 指纹上报、连接画像关联），因此纯补环境不可通过。业界成功案例全部集中在旧版 SDK 或商家端/弱登录态接口，与本案例同档位的公开成功复现未见报道。

## 刷新全流量联动分析（2026-08-05 深夜，lst_87bdee8e1f374cc0，97 条请求）

**核心发现：指纹注册先于业务请求；账号风控已升级至"页面加载即拦"。**

### 真实浏览器页面加载的完整时序（loader D51612CF）

```
t+0.0s  GET goods_comments.html
t+0.5s  GET CSS/JS/react_anti_co/b9216582 RCF SDK
t+1.5s  GET reviews/info + GET api/server/_stm（服务器时间，token 生成前置）
t+1.8s  GET xg/pfb/a3                    ← 指纹上报·阶段1
t+2.0s  OPTIONS+POST xg.pinduoduo.com/xg/pfb/ae4（跨域 preflight）← 指纹上报·阶段2
t+2.2s  POST reviews/list page=1 size=20  ← 业务请求（HTTP 200，但软拦）
t+2.6s  跳转 psnl_verification.html?VerifyAuthToken=Pudj9RTI...   ← 第一次拦截
t+2.7s  再跳 psnl_verification.html?VerifyAuthToken=CbONduG...    ← 第二次
t+3s起  验证页资源链：obtain_captcha → intelligence_verify → xg/pfb/a4(6357B)
        → client.message.yangkeduo.com:16482/rwubvs 长连（失败）→ phantom/ba/dt/cg
```

### 三个决定性结论

1. **"指纹注册 → 业务请求"模型证实**：页面自己的时序是 `a3 → ae4 → reviews/list`，指纹上报**先于**业务请求发出。服务端用当前会话的 a3/ae4 指纹记录与 reviews 请求关联——本地请求没有这条注册链，即使 token/cookie/遥测全对齐也被拒。**这就是"我跟浏览器一样为什么过不了"的终极答案：复制了报文，没有复制报文之前的指纹注册行为。**
2. **账号风控状态已升级至"加载即拦"**：本次是真实浏览器的自然页面加载（完整资源链 + a3/ae4 + 页面自产 token），reviews/list 仍被软拦（HTTP 200 + verify_auth_token → 前端跳转）。账号当日累计已三次触验证，风控预算完全耗尽。
3. **拦截模式确认**：reviews/list HTTP 200 但 body 内 verify_auth_token 触发前端跳转（软拦），与本地 54001 是同一风控体系的两档响应。

### 当前状态

- 页面停在 `psnl_verification.html?VerifyAuthToken=CbONduGafJwQ4mgef8I86Q6a20625db1d37a491`，**需人工验证**
- **今日全部实验终止**：连自然浏览都被拦，任何额外请求只会加深封锁
- 建议冷却 24h 以上再恢复；恢复后仅维持浏览器内低频闭环，不再做任何判据实验

## a4 指纹上报完全逆向（2026-08-06，静态审计路线，全部判据已验证）

**结论：a4 载荷不是加密，是 zlib + 自定义 TLV + urlsafe-base64。编码链已完全逆向并字节级往返验证，之前预估的"数日工作量"被推翻。**

路线：字符串数组解码产物（`rcf_string_array.json` 2005 条）+ 部分内联版 `rcf_b9216582_deobf2.js` 静态审计，未依赖完整解混淆。

### 1. sign 算法（已验证命中）

```python
sign = SHA1("feHJ6793TJDI86DLS9D" + timestamp + data)   # verify_a4_sign.py 逐字节命中抓包样本
body = {"data": data, "timestamp": ts, "appKey": "fe", "sign": sign}
```

- salt 来自解码字符串数组 0x7b2；发送函数 `_0x4e2850`（deobf2 @441678）。
- 服务端响应 `result.a` = 指纹凭证（写 cookie `h_wjrpl`/localStorage，365 天），`result.b` 写 `h_dkrjl`。

### 2. data 编码链（已字节级往返验证）

```
payload(指纹kv) → assembleKeyValuePairs → encodeEs(TLV) → pako.deflate(zlib) → '0a' + urlsafe_b64
```

- TLV 格式（`_0xd63dc4`）：每个字符串 = `zigzag_varint(0xF1)` + `zigzag_varint(utf8长度)` + utf8 字节；0xF1 的 varint 即 `e2 03` 标记。
- base64 为标准字母表后转 urlsafe（`_0x399011`：+→- /→_ 去=）。
- **往返验证**（verify_a4_roundtrip.py）：抓包 data 解码→有序解析 108 对 kv→自实现编码器重建→**56287 字节与原始完全一致**。

### 3. 明文指纹结构（108 字段，a4_decoded_payload.json）

顶层字段：isInterval / reportType / rawData / reportTimestamp / version / app / cookie / FKGJ / uid / pageId / 行为事件(moveData/clickData/…) / 大量检测器结果 / domElems(43KB DOM 快照)。

**决定性发现（CDP 调试浏览器的自曝信号）**：

| 字段 | 值 | 含义 |
|------|-----|------|
| `botD` | `{"bot":true,"botKind":"headless_chrome"}` | **SDK 直接判定我们的 Edge 调试浏览器为机器人** |
| `cdpProxy` | `true` | CDP 调试通道被检出 |
| `hookFuncs` | CSSStyleDeclaration.setProperty / Navigator.connection… | 我们注入的 hook 被枚举上报 |
| `hasWd`/`domAutomation`/`winSelenium` | false | 常规自动化检测未命中，唯 CDP 暴露 |

**这解释了账号反复触发风控的深层原因**：即使是"真实浏览器"，只要挂着 CDP 调试端口 + 注入 hook，每次 a4 上报都在告诉服务端"这是 bot"。

### 4. 本地构造 a4 的可行性与约束

技术上已完全可行（编码器字节级验证）：收集/伪造指纹 kv → TLV → zlib → '0a'+b64 → SHA1 签名 → POST xg/pfb/a4。

约束：
1. **禁止重放抓包 payload**——其中 botD=bot:true 是自曝指纹，重放等于自我举报；必须构造 bot:false 的干净指纹。
2. 指纹必须与后续业务请求的环境交叉一致（UA/屏幕/IP/cookie 同源）。
3. 活体验证消耗风控预算，须用户明确批准且限 1 次。

交付脚本：`decode_a4_full.py`（解码器+明文dump）、`verify_a4_roundtrip.py`（字节级往返验证）、`verify_a4_sign.py`（sign 验证）。

## 活体判据实验：干净 a4 注册 + 本地 reviews（2026-08-06，用户批准，a4×1 + reviews×1）

**结果：a4 服务端完全接受本地构造的干净指纹（success:true + 下发凭证），但 reviews 仍 54001 —— a4 单端点注册不是充分条件。**

实验流程（a4_live_test.py）：
1. 清洗自曝字段（botD→bot:false、cdpProxy→false、hookFuncs→[]、botSignals→unknown）+ 时间戳平移到当前
2. TLV→zlib→'0a'+b64→SHA1 签名 → POST a4（impersonate=edge99 + UA 逐字对齐指纹内 Edge 151）
3. 响应 `result.a=7GgtyvtIOCHaMZSZl935PvhkLXyA4pkU` 写入 cookie njrpl → 同 Session 发 reviews

| 步骤 | 结果 | 含义 |
|------|------|------|
| a4 注册 | HTTP 200, success:true, result.a 下发 | **本地构造的载荷完全合法，服务端不校验来源**；result.a 与抓包样本 cookie 字段同值（uid 维度稳定） |
| reviews | HTTP 200, error_code=54001, verify_auth_token=true | a4 注册不足以放行业务请求 |

**信息增量与剩余嫌疑收敛**：
1. a4 层已完全白盒：编码、签名、清洗后指纹均被服务端接受——之前预估的"最大黑盒"已拆除。
2. 剩余障碍：**a3/ae4 前置链**（页面真实时序 a3→ae4→reviews，本次未发；ae4 载荷未逆向）或连接级画像（TLS 会话/HTTP2 帧级）。
3. 混淆变量：账号昨日已被软拦（自然浏览也 verify_auth_token），本次 54001 可能部分来自账号状态；按风控纪律不追加实验。

**工程决策（更新）**：纯本地路线剩余工作量 = ae4 载荷逆向（新一轮黑盒）+ 账号冷却后重试；性价比低于浏览器内闭环取数，默认维持 `pdd_comments_rpc.py` 形态。若用户要求继续，下一步是抓包逆向 ae4（同 a4 方法论：先验结构、字符串数组定位发送函数）。

## a3/ae4 逆向 + 全链活体判据（2026-08-06 续，用户批准，4 次请求）

### a3/ae4 协议（静态逆向完成，意外简单）

```
a3 : GET  mobile.pinduoduo.com/proxy/api/xg/pfb/a3（无 body）→ result 返回指纹凭证串
ae4: POST https://xg.pinduoduo.com/xg/pfb/ae4（跨域，需 OPTIONS preflight）
     body = {"data": shift30(JSON.stringify({u: uid, f: "", keys: "t,acc"}))}
     shift30 = 逐字符 charCode+30（_0x31bc2f/_0x23b186）；响应 result.data 用 -30 还原
     用途：pullConfigByUid，按 uid 拉账号级配置（acc 标志）
```

### 全链判据结果（a3 → ae4 → a4 → reviews）

| 步骤 | 结果 |
|------|------|
| a3 | HTTP 200，返回凭证 `7GgtyvtI...`（与 jrpl 同值） |
| ae4 | HTTP 200，配置空（未拒绝） |
| a4 | HTTP 200, success:true，再次下发凭证 |
| reviews | **仍 54001 + verify_auth_token** |

### 终局定界：a3/ae4 前置链假设也被排除

至此应用层 + 注册链全部变量排除完毕（token/cookie/verifyauthtoken/is_back/H2H3/t.gif/a4/a3/ae4）。剩余变量只有三个：
1. **IP 信誉**：本地出口 IP 与浏览器不同源；可用远程服务器（广州/北京）跑同链做判别实验。
2. **连接级画像**：HTTP/2 帧级/SETTINGS/会话结构与真浏览器差异（curl_cffi 残留黑盒）。
3. **指纹内容深层污染**：构造的指纹源自曾被标 bot:true 的 CDP 会话采集，其余 103 字段可能带历史污染；彻底方案是在无 CDP 干净浏览器重新采集一份。

交付脚本：`full_chain_live_test.py`（全链判据）、证据 `full_chain_evidence.json`。

**工程决策（终局）**：纯本地路线在应用层与注册链层面已全部打通但服务端仍拒，障碍封顶在 IP/连接层；继续投入需远程 IP 判别实验或指纹重采集，均须用户决策。默认交付形态维持浏览器内闭环 `pdd_comments_rpc.py`。

## 通道定界续拆（2026-08-06，同公网 IP 金标准）

脚本：`dissect_channel_54001.py` → 证据 `dissect_channel_evidence.json`。

| 对照项 | 结果 |
|--------|------|
| 浏览器公网 IP | `64.64.234.18` |
| curl_cffi 公网 IP | `64.64.234.18`（**完全相同**） |
| token | 浏览器 `45246.g()` 新鲜 `0as`（547~548 字符） |
| Cookie | CDP 全量 10 枚（含 `PDDAccessToken`）同源 |
| **浏览器内 fetch** | HTTP 200，`n=10`，0.36s |
| **curl_cffi(impersonate=chrome) 同 token** | HTTP 200，`error_code=54001` + `verify_auth_token`，0.18s |

### 定界升级

1. **IP 信誉假设已排除**（同机同出口下仍一边过一边 54001）。
2. **anti_content 算法 / Cookie / a3·ae4·a4 注册** 此前已排除；本实验再用「浏览器刚生成的真 token」钉死：问题不在 token 内容可验性。
3. **唯一高置信剩余根因**：**请求通道画像**——TLS/JA3·JA4、HTTP/2 SETTINGS/帧序、连接复用/会话票据等与真 Edge 栈不一致。服务端把 `anti_content` 与「当前 TCP/TLS 连接身份」交叉校验；curl_cffi 仿浏览器应用层头，仿不了完整 Chromium 传输栈。
4. CDP 指纹自曝（`botD`）解释账号易升级验证，**不能**解释本实验（同 CDP 会话内 page fetch 已通过）。

### 还值得做的下一步（均需另批预算）

- 真 Chromium 网络栈代发（DrissionPage/无头 Chrome 发 POST，非 curl_cffi）——若过，则锁定「非 curl_cffi TLS 栈」为充分条件。
- 抓包对比 JA3/JA4 / H2 SETTINGS（浏览器 vs curl_cffi）做指纹 diff（零 reviews 预算）。
- 不建议再烧 reviews 本地 54001 预算做重复对照。

## TLS/JA3·JA4 指纹对照（2026-08-06，零 reviews 预算）

证据：`tls_fp_compare.json`（浏览器页 `tls.browserleaks.com/json` + curl_cffi 多档 impersonate）。

| 客户端 | ja3_hash | ja4 | akamai_hash(H2) | 含 sig 0904/0905/0906 |
|--------|----------|-----|-----------------|------------------------|
| **真 Edge 151** | `5e8c5223…` | `t13d1516h2_8daaf6152771_**806a8c22fdea**` | `52d84b11…` | **是** |
| curl_cffi chrome/136/146 | 各不相同 | `…_8daaf6152771_**d8a2da3f94cd**` | `52d84b11…`（与 Edge 相同） | **否** |
| curl_cffi edge99/101 | `cd08e314…` | `…_e5627efa2ab1` | `4f04edce…`（不同） | **否** |

### 机制收窄

1. **Akamai H2 SETTINGS 可与真 Edge 对齐**（chrome impersonate 同 hash）→ 「纯 H2 帧参数」不足以解释 54001。
2. **JA3 / JA4 全档 impersonate 均无法对齐 Edge 151**：JA4 前两段（TLS 版本+密码套件哈希）可接近，**第三段（扩展/签名算法指纹）系统性不同**。
3. 真 Edge 的 `ja4_r` 签名算法列表以 `0904,0905,0906` 开头；本机 curl_cffi 已测到 `chrome146` 仍不含该族 → **现成 impersonate 档位盖不住 Edge 151 ClientHello**。
4. 与同 IP 通道对照合流：服务端在 reviews 上校验的「连接身份」主要是 **TLS ClientHello（JA3/JA4）**，不是公网 IP，也不只是 H2 SETTINGS。

### 工程含义（更新）

- 继续调 curl_cffi impersonate 档位 **期望值极低**（缺 0904 族签名算法）。
- 可行本地化方向只剩：① 真浏览器代发（已交付）；② 自建/升级能复刻 Edge 151 ClientHello 的 TLS 栈（成本高）；③ 等上游 curl_cffi 出现匹配档。
- **不再消耗 reviews 本地 54001 预算做重复对照。**

## 纯本地三条件框架对齐（2026-08-06）

> 理论上能，但门槛不是「算出 token」，而是同时：①票证干净 ②通道位级一致 ③出口干净。浏览器内 RPC 天然满足三条；当前卡在 ②（可能叠加 ① 的 a4 自曝，但不解释同 token 双通道分裂）。

### 2×2 通道×票证（缺失格已填，勿再烧）

| token 源 \\ 通道 | 浏览器真栈 | 本地 curl_cffi |
|---|---|---|
| sdenv `0as` | **200**（C2，`local_repro_experiment`） | 54001（C1） |
| 浏览器 `45246.g()` | **200**（金标准） | 54001（同 IP 金标准） |

判读：**TICKET_CLEAN_CHANNEL_GAP** — reviews 用的 `0as` 票证足够干净（能过真栈）；差纯在通道。预算投 ④a/④b（utls/真栈），不先「修 sdenv 算 token」。复验脚本（仅换会话时）：`p1_missing_cell_sdenv_browser.py`。

### 子假设状态

| ID | 内容 | 状态 |
|---|---|---|
| ④a | TLS ClientHello JA3/JA4 | **高置信主因** — Edge 151 含 `0904/05/06`，curl_cffi 全档 JA4 第三段恒为 `d8a2da3f94cd`（`tls_fp_compare.json`） |
| ④b | H2 SETTINGS/PRIORITY/HPACK | **单独不足** — Akamai H2 hash 可与 Edge 对齐仍 54001；帧序细差未逐字节钉死 |
| ④c | 浏览器 H3 vs 本地 H2 | **本会话排除** — navigation/reviews/a3/a4 均为 `h2`（`protocol_h2_h3_check.json`） |
| ④d | token 绑定页内 H2/TLS session | 中，未单独 A/B |
| ④e | 头序/casing/sec-fetch | 中低；应用层「同头」已多次对齐仍拒 |
| ④f | 遥测连续性 | 中；全链 a3→ae4→a4→t.gif 仍 54001 → 注册报文可「格式正确被接受」，洗不白首握打标 |

全链实验含义不变：注册端点接受格式正确指纹 ≠ 连接从第一次握手起未被打标。

### P0 票证自检（零 reviews）

证据：`p0_ticket_selfcheck.json` + `a4_decoded_payload.json`。

| 层 | 结论 |
|---|---|
| CDP 会话采的 **a4 注册明文** | **脏**：`botD.bot=true/headless_chrome`、`cdpProxy=true`、`hookFuncs` 枚举 fetch/XHR/plugins… → 账号 B 类风险（易升级验证），与「同 token 浏览器过/本地拒」正交 |
| sdenv / 页面 **`0as` reviews token** | **够干净**（C2 真栈 200） |
| 「a4 success:true」 | ≠ 被标记为干净（全链后 reviews 仍 54001） |

### 下一步（信息增益序，与科研线并行）

**已完成（零/已批预算）**：票证自检拆层、JA3/JA4 diff、reviews=h2、同 IP 金标准、2×2 缺失格（历史 C2）。

**P1 不必重跑**（除非换账号/会话复验）。

**P2 再批**：① Go utls / tls-client 字节级 ClientHello+H2 同 IP 同票证 — 过则钉死 ④a、纯本地可换栈成立；仍不过且确认非 h3 → 通道含连接态/遥测，成本≈半个浏览器，转工程托底。② 住宅 IP A/B（本机已同 IP 排除信誉，住宅仅作额外对照）。

### 工程托底（并行）

1. **Extension 化 RPC（首推）**：content script 页面原生 fetch + WS 回传 — 无 CDP/无 hook、真栈、消 `cdpProxy/hookFuncs` 自曝。
2. DrissionPage：真栈但 CDP 在场，过渡。
3. 现状：`pdd_comments_rpc.py`；`DEFAULT_TAB` 已改为 `3AC01DA691EDCC73060A21A21F94ADDD`（过期用 `--tab_id`）。

**一句话**：纯本地不是不能，是 **curl_cffi 栈补不到 ④a**；票证侧 reviews 的 `0as` 已过真栈，脏的是 CDP 采的 a4 自曝。下预算要么 utls 对 ClientHello，要么直接 extension 化交付。

## 双线批注执行（2026-08-06）

隔离：utls A/B ≤5 次 reviews、**牺牲账号** + 同机出口；Extension 主线零风控预算。生产账号实验窗口暂停取数或独立出口。

### Phase 0 — 离线对齐（已完成，零 PDD 预算）

脚本/证据：`phase0_tls_diff.py` → `phase0_tls_diff.json`（`tls-client-python`，勿用旧 `tls_client==1.0.1`）。

| 客户端 | JA4 == Edge151 | 0904/05/06 | Akamai H2 |
|--------|:---:|:---:|:---:|
| **真 Edge 151** | 基准 `…_806a8c22fdea` | 是 | `52d84b11…` |
| **tls-client `chrome_150`** | **是（逐字相同）** | **是** | **是** |
| tls-client `chrome_150_PSK` | 是 | 是 | 是 |
| tls-client `chrome_146`/`144` | 否 | 否 | 是 |
| curl_cffi `chrome` | 否（`…_d8a2da3f94cd`） | 否 | 是 |

**门禁结论：`stock_aligned=true` → V1 用 stock `chrome_150`，不写自定义 ClientHelloSpec。**  
残留：JA3 hash 仍与 Edge 不同（GREASE/扩展序）；若 V1 仍 54001，再评估 JA3/④d/④f，不先烧 1 人日自定义 spec。

### Phase 1 — live（2026-08-06 已跑，预算 2/5）

脚本/证据：`phase1_utls_live.py` → `phase1_live_evidence.json`（`--confirm-sacrifice`）。

| 变体 | 栈 | 前置链 | reviews |
|------|-----|--------|---------|
| V0 | curl_cffi `chrome` | a3/ae4/a4/t.gif 全 200 | **54001 + verify**（未漂移） |
| V1 | tls-client **`chrome_150`** | 同上全 200 | **200，n=10，无 verify** |

**判读：④a 钉死。** 同机、同 Cookie 域、同全链、票证均为浏览器新鲜 `0as`；唯一实质差分为 ClientHello（JA4/`0904` 族）。纯本地换栈 **成立** → 交付栈切 `tls-client` `chrome_150`；V2 自定义 spec **取消**。

加固清单（下一步，非判据）：翻页稳定性、≥5s 限频、54001 熔断、sdenv 离线出票替代浏览器 `g()`、IP 池可选。Extension 主线仍并行（多账号/无 CDP/消 B 类自曝）。

### 纯本地翻页冒烟（同日）

`pdd_comments_local_tls.py --confirm-local --pages 2 --start_page 43`：
预热全 200 → page43/44 各 **OK n=10**（0.17–0.19s），累计 20 条 → `comments_local_881388350961_p43.json`。
出票仍借浏览器 `g()`（通道已本地化）；`--token-source sdenv` 可继续去浏览器依赖。

### 去浏览器依赖（同日续）

| 步骤 | 命令 | 浏览器？ |
|------|------|:---:|
| 一次性导出 | `python pdd_comments_local_tls.py --dump-assets` | 要（仅此时） |
| 日常出票自检 | `python pdd_comments_local_tls.py --offline --token-only` | **否**（直调本地 sdenv / Node） |
| 日常翻页 | `python pdd_comments_local_tls.py --confirm-local --offline --pages N --start_page P` | **否** |

落盘资产：`webpack_45246_bundle.js`（~515KB，362 模块）+ `session_offline.json`（Cookie）。默认 `--token-source sdenv`。出票 ~12–25s/枚（冷启动可至 ~130s）。

**活体注意（2026-08-06 下午）**：当前会话浏览器原生 fetch 亦返回 `{"data":[]}`（非 54001）——账号软限/会话失效，与出票栈无关。`data=[]` 连续 ≥2 次会熔断。换号或恢复会话后再验 `n>0`。

### Extension RPC 骨架（主线，今日已立）

目录：`cases/pdd_goods_comments/extension/`

- MV3：`manifest.json` / `background.js`（WS + tab 注册 + alarm ping）/ `content.js`（MAIN 一次性 inject，无 native hook）
- 本地：`ext_ws_server.py` → `ws://127.0.0.1:18765`
- 加载：手动 Edge **不带** `--remote-debugging` → Load unpacked；stdin：`tabs` / `ping`

下一步工程：SW 侧 `chrome.scripting.executeScript({world:'MAIN'})`、限频熔断、与 `pdd_comments_rpc.py` CLI 对齐；另开 `pdd_comments_local_tls.py`（tls-client 全链翻页）作纯本地交付。

## 换号离线闭环（2026-08-06 下午）

账号 `pdduid=8806803917643`，goods=`983991442402`，tab=`FA9C80FA…`。

| 步骤 | 结果 |
|------|------|
| 浏览器对照 page1 | 200 / n=10 |
| `--dump-assets` + `--offline` sdenv + `chrome_150` **page1** | **200 / n=10**（出票 ~20s） |
| 同跑 page2（间隔 5s） | 54001 |
| 此后浏览器再请求 | 亦 54001（账号级加热） |

证据：`offline_new_account_evidence.json`。确认：纯本地出票+发包在干净号上成立；翻页间隔与单号失败预算仍是运维红线。
