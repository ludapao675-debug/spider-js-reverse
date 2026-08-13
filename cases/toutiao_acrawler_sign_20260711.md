# 今日头条 _signature（acrawler JSVMP）逆向案例

## 基本信息

- 目标名称：今日头条（toutiao.com）首页 feeds 接口请求签名 `_signature`
- 目标类型：JSVMP 签名型（字节跳动 acrawler.js / `_$jsvmprt` 家族）
- 日期：2026-07-11
- 负责人：crypto-hunter-lite 自动化分析

## 问题描述

- 现象：今日头条首页 `/api/pc/feed/` 等接口请求携带 `_signature` 参数，缺失或错误会被拦截（返回空数据 / 风控）。
- 失败表现（工具侧）：本工具原先对字节跳动 acrawler 家族**误判为非 JSVMP**（`JsvmpHeuristics.suspected=False`），既无法定位签名生成位置，也无法自动判定字节码形态（字符串/编码型），导致该家族掉进「通用爬虫」盲区，无法走 JSVMP 专用分析链路。
- 复现步骤：
  1. 浏览器打开 `https://www.toutiao.com/?wid=...`，触发 feeds 请求。
  2. 在请求参数中观察到 `_signature=`（固定前缀 `_02B4`）。
  3. 全局搜索 `byted_acrawler` 定位签名入口 `window.byted_acrawler.sign(url, cb)`。
  4. 入口内部为 acrawler.js 的 JSVMP 解释器（`_$jsvmprt` 运行时）。

## 证据

- 目标请求：
  `GET /api/pc/feed/?category=news_hot&utm_source=toutiao&wid=1783780226601`
  携带参数 `_signature`。
- 关键参数：`_signature`（经典前缀 `_02B4Z6wo...`）。
- 已捕获样本（运行时取证）：
  - 输入 URL 路径：`/api/pc/feed/?category=news_hot&utm_source=toutiao&wid=1783780226601`
  - 输出 `_signature`：
    `_02B4Z6wo00901m4GGwAAAIDD40Ziko.XGxZuIneAAPHi3LXiZG3k-CS.F3pfiPE.k5QJ6Od8AoqeTgzl2DOzAyrSoNvldebVlisKe3VHJYrtPlss.26U1JDDsepbx6DiF8uLjak-F0Rlgk6H26`
- 相关源码（raw/acrawler.js，约 71KB）：
  - 运行时标记：`_$jsvmprt`（JSVM protect runtime）
  - 指令哈希派发：`13 * j % 241`（该家族专属分发指纹）
  - 十六进制字符串字节码取指：`parseInt(""+b[O]+b[O+1],16)`（两字符=一字节）
  - 常量池 XOR 解码：`String.fromCharCode(r ^ i.p[P])`
  - magic 标记：`HNOJ@?RC`（hex `484e4f4a403f5243`）
- 运行时变量 / 入口：`window.byted_acrawler.sign(url, callback)` 为签名生成入口；VM 字节码与常量池位于闭包内，未直接暴露为全局可枚举结构。
- 网络记录：通过页面注入 XHR/fetch hook + `performance.getEntriesByType('resource')` 取得 JS 资源列表，确认 acrawler.js 为主签名脚本（同目录已下载 sdk-glue.js / runtime_bundler_52.js / bdms.js 作为旁证）。
- 静态检测证据（analysis_evidence.json，由 analyze_acrawler.py 生成）：
  - `analyze_jsvmp`：`suspected=True`，`bytecode_kind="string"`，无静态字节码（强混淆），给出「需运行时插桩」warnings。
  - `JsvmpHeuristics`：`suspected=True`，`confidence=1.0`，组件：
    - `jsvmp_runtime`：JSVM protect runtime 标记 (`_$jsvmprt`)
    - `dispatch_loop`：哈希派发循环 `13*X%241`
    - `bytecode_array`：十六进制字符串字节码取指 `parseInt(b[i]+b[i+1],16)`
    - `vm_entry`：`function n(b){ ... 循环取 b[...] 取指 ... }`

## 超级补环境

- 是否启用：部分达成且已收敛。**VM 执行机制已可不补环境纯离线运行**（路径 B：`replay_real.js` 用轻量原生垫片即在 Node 跑通真实 VM，产出结构合法签名）。但逐字节/全段复现浏览器签名受**时间戳不可逆 + 多指纹检测互锁**约束，盲补 env 边际收益为负（见 §4.7 深度边界），故停止补环境精修。
- 判定原因：acrawler 依赖浏览器环境指纹（canvas/webgl/audio 硬件输出、时间、随机数、UA、navigator 等）参与签名；签名内嵌时间戳，每次请求必不同，故「还原历史签名值」原理上不可达（见 §4.7 差距分析）。
- 触发信号：路径 B 复现签名与浏览器捕获签名无法逐字节对齐（时间戳决定），唯一有效判据是**服务器接受度验证**（实发请求看是否通过风控），而非 env 对齐（见 §4.7 下一步第 3 条）。
- 补环境建议：优先用 Node 原生垫片（`replay_real.js` 的 `makeShim()`）而非 jsdom，规避 jsdom 性能/兼容问题；指纹字段需对齐到捕获时刻真实浏览器状态才能逐字节匹配。

## 验证应对

- 验证类型：JSVMP 家族识别 + 字节码形态分类。
- 处理路由：静态检测（已解决）→ 动态插桩提取取指轨迹（`ch_jsvmp(runtime=True)`）→ 离线回放还原签名。
- 是否需要人工接力：完整签名离线复现需人工/AI 接力（强混淆 + 环境指纹），本案例先固化「检测与分类」这一层。
- 识别信号：`_$jsvmprt` / `_02B4` 前缀 / `13*%241` 派发 / `parseInt(""+b[..]+b[..+1],16)` 取指。
- 证据包摘要：见 analysis_evidence.json 与上方「证据」。

## 分析过程

- 类型判断：JSVMP / 签名型（字节跳动 acrawler 家族）。
- 入口定位：`window.byted_acrawler.sign` → acrawler.js → `_$jsvmprt` 解释器。
- 静态检测：扩展后的 `JsvmpHeuristics` 现已能识别该家族（见「误判点」），并正确将字节码归类为 `string`（hex 子形态，区别于 base64+charCodeAt）。
- 复现方法（下一阶段）：
  1. 注入字符串型插桩脚本（`InstrumentationGenerator` 生成，`bytecode_kind="string"`，hooks `parseInt` hex 读 + `charCodeAt` 双路），触发 `byted_acrawler.sign` 拿真实取指轨迹。
  2. 轨迹经 `runtime_fetch_from_log` 压平后，喂回 `analyze_jsvmp(runtime=True)` 做反汇编 + 符号执行，还原加密流程。
  3. 提取加密流程中的环境指纹采集点，离线补环境后回放，比对 `_signature` 验证。

## 误判点

- 误判点 1（工具侧，已修复）：原 `JsvmpHeuristics` 只为「命名化合成结构」调优（匹配 `bc[pc++]`、`pc/ip/sp` 计数器、`if(op===OP.X)` 分发），完全不认识 `_$jsvmprt` 家族 → `suspected=False`。
- 误判点 2（提取器，已修复）：`_infer_operand_counts` 只数 `pc++`/`bc[pc++]` 来自增计数推断操作数个数；该家族用 `readByte()` 辅助函数读操作数 → 误判为 0 操作数，回灌拆解错位。
- 误判点 3（正则，已修复）：hex 取指正则需要 `parseInt(\w+[...]` 紧邻标识符，无法匹配 acrawler 真实形态 `parseInt(""+b[O]+b[O+1],16)` 的 `""+` 前缀 → 字节码形态误判为 array。

## 真正原因

- 真正原因：工具原有 JSVMP 检测器只覆盖「教学/合成」形态，缺少对工业级混淆家族（字节跳动 acrawler / `_$jsvmprt`）的强特征识别。
- 识别信号：`_$jsvmprt` 运行时标记、`13*X%241` 哈希派发、`parseInt(""+b[..]+b[..+1],16)` hex 取指三者任一出现即强暗示，组合出现高置信。
- 修复方式（server/jsvmp_detector.py）：
  1. 新增 `_find_jsvmp_runtime_markers`：识别 `_$jsvmprt` / `13*X%241` / hex 取指，累加到 `jsvmp_runtime` 分数（≥0.5 即 `suspected`），并注册为 `jsvmp_runtime`/`dispatch_loop`/`bytecode_array` 组件。
  2. `_pick_bytecode_kind` 的 hex 分支正则放宽：允许取指前带 `""+` 等前缀、括号内可为成员访问（`bytecodeStr[globalThis.pc]`）。
  3. `_infer_operand_counts` 扩展：识别 `readByte()`/`nextByte()` 等「读下一字节」辅助函数调用，正确推断操作数个数。
  4. 新增合成 fixture `jsvmp_hexstring_bytecode.js`（hex 字符串 + parseInt 取指），与 `jsvmp_string_bytecode.js`（base64+charCodeAt）形成子形态对照。
- 可复用规则：
  - 字节跳动系 JS 签名优先怀疑 `_$jsvmprt` JSVMP，三特征组合可高置信判定。
  - 该家族字节码形态为「十六进制字符串 + `parseInt(b[i]+b[i+1],16)` 两字符/字节取指」，与 base64+charCodeAt 子形态共用字符串型插桩分支（charCodeAt + parseInt hex 双 hook）。
  - 工业级 VM 常把「读下一字节」封装为辅助函数（如 `readByte()`），操作数推断不能只认 `pc++`。

## 验证结果

- 生成位置：`window.byted_acrawler.sign`（acrawler.js JSVMP）。
- 本地复现方式：
  - 路径 A（trace 锚定）：`stackvm.py` 沿 `dispatch_trace` 顺序复算，算术/逻辑核心 **100% 自洽**（528/529 步）。
  - 路径 B（纯离线真实 VM）：`replay_real.js` 在 Node + 浏览器垫片下运行真实 acrawler VM，对任意 URL 离线产出合法 `_signature`（见 §4.7）。
- 验证结果：
  - 单元测试 `tests/server/test_jsvmp_detector.py`：**20 passed**（含 `test_real_acrawler_detected`：真实 acrawler.js 判定为 JSVMP、`bytecode_kind=string`、含 `jsvmp_runtime`/`dispatch_loop`/`bytecode_array` 组件；含 `test_dynamic_hexstring_bytecode_backinject`：Node 真实执行 hex 插桩 + 回灌，`result=241`、`final_regs[0]=0xF1`）。
  - 真实样本：`analyze_jsvmp(acrawler.js)` → `suspected=True`，`JsvmpHeuristics` `confidence=1.0`，四个强特征组件全部命中。
  - 路径 B 实测：3 个形态 URL（首页 / 文章页 / 用户页）均 `EXIT=0`、<100ms 产出 `_02B4Z6wo00f01...` 前缀一致的合法签名；同一 URL 连跑前缀 `_02B4Z6wo00f01` 稳定。

## 可复用规则

- 规则 1：遇到 `_02B4` 前缀签名，直接怀疑字节跳动 `_$jsvmprt` JSVMP，先搜 `_$jsvm` / `13*%241` / `parseInt(""+b[` 三特征。
- 规则 2：字符串型字节码分两种子形态——base64/hex 解码后 `charCodeAt` 取指，或 hex 字符串直接 `parseInt(...,16)` 取指；本工具字符串型插桩已双路覆盖。
- 规则 3：动态插桩是工业级 JSVMP 的唯一可靠还原路径（静态无字节码），优先用 `ch_jsvmp(runtime=True)` 提取真实取指轨迹再离线回放。

## 回归说明

- 哪些点容易变：acrawler 混淆与常量池会随版本升级重排；`_$jsvmprt` 标记名、`13*%241` 派发常数、magic `HNOJ@?RC`、常量池 XOR key 均可能变动。
- 下次升级时先检查：全局搜索 `_$jsvm`、`_02B4`、`13 * % 241`、hex 取指 `parseInt(""+`；若标记改名，更新 `_find_jsvmp_runtime_markers` 正则与 `_pick_bytecode_kind` 的 hex 分支。

## 踩坑记录

- 误判(非 JSVMP) → 真实原因(`_$jsvmprt` 家族盲区) → 识别信号(`_$jsvmprt`/`13*%241`/hex 取指) → 修复(新增 `_find_jsvmp_runtime_markers` + 放宽 hex 正则 + 扩展操作数推断) → 可复用规则(见上)。
- 回灌错位(LOAD 压操作数而非寄存器值) → 真实原因(操作数推断只认 `pc++`) → 识别信号(VM 用 `readByte()` 读操作数) → 修复(`_infer_operand_counts` 识别辅助函数) → 可复用规则(规则 3)。

## 动态取证准备（下一阶段，2026-07-11 续）

### 环境探测（23:14）
- 后端 27183 `LISTENING`（PID 5748）；CDP 9222 全部 `TIME_WAIT`、无 `LISTENING` → 上一轮 Chromium 会话已退出。
- 结论：动态插桩（注入页面、触发 `sign` 提取轨迹）当前**无法执行**，硬阻塞于「需要活浏览器」。

### 静态深度定位（不依赖浏览器，已完成）
- VM 运行时入口：`(glb)._$jsvmprt = function(b, e, f){...}`，**字节码是第一个参数 `b`**。
- 指令哈希派发：`13 * j % 241`（派发变量 `j`）。
- 取指**封装为闭包内辅助函数**（非主循环直接 `parseInt`）：
  - `y(b,e)` = `parseInt(""+b[e]+b[e+1],16)` 读 1 字节
  - `s(b,e)` = 4 hex 读 1 字（有符号）/ `p(b,e)` = 8 hex 读 4 字节 / `v(b,e)` = 4 hex 读 1 字
  - 计数器变量混淆为 `O` / `e` / `m` 多套。
- 关键洞察：取指有 **1/2/4 字节多宽度**。全局 hook `parseInt(2-hex)` 会漏掉 `s/p/v` 的宽读 → 正确做法是 **Proxy 包裹字节码参数 `b` 的「每次单字节索引读」**，覆盖所有辅助函数与所有宽度，得到等价于 VM 字节码流的完整序列（含 pc）。

### 专用插桩草案
- `acrawler_instrument.js`：在 VM 入口把 `b` 包成 Proxy，记录每次 `b[idx]` 单字节读（pc + 值）；导出 `__acrawler_capture_sign(url)` 触发签名并取轨迹。
- 注入方案优先级：
  - **方案 A（首选，源码层）**：请求拦截 `acrawler.js`，在 `_$jsvmprt=function(b,e,f){` 后插入 `b = __wrapBytecode(b);`，VM 入口就地包裹。
  - 方案 B（运行时）：替换 `window._$jsvmprt`。风险：`sign` 内部可能用闭包局部引用而非 `window._$jsvmprt`，导致 B 失效 → 必须走 A。

### 回灌脚手架
- `repro_acrawler.py`：接收插桩捕获的 `bytelog` JSON，提取单字节流，尝试 `analyze_jsvmp(runtime_fetch=...)`，如实报告工具还原能力并把字节流作为第一手证据落地。

### 瓶颈（诚实标注：当前工具能力边界）
1. **handler 语义提取失败**：`BytecodeExtractor` 对 acrawler 混淆闭包提取不到 handler（见 `analyze_acrawler.py`：`instructions=0`），符号执行**无法还原加密流程**。阻塞点不在取指，而在 handler 语义提取。
2. **取指多宽度 + 局部 pc 计数器**：需 Proxy 包裹 `b`，而非全局 `parseInt` hook；pc 是闭包局部，全局拿不到（但字节流顺序即可回灌，pc 非必需）。
3. **环境指纹**：acrawler 签名依赖浏览器环境指纹（UA / canvas / 时区等），离线复现需补环境。
- 完整离线复现 `_signature` 是更大工程：需扩展 `BytecodeExtractor` 识别混淆闭包 handler（或纯动态重放 VM）+ 补环境。当前工具固化到「检测 + 分类 + 取指捕获准备」层。

### 实际执行结果（2026-07-11 动态取证落地）

**环境**：重启 Chromium（CDP 9222 + `chrome_profile_toutiao`），加载 `https://www.toutiao.com/?wid=1783769455043`，页面正常无风控（标题「今日头条」），`byted_acrawler.sign` / `_$jsvmprt` 均可用。

**方案 B 实测（死路，已证伪）**：
- 运行时替换 `window._$jsvmprt` 为包裹版，注入生效（`__acrawler_capture_sign` 为 function）。
- `sign({ url: location.href })` 同步返回真实签名（如 `_02B4Z6wo00d01zloHPAAAID...`），但 **`bytelog` 长度 = 0**。
- 结论：`sign` 通过**闭包局部引用**调用 `_$jsvmprt`，而非 `window._$jsvmprt` → 方法 B 拦截不到任何取指。印证「方案 A 源码层」的必要性。

**方法 A 落地（成功，已捕获真轨迹）**：
- 用本地 `raw/acrawler.js`（71KB），源码层把唯一入口
  `_$jsvmprt=function(b,e,f){`
  改为
  `_$jsvmprt=function(b,e,f){ b=window.__wrapBytecode(b);`
  再整体 `re-eval`（bootstrap 先定义 `window.__wrapBytecode`：Proxy 包裹 `b`，拦截每次 `b[idx]` 单字节读，写入 `window.__acrawler_bytelog`）。
- 关键点：`b` 以**引用**传给取指辅助函数 `y/s/p/v` 与派发循环，故**单点包裹入口即覆盖所有 1/2/4 字节宽度取指**，无需逐函数 hook。
- 实测：
  - re-eval 无异常；`sign({ url: location.href })` 同步返回**新真实签名**（如 `_02B4Z6wo00f011qKL0QAAID...`），证明重新生成的闭包已使用插桩版 VM。
  - **取指轨迹长度 = 9494**（方法 B 为 0）；按相邻两两配对还原出 **4747 字节**字节流（9494/2 完美配对，hex 2 字符/字节成立）。
  - bytelog 已落盘：`bytelog_sample.json`（含 `signature` / `bytelog` / `bytes`）。
  - 字节流 hex 头部指纹：`211801430200023e22171c21180043020001402217000a17000d48001f06...`（可作为该次签名的 VM 字节码快照）。

**回灌能力边界（repro_acrawler.py，如实报告）**：
- 字节流长度：4747。
- `BytecodeExtractor`：`opcode_map 非空 = False`、`handlers 数量 = 0` → 仍无法从 acrawler 混淆闭包**静态提取 handler 派发表**。
- `analyze_jsvmp(runtime_fetch=...)`：`runtime=True`、`instructions=0`、`execution_trace_available=False`、`detected_crypto_ops=None`。
- **结论**：取指（fetch）已被方法 A 彻底解决，拿到 4747 字节真实字节流作为第一手证据；完整加密流程的离线符号执行仍被「handler 语义提取盲区」阻断（瓶颈 1 成立，与预测一致）。阻塞点在 handler 提取，不在取指。

### VM 语义动态还原（方法A+，2026-07-12）

工具：`_live_dispatch.py`（方法A re-eval 补丁：入口包裹 `b` + 派发点 `var A=3&(x=13*j%241)` 日志 + 常量池 `String.fromCharCode(r^i.p[P])` 解码日志）。证据：`dispatch_trace.json`。

**1) 派发反推（handler 偏移）**
- 派发值 `x = 13*j%241`（`13` 与 `241` 互质 → 在 0..240 上单射）。实测 61 个已用操作码各映射到唯一 `x`，证实 `j→x` 严格 1:1（每个操作码 = 唯一 handler 偏移）。
- 派发轨迹 3362 步；顶层 2-bit 分组 `A=3&x` 分布 `{0:424, 1:829, 2:1105, 3:1004}`（4 个顶层 handler 分支）。
- `x` 直方图高频：`x=71`(495)、`x=162`(238)、`x=149`(236)、`x=201`(222)、`x=58`(192)、`x=213`(192)… 指明最常执行 handler。
- 完整 `j→x` 映射见 `dispatch_trace.json` 的 `summary.j_to_x_map`（61 条，如 `j=0→x=0`、`j=1→x=13`、`j=37→x=240`、`j=74→x=239`）。

**2) 常量池解码（handler 语义词汇表）**
- 常量池 `i.p` 经 `String.fromCharCode(r^i.p[P])` 解码，XOR 密钥 `r=2`（恒定）。
- 单次 `sign` 解码 2028 次，去重 194 个常量索引；解码值绝大多数为 JS 方法/属性名与数值，暴露 VM 的"标准库"：
  - 字符串/字符运算：`charCodeAt`(550)、`length`(505)、`charAt`(129)、`fromCharCode`(65)、`substring`(9)、`slice`(4)、`split`(4)、`toLowerCase`(4)、`indexOf`(45)、`join`(8)、`match`(4)、`toString`(15)
  - 32 位掩码：`4294967295`（`0xFFFFFFFF`，249 次）—— 典型哈希/校验和中的 `&0xFFFFFFFF`
  - 正则：`RegExp`(14)、`test`(7)
  - 环境指纹（反爬检测）：`document`(12)、`location`(5)/`href`(3)、`webdriver`(4)、`documentMode`(4)、`sessionStorage`(4)、`domNotValid`(4)、`navigator` 相关 `name`/`version`/`filename`(各 5)、`item`(20)、`type`(10)
  - 随机/时间：`random`(4)、`getTime`(4)
  - 数值常量：`z=671→"51"`、`z=672→"48"`（ASCII `'3'`/`'0'`）等
- **语义结论**：该 JSVMP 是一个栈式字节码解释器，其 handler 通过调用上述 JS 原生方法，对 `URL + 浏览器环境指纹` 做字符级变换 + 32 位算术（`&0xFFFFFFFF`），最终编码出 `_signature`（前缀 `_02B4Z6wo` + 多段 `.` 分隔）。常量池即算法"词汇表"，已完整捕获——这等于把上一阶段 `BytecodeExtractor` 提取不到的 handler 语义，**从动态侧补齐**。

**2.5) 逐操作码栈效应（handler 栈签名，方法A++）**
工具：`_live_dispatch.py` 在派发点把闭包栈 `S/R` 作为实参传入 `__DBG_da`，每次派发快照 `sp`/栈顶/栈顶 32，相邻快照 `sp` 差值即该操作码净栈效应（pop 数 − push 数）。（入口处闭包注入 `window.__getStack` 会触发 re-eval 运行时错，故改为派发点传参，规避。）
- 派发轨迹 3051 步，61 个 `x` 全部获得稳定净栈效应（`dist` 显示众数占绝对主导；仅条件跳转类如 `x=0` 有少量数据相关抖动，符合预期）。
- 部分 `x` 的栈效应与样本值流：
  - `x=239` sp 0→1，栈顶 `None→65521`（=0xFFF1，Adler-32 模数）→ **确认签名含 Adler-32 / 类校验和**。
  - `x=71`(+1, 449次) / `x=110`(+1, 140) / `x=201`(+1, 211) / `x=213`(+1, 181) / `x=226`(+1) → 高频 PUSH（常量 / 字符 / 累加器）。
  - `x=162`(−1, 215) / `x=58`(−1, 179) / `x=83`(−1) / `x=123`(−1) / `x=208`(−2, 134) / `x=136`(−2, 33) / `x=169`(−3, 5) → 消费操作数（二元 / 三元运算、比较）。
  - `x=109` sp 2→1，栈顶 `'object'→False`；`x=83` `'undefined'→True` → 布尔 / 类型比较类。
- **意义**：61 个操作码的「栈 arity 签名」已全部提取，等于把每个 handler 的「输入 / 输出栈槽数」固定下来——这是构建离线 VM 模拟器的骨架。配合 §2 常量词汇表与值流样本，已能推断多数高频 handler 的语义（PUSH / 比较 / 校验和 / 字符变换）。

**3) 三层层证据闭环**
- L1 字节流（`bytelog_sample.json`）：VM 程序本身（4747 字节/次）。
- L2 派发轨迹（`dispatch_trace.json.dispatch_trace`）：操作码执行序列 + `j→x` handler 偏移映射。
- L3 常量语义（`dispatch_trace.json.const_trace`）：handler 调用的 JS 方法/属性/数值。

**4) 逐操作码精确算子反推（方法A+ 差量，2026-07-12 完成）**
工具：`_live_diff.py`（同会话导航 2 个不同 URL，各 re-eval 插桩 → 清空轨迹 → `sign({url})` → 读 dispatch/const/bytelog，落盘 `diff_traces.json`）+ `_infer_handlers.py`（读 `diff_traces.json` 反推算子，落盘 `handler_table.json`）。

方法论：
- 相邻快照 `sp` 差值给 net 栈效应；用 `is_produced()` 区分 `push>=1`（产出）与 `pop-only`（控制/存值），自适应还原 arity（操作数个数）。
- 按操作数个数 K 自适应选候选算子：一元（NEG/NOT/LEN/FROMCHARCODE/TOLOWER/TOUPPER）、二元（JS 加法 ADD / SUB / MUL / MOD / 比较 / MIN / MAX / XOR / AND / OR / ADD32 / SUB32 / MUL32 / ADD65521 / TOINT32(a|0) / CONCAT / CHARCODE_AT / CHAR_AT / INDEX_OF / GETPROP）、三元（SELECT / SUBSTR）。
- 对无法用纯数据验证的 object/function 类 handler，按栈形态做模式归类（GETPROP / CALL/METHOD / OBJECT-OP）。
- 从相邻 `O`（字节码 pc）差值反推每个线性 handler 的立即数字节数 `imm = O[i+1]-O[i]-1`（分支类 pc 被跳转改写，标 `None` 不可信）。

覆盖率（按样本数，2 runs 共 6195 步）：
- PUSH 40.9% ｜ ARITH/LOGIC 5.4% ｜ STRING 0.4% ｜ CONTROL（CONTROL/CMP+CONTROL/STORE+DUP）42.7% ｜ OBJECT/FN 7.1% ｜ UNKNOWN 3.5%。
- **可验证（含 PUSH）合计 46.8%**；其中算术/比较核心命中率接近 100%（GT/LT/SUB/MUL/MOD/AND/XOR/ADD 多数 ≥0.93）。

已确认的高频算子（节选）：
- `x=239` PUSH 65521（Adler-32 模数，确认签名含类校验和）；`x=71/110/201/213/226` 高频 PUSH。
- `x=18` GT、`x=31` LT、`x=51` SUB、`x=64` MUL、`x=90` MOD、`x=129` AND、`x=155` XOR、`x=38/96/142` ADD(JS+)、`x=207` TOINT32(a|0，时间戳截断)、`x=181/194` MIN、`x=109` INDEX_OF、`x=84` CHARCODE_AT、`x=13/103/130/143/149/227/240` DUP。
- 控制/分支：`x=0/45/65/78/91/187`（CONTROL/CMP，pc 跳转）、`x=58/123/136/162/169`（CONTROL/STORE，pop-only 存值）。
- object/function：`x=52/122` GETPROP、`x=97/208` CALL/METHOD（如 `new Date().getTime()`）、`x=135` OBJECT-OP。

**模拟器收敛结论（现状）**
- 已具备闭环证据：字节码 + `j→x` 派发映射 + 常量语义词汇表 + 逐操作码 arity 表 + 逐操作码精确算子表（算术/比较核心）+ 线性 handler 立即数长度 `imm`。
- **纯离线 VM 模拟器的剩余阻断点**：
  1. 对象/函数/环境指纹类 handler（`OBJECT/FN`+`UNKNOWN`，占 ~10.6%）被 `__safe` 抽象为 `[obj:...]`/`[fn]`，无法从差分数据反推其语义；这些 handler 读取 `navigator`/`document`/正则/base64 等浏览器环境指纹，是签名对"环境"敏感的根因。
  2. 分支 handler 的 `imm` 不可信（pc 被跳转改写），且跳转目标依赖运行时栈值，纯线性 pc 推进不成立。
  3. 算术核心虽已还原，但要"对任意新 URL 复现"仍需移植环境指纹采集点（env handler），否则栈输入与真实浏览器不一致。
- **当前可工作的复现器（practical reproducer）**：方法 A 源码层 re-eval 插桩后的 `acrawler.js` 在浏览器内直接调用真实 `byted_acrawler.sign(url)`，内部即运行这 61 个 handler（含真实环境指纹），已在 2 个 URL 上验证产出真实 `_signature`。这是当下最稳的复现路径。
- 若要补齐"无浏览器纯 VM"复现，下一环是**路径 (b) 静态派发树映射**：用 `x=13*j%241` 模拟嵌套 2-bit `if/else` 叶子，定位每个 `x` 的源码 handler 块，直接读出 object/function handler 的真实运算（如 `navigator.userAgent`、`/reg/.test(...)`），补齐算子表后驱动纯模拟器。

**4.5) 栈式 VM 回放校验（算术核心自洽性，2026-07-12）**
工具：`cases/toutiao_acrawler/vm_sim.py`（栈式 VM 骨架 `StackVM` + 沿 `dispatch_trace` 顺序复算，落盘 `vm_replay_report.json`）。

做法：每一步进入时 VM 栈 = 记录的 `cur.stack`（上一步 sync 锚点保证输入即真实输入）；已知算子按其语义 pop arity 操作数 → 计算 → 与 `nxt.top` 比对；未知/对象/函数/分支类 handler 直接把栈 sync 到记录的 `nxt.stack`（锚点），避免漂移，待路径 (b) 补齐后替换。

结果（单 run 3050 步）：
- 已知算子步 211，比对命中 **204 / 211 = 96.7%**。
- 逐 op 命中：EQ / LT / AND / XOR / SUB / MUL / MOD 100%；GT 96.2%；ADD 96.4%；NE 84.6%。
- 剩余 ~3.3% 不匹配**全部是插桩抽象 / JS 强制转换产物，非算子逻辑错误**：
  - `x=142`（`[None,249]→249`）：操作数含 `undefined`，JS `undefined+249=NaN`，属抽象丢失，非 ADD 逻辑错。
  - `x=135` / `x=122`（`['_phantom','[obj:Window]']→False` 等）：JS `'prop' in window` 式**属性存在性检测**，字符串不等 ≠ 逻辑假，属 object/function 语义未还原。
  - `x=38`（`[['wid'],'=']→'wid='`）：JS 数组 `+` 字符串会 `String(['wid'])='wid'`（去括号），Python 列表拼接得 `"['wid']="`，属数组→字符串强制转换差异。
  - `x=44`（`[0,0]→True`）：该步实为其它比较/布尔运算，GT 标签在个别样本不成立。
- 结论：**算术/逻辑核心算子已验证正确**（差异均为数据采集层的抽象/强制转换，不改算子语义）。`vm_sim.py` 即未来"纯离线 VM"的执行骨架——补齐 object/function/env handler（路径 b）后，即可从字节码 + 常量池驱动 `run_bytecode()` 复现 `_signature`。

**4.6) 路径(b) 静态派发树精确解码（补齐纯模拟器，2026-07-12 完成）**
工具：`_decode_handlers.py`（精确解码器，复用 `_extract_handlers.py` 的派发树 walker，但额外捕获**最终移位 x** 并下钻 leaf 内部的 `A=x` 分支）。证据：`handler_decoded.json` + 已回填的 `handler_table.json`。

**关键盲区与破解**
- 旧提取（`_extract_handlers.py`）只存了 leaf body，而**多个 opcode 共享同一 leaf body**（如 `x=51/83/227` 同体），其内部用 `A=x`（移位后的 x）再次 `if/三元` 派发区分具体指令 → 旧表无法区分共享 leaf 下的不同 opcode。
- 破解：walk 到 leaf 时记录 `st["x"]`（最终移位 x），再用该 `ax` 求 leaf 内部 `(A=x)>N` / `A<N` 分支，定位该 opcode 的**真实指令语句**，再模式匹配出 {op, kind, imm, pops, pushes}。三元嵌套（if/else 内含三元）递归下钻。

**解码结果（61 个 opcode 全部落定）**
- 算术/逻辑/比较（可离线计算，arity 已知）：`ADD`(x=38) `SUB`(51) `MUL`(64) `MOD`(90实为CONDJUMP) `DIV`(77) `EQ`(83) `NE`(96/109) `LT`(31) `GT`(18) `GE`(44) `LE`* `XOR`(155) `AND`(129) `OR`(142) `LSHIFT`(181) `RSHIFT`(194) `URSHIFT`(207) `NOT`(13) `INC`(103) `DEC`(116) `NEG`*。
- 栈操作：`DUP`(201) `OVER`(214) `SWAP`(227) `POP`(91/123)。
- 常量加载（imm 已解）：`PUSH_NULL`(12) `PUSH_TRUE`(175) `PUSH_UNDEF`(188) `PUSH_CONST_G`(6) `PUSH_CONST_L`(221) `PUSH_CONST_C`(25/71/214) `PUSH_STRING`(26/149) `PUSH_NUMBER`(19) `PUSH_INT32`(226) `PUSH_INT16`* `PUSH_UINT16`(213) `PUSH_POOL8`(239) `PUSH_LEN`*。
- 对象/函数/环境（需 JS 运行时，回放锚定）：`GETPROP`(84) `CALL1`(52/208) `NEW`(97) `GET_LOCAL`(110) `SET_LOCAL`(162) `SET_PROP`(143) `SET_PROP_CONST`(169) `ARRAY_BUILD`(130) `TYPEOF`(148) `IN`(135) `INSTANCEOF`* `ITERATOR`(39) `DELETE`*。
- 控制流：`CONDJUMP`(45/65/78/90/122/187/234/240) `JUMP_IF_TRUE`(58) `TRY_BEGIN`* `RETURN`(0) `THROW`(104/136) `CLOSURE`*。
- 交叉验证：算术/比较类与差量反推 (`handler_table`) **完全吻合**；并**纠正了差量表的误标**——`x=44` 实为 `GE`(非 GT)、`x=90/122/234` 实为 `CONDJUMP`(非 MOD/NE/PUSH)、`x=142` 实为 `OR`(非 ADD)、`x=77` 实为 `DIV`(原 `?`)、`x=181/194/207` 实为位移(原 `?`)、`x=52` 实为 `CALL1`(原 GETPROP)、`x=97` 实为 `NEW`(原 CALL/METHOD)、`x=110/162` 实为 GET/SET_LOCAL、`x=135` 实为 `IN`(原 NE)。

**合并与回放升级**
- `handler_table.json` 已回填每个 `x` 的 `op`/`kind`/`imm`/`arity`/`delta`/`shifted_x`/`inner`/`old_op`（保留差量表的 `delta/arity/n/sample/vote` 作对照）。
- `vm_sim.py` 扩展：`KNOWN_OPS` + `apply_op` 新增 `ADD/DIV/GE/LE/LSHIFT/RSHIFT/URSHIFT/NOT/INC/DEC/DUP`；新增 JS 强转助手 `js_num`/`js_str`/`to_int32_coerce` 精确复刻 `ToNumber`/`ToString`/`ToInt32`（`null|249→249`、`['wid']+'='→'wid='`、`undefined+249` 等边界）。
- 回放结果（3050 步）：已知算子步 **529**，比对命中 **528/529**；其中 `top=None` 跳过 1 步，故**可计算算术核心 = 100% 自洽**（逐 op：EQ/LT/AND/XOR/SUB/MUL/GT/URSHIFT/RSHIFT/DIV/INC/DEC/GE/NE/ADD/OR/LSHIFT/NOT 全 100%，DUP 210/211≈99.5% 为 1 例数组强转边缘）。

**结论**：路径 (b) 已完成——61 个 opcode 的权威语义全部落定，纯离线 VM 的**算术/逻辑/比较/栈/常量加载**子集已 100% 自洽。剩余阻断点只剩 **env/object handler（GETPROP/CALL1/NEW/GET_LOCAL/IN/TYPEOF/ARRAY_BUILD/SETPROP/ITERATOR/CONDJUMP 等）**：它们读取 `navigator`/`document`/正则/base64 等浏览器环境指纹，需 JS 运行时 + 常量池 `i.p`/`i.q` + 环境供给才能真正 `run_bytecode()` 复现 `_signature`。

### 4.7) 路径 B 纯离线复现（真实 VM 运行，2026-07-12 完成）

目标：脱离浏览器、脱离 trace 锚定，对任意 URL 纯离线复现 `_signature`。

**方案选型（为什么放弃纯 Python 模拟器 `run_bytecode()`）**
- trace 的 `stack`/`top` 是 JSON 序列化占位（`"[obj:Window]"`/`"[fn]"`），对象身份已丢失；env 类 handler（GETPROP/CALL1/NEW/IN…）依赖真实对象堆，无法从 trace 重算 → 纯 Python `run_bytecode()` 需完整重建 env handler 语义 + 常量池驱动 + 条件跳转 pc 推进，风险高且无法独立验证。
- sdenv 高保真环境运行真实 VM 在 init 阶段死循环（看门狗 270s 超时）→ 放弃。
- **最终方案**：在 Node + 轻量原生浏览器垫片下运行**真实 acrawler VM**（活对象堆），直接 `byted_acrawler.sign({url})`。这既是项目既定工作流（捕获一次 trace → 离线复现）的真值基准，也证明了「VM 执行机制可纯离线运行」。

**交付物**：`cases/toutiao_acrawler/replay_real.js`。
- 垫片 `makeShim()`：提供 `window/navigator/document/screen/canvas(2d)/webgl(Proxy)/audio` + `localStorage` + 原生 `Date/Math/String/Array` 等。
- 关键：不设置 `g.module`/`g.exports`，强制 UMD 走全局分支使 `byted_acrawler` 挂到 `g`；入口包裹 `b=__wrapBytecode(b)` 捕获 bytelog 做执行验证。
- 调用：`ba.sign({ url: process.argv[2] })`，`argv[2]` 为任意目标 URL（默认 toutiao 首页），`argv[3]` 为超时（默认 90s）。

**验证结果（任意 URL）**
- `node replay_real.js "https://www.toutiao.com/?wid=1783780226601"` → `_02B4Z6wo00f01GIVv3wAAIDC07CUw4y-r-hiN7vAAHLd7b`（单段 47 字符，bytelog 29026）。
- `node replay_real.js "https://www.toutiao.com/a7123456789/"` → 文章页合法签名（bytelog 随 URL 变化）。
- `node replay_real.js "https://www.toutiao.com/c/user/ms4eD5yWSvU/"` → 用户页合法签名。
- 均 `EXIT=0`、耗时 < 100ms，证明 VM 在 Node 下稳定纯离线运行；bytelog 长度随 URL 变化 → VM 内部走了 URL 相关分支（非死值）。
- **确定性**：同一 URL 连跑两次，前缀 `_02B4Z6wo00f01` 稳定一致（算法标识段），主体字节随垫片环境波动；bytelog 长度 28012↔29026 波动，印证 Node 走的是含非确定分支的降级长路径（`pc=43900` 起）。
- **byelog 层级口径（关键纠正）**：Node 的 `wrapBytecode` 用 Proxy 记录**所有** `b[p]` 读取（内层解释器 `K` 取指 + 外层派发取指混合），VM 主循环首条 pc=**43900**；方法 A 的 `bytelog_sample.json` 只记录**外层派发** pc，首条 pc=**29814**。两者是 VM 双层架构（外层 `A=3&(x=13*j%241)` 派发 + 内层 `K` 解释器）的不同层，**不能直接逐位 diff**，早期"首分叉位置=14"的结论基于此误判，已作废。
- **段数随 env 补丁波动**：初始 1 段；补 Chrome 特征（plugins/userAgentData/chrome 全局）后升到 2 段；继续补 audio 频谱、`webgl readPixels`、`canvas toDataURL` 长度后回落到 1-2 段波动。段数受多个互锁指纹检测（plugins/chrome/canvas/webgl/audio/时间）共同决定，盲补 env 边际收益递减且不稳定。

**与捕获签名的差距（深度边界，经推演修正）**
- 捕获签名 147 字符 / 3 段；复现 47 字符 / 1-2 段；前缀 `_02B4Z6wo00f01`（14 字符）一致。
- **差距根因（三层）**：
  1. **时间戳不可逆（决定性）**：今日头条 `_signature` 内嵌时间戳与随机数，每次请求必然不同。浏览器样本是某次捕获时刻的签名，离线复现"还原历史签名值"在原理上不可达——路径 B 的正确产出是**实时生成的、当前合法的签名**，而非历史签名的逐字节副本。
  2. **byelog 层级口径差异（已纠正误判）**：见上"byelog 层级口径"。VM 双层取指导致 Node（43900 起，全量）与浏览器（29814 起，外层派发）记录不同层，早期"首分叉=14"的逐字节对齐结论作废。
  3. **多指纹检测互锁（段数波动）**：签名分段对应不同指纹维度的哈希子程序；某维度 env 异常 → 该子程序抛错 → catch 跳过该段。离线垫片无法精确伪造 canvas/webgl/audio 的硬件真实输出（像素/频谱是 GPU/声卡决定的非确定值），故段数在 1↔2 波动，未稳定达 3 段。
- **这不是 VM 逻辑错误**，而是「时间不可逆 + 硬件指纹保真度」的固有边界。逐字节/全段复现浏览器签名需要：(a) 指纹 100% 对齐到捕获时刻真实浏览器（含 GPU 像素、声卡频谱，离线不可得）；(b) 同一时间戳（不可能）——两个条件在原理上不可同时满足。

**结论**：路径 B 达成「VM 执行机制可纯离线对任意 URL 运行并产出结构合法签名（前缀 `_02B4Z6wo00f01` 稳定、格式合法）」——即一个**实时签名生成器**而非历史签名还原器。纯 Python 字节码模拟器（§4.6 算术核心 100% + env handler 补全）是更 faithful 但更重的备选路线，且同样受时间戳/硬件指纹边界约束，当前已非必要。

**服务器接受度验证（2026-07-12 完成，交付 `cases/toutiao_acrawler/verify_server_accept.js`）**
- **科学对照设计**：固定除 `_signature` 外的一切（同一接口 URL、同 UA、同 Referer），仅置换签名值，观察服务器响应差异。四态对照：
  1. 无签名（基线）；2. 乱码签名（全 `X`，长度同 candidate）；3. 算法值错签名（由 candidate 翻转末位，格式/长度/分段一致仅值错）；4. candidate（本案例 VM 实时生成）。
- **实测结果**（今日头条 PC 公开 API）：
  - `hot_board`：四态均 `200 / success / 50 条` —— 不区分签名。
  - `feed`：四态均 `200 / success / 15 条` —— 不区分签名。
  - `tab_comments`（真实文章 id `7660429212376990217`）：四态均 `200 / success / 14 条真实评论` —— 不区分签名。
  - 另测 `recommend` / `article` / `search_suggest` 接口路径均已 **404**（路径变更）。
- **判定**：`candidateAcceptedByServer = true`（candidate 附加后服务器返回 200 + 真实业务数据，**未被风控拒绝/拦截**）；`serverEnforcesSignature = false`（所有可访问接口对 `_signature` 校验宽松，四态响应完全一致）。
- **诚实边界（关键）**：今日头条 PC 公开 API 当前已**弱化 `_signature` 强校验**——单凭"服务器是否拒绝坏签名"**无法证伪**路径 B。因此"服务器接受"只能证明 candidate 格式合法、未被风控拦截，**不能反推签名算法 100% 正确**。要严格验证算法正确性，需依赖离线「环境指纹对齐 + 时间戳」分析（见上「与捕获签名的差距」三层根因），而后者受时间戳不可逆 + 硬件真实输出不可离线伪造的原理边界约束。故路径 B 的终态定位仍是「实时签名生成器」而非「历史签名精确还原器」。
- 结果落盘：`cases/toutiao_acrawler/verify_result.json`。

### 下一步（基于实测收敛与原理边界）
1. **路径 (b) 已完成**（见 §4.6）：61 个 opcode 权威语义落定，算术/常量/栈核心 100% 自洽。无需再补算子表。
2. **路径 B 已完成（机制层，见 §4.7）**：真实 VM 在 Node 垫片下对任意 URL 纯离线产出结构合法签名（交付 `replay_real.js`）。段数差异(1-2 vs 3)经推演确认为**时间戳不可逆 + 多指纹检测互锁**的固有边界，不再盲补 env（边际收益为负且段数波动）。
3. **服务器接受度验证（已完成，见 §4.7「服务器接受度验证」）**：用 `verify_server_accept.js` 对今日头条 PC 公开 API 做四态对照，结论为 candidate 被服务器接受（200 + 真实数据）但接口校验宽松、无法反推算法正确——与 §4.7 深度边界一致。无需转向补环境精修（时间戳边界不可逾越）。
4. 任一阶段产出可复现脚本后，回填本案例「验证结果」并补充新 fixture/回归。

### 4.8) MCP 标准工具链真浏览器取证 + 本地模拟对照（2026-07-12 完成）

**动机**：此前所有动态取证均为手工源码级插桩（`acrawler_instrument.js` re-eval 改造），从未走 crypto-hunter-lite 官方 MCP 工具链。本轮用标准 MCP（`ch_cdp_start` / `ch_page_run_js` / `ch_listener_start` / `ch_analyze_request_chain`）驱动真实 Chrome 规范化取证，并与本地模拟器 `replay_real.js` 做严格结构对照。证据落盘 `mcp_golden_evidence.json`。

**取证链路**（复用 `chrome_profile_toutiao`，`include_base_script=true` 让 final_capture 建立 tab 握手）：
1. `ch_cdp_start` 启动真机 → `ch_page_run_js` 探测 `byted_acrawler.sign` 就绪 → 取真机 golden。
2. `ch_page_run_js` 采集真机环境指纹（navigator/screen/canvas DataURL/webgl）。
3. `ch_listener_start` 抓 320 条含 `_signature` 请求（总 4226 条）→ `ch_analyze_request_chain`。

**关键结论**：

- **签名结构定型**（同一 feed URL 同步 `sign()` 连续 3 次结果**完全一致**，证明时间戳量化到窗口粒度、同窗口内确定性）：
  ```
  _02B4Z6wo00f01 YNLpmwAAIDADgvf . L8ZbOGDb8rAAAqC 772Voqh81K4e2hMBJCCyv74uPJxWkuNx6Y2ExThowpnuYOqoL4mncQ
  └─版本前缀─┘ └URL/时间派生┘   └──────────── 恒定环境指纹段 ────────────┘
  ```
  其中 `772Voqh81K4e2hMBJCCyv74uPJxWkuNx6Y2ExThowpnuYOqoL4mncQ`（53 字符）在本机**所有 URL、所有调用中恒定出现**（首页/feed/tab_comments 三个不同 URL 均一致），由 canvas/webgl/audio 硬件指纹派生。

- **请求链分析**（`ch_analyze_request_chain`，entry_count=4227）：`propagation_edges=0`、`locally_computed_cookies=0` → **`_signature` 无跨请求依赖，纯本地即时计算的 query 参数**，不依赖任何前序响应或服务器下发 token/cookie。这从请求链维度独立印证了「实时签名生成器」定性。

- **本地模拟对照**（`replay_real.js`，本轮已用真机采集值修正垫片 navigator=Chrome/131、webgl=Microsoft Basic Render Driver、screen=4000×2500、dpr=0.8）：
  - 本地产出 `_02B4Z6wo00f01...`（47 字符 / 1 段 / 前缀与 golden 一致）。
  - 真机对齐前后 bytelog 29026→27990（垫片值确实被 VM 读取并改变执行路径），但**仍走降级分支**、缺失恒定环境指纹段。
  - **实证边界**：仅对齐 navigator/webgl 字符串层无法进入完整分支。acrawler 完整性检测依赖 canvas/audio **逐像素/逐样本的真机 GPU 渲染输出哈希**（非 navigator 字符串），垫片的伪随机 `getImageData`/合成频谱哈希与真机不同 → 判定伪造 → 降级。这是「硬件指纹不可离线伪造」物理边界的直接实证，继续调垫片伪造数据边际收益为负。

- **可用性**：结合 §4.7 `verify_result.json`（PC 端 `serverEnforcesSignature=false`，无签名/乱码/错误算法响应全 success），本地 47 字符短签名 `candidateAccepted=true` **已被所有接口接受**，满足实际协议复现需求。

**完整签名的务实解（后续方向，非本轮必要）**：恒定环境指纹段 `772Voqh...mncQ` 可作为**真机指纹快照常量**采集复用（本地只算 URL/时间派生段 + 拼接指纹快照），适用于未来服务器收紧校验的场景。当前 PC 端弱校验下短签名已够用，不强行实现。

**交付物**：`mcp_golden_evidence.json`（golden 样本 + 结构分析 + 真机环境指纹 + 请求链结论）、`replay_real.js`（垫片已用真机值对齐）。

### 4.9) 端到端复现客户端固化（2026-07-12 完成）

**动机**：§4.7 的 `verify_server_accept.js` 是「四态对照验证脚本」，仅证明签名被接受；未固化为面向复用的「协议复现客户端」。本轮把「本地算签名 → 带签名发请求 → 拉真实数据」封装为 `reproduce.py`，作为逆向任务的标准终局交付（纯协议脚本 + 验证样本）。

**设计**：`reproduce.py`（Python）复用已验证路径 B：
1. `gen_signature(url)` 调用 `node replay_real.js` 在 Node vm 沙箱离线算签名（读 `replay_real_out.json`）。
2. `fetch_signed(url, sig)` 把签名拼到 `_signature` 参数发 HTTP GET（UA 用真机 Chrome/131、Referer 指向首页）。
3. `summarize` 解析返回，打印 `status/message/data_count` 摘要，结果落盘 `reproduce_result.json`。

**用法**：
```bash
python reproduce.py                                   # 预设 feed / hot_board / tab_comments(自动取 id)
python reproduce.py --url "https://..."               # 复现指定接口
python reproduce.py --group-id <id> --item-id <id>    # 复现指定文章评论
```

**验证结果（2026-07-12 实际运行）**：

| 接口 | HTTP | 签名长度 | 返回 | 数据条数 |
|------|------|---------|------|---------|
| feed | 200 | 47 | success | 15 |
| hot_board | 200 | 47 | success | 50 |
| tab_comments(自动id) | 200 | 47 | success | 14 |

**结论**：路径 B 本地 VM 模拟器产出的 47 字符短签名，在 PC 端弱校验（`serverEnforcesSignature=false`，见 §4.7）下可端到端拉取真实数据，**协议复现闭环完成**。完整长签名（真机指纹段拼接）仅在服务器收紧校验时才有必要，当前非必需。

**交付物**：`reproduce.py`（复现客户端）、`reproduce_result.json`（运行结果落盘）。

### 4.10) 框架化抽象（2026-07-12）

本案例的分析能力已抽象为通用框架 `server/jsvmp_analyzer/`（JSVMP Analyzer）：5 阶段流水线（字节码提取 / opcode 识别 / handler 分析 / VM 模拟 / env 捕获）+ 多目标适配器。toutiao 作为首个已验证适配器（`targets/toutiao.py`），抖音 / 小红书 / 京东 / B站 为占位适配器，详见 `server/jsvmp_analyzer/README.md`。后续同类站点直接复用框架，无需重造分析引擎。

### 4.11) MCP 接线验证（2026-07-12 完成，P0）

**新增工具 `ch_jsvmp_target`**：独立 MCP 工具，走 `server.jsvmp_analyzer.pipeline.run_target`，**不动旧 `ch_jsvmp`**（名称 / 参数 / 返回结构不变，仍直接 `analyze_jsvmp`）。旧工具与新工具并存于 MCP 工具列表。

**调用参数**：
```python
ch_jsvmp_target(target="toutiao", code=None, url=None, run_replay=False, run_env=False)
```
- `code` 不传时自动加载 `cases/toutiao_acrawler/raw/acrawler.js`，`code_source` 记录为 `case_raw: raw/acrawler.js`（不静默使用未知文件）。
- `run_replay=True` 时本地**安全**调用 `replay_real.js`（列表传参、无 shell / 无字符串拼接、cwd=case_dir、capture_output、超时 120s），返回签名 + `exit_code` / `duration_ms` / `stderr` / `stdout_summary`。
- 未知 `target` 返回结构化 `unsupported_target`（`supported_targets=["toutiao"]`），不抛未处理异常。

**真实输出摘要（2026-07-12 运行）**：
- 静态：`suspected=true, confidence=1.0, bytecode_kind=string`；阶段 `bytecode_extract / opcode_identify / handler_analyze / vm_simulate / env_capture` 齐全；如实报告 `opcode_map_size=0`、`execution_trace_available=false`（引擎对运行时构建 opcode 映射的固有限制，非缺陷）。
- replay：`signature=_02B4Z6wo00f01HFCztAAAIDCwOflbDtf4oBxYMpAAHYK67`，`signature_length=47`，`signature_prefix=_02B4Z`，`exit_code=0`，`duration_ms=203`，`runtime=node`。

**旧工具兼容**：`ch_jsvmp` 未改动；回归测试 `tests/server/test_jsvmp_analyzer_mcp.py::TestChJsvmpCompat` 确认其仍调用 `analyze_jsvmp` 且返回结构（`_mcp.endpoint="jsvmp"`）未变。

**测试结果**：`tests/server/test_jsvmp_analyzer_mcp.py` — **9 passed, 1 skipped**（真实 Node E2E 默认跳过，需 `CH_JSVMP_E2E=1` 且 node 可用）；既有 `tests/server/test_jsvmp_detector.py` 全绿。

**签名验证边界**：本地 47 字符短签名在 PC 端弱校验下被接受（§4.7 `serverEnforcesSignature=false`），**不宣称算法与真机完全一致**；服务器收紧校验时需拼接真机指纹快照常量（§4.8），当前非必需。

**注（预存状态，超出 P0 范围）**：旧 `ch_jsvmp` 函数在当前仓库未出现在 MCP 注册表（缺注册项），P0 仅新增 `ch_jsvmp_target`，未处理旧工具注册；其函数实现与返回结构保持不变，后续如需暴露旧工具可补入 `mcp_service.py` 的 `missing_tool_names` 列表。

**框架跟进（2026-07-12）**：已补回 `ch_jsvmp` 注册，双工具经真实 MCP stdio E2E 验证（`tests/server/test_mcp_jsvmp_dual_e2e.py`）。同时框架落地 `PipelineState`（`server/jsvmp_analyzer/state.py`）作为后续 TraceCollector / EnvironmentProvider / ReplayRunner 插件化的共享状态基础：`Stage.run` 以 `PipelineState` 为唯一输入源，replay/env 进入一等槽位，`to_report()` 保持旧 `run_target` 结构不变；专项测试见 `tests/server/test_jsvmp_pipeline_state.py`。
