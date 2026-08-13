# AI 分流实战（2026-08-05 复测）

原则：看样本后人工选工具——`obfuscator.io` → `run_auto_deobfuscate` / `ch_deobfuscate_auto`；字节码 VM → `analyze_jsvmp` / `ch_jsvmp`。流水线**不硬拦**。

产物：`COMBAT_AI_ROUTE.json` + `*.combat.deob.js`

## 总览

| 样本 | AI 路由 | 结果 | 关键指标 |
|------|---------|------|---------|
| 美团 `default.js` | obfuscator_io | **强**（引擎有效；calls 计数器漏检 base64 形态） | `isolated_decode+super_ast`；201KB→233KB；134s |
| 京东 `gatherInfo` | obfuscator_io | **强** | calls **152→0**；score 45.8→18.7；worker；124s |
| 京东 `wbc.min` | obfuscator_io | **强**（较上轮提升） | calls **2927→0**；worker+super_ast；131s |
| 小红书 `as/v2/ds` | jsvmp | **工具选对** | `__$c`；suspected=true；0.4s；未跑 Tier1 |
| 小红书 `as/v2/fp` | jsvmp | **工具选对** | `_sabo_`；suspected=true；49s；未跑 Tier1 |
| 快手 `kws5` | jsvmp | **工具选对** | `Doflamingo`/`_sabo_`；suspected=true；11s |
| 快手 `kws8` | jsvmp | **工具选对**（检测器弱） | `Jimbei`/`_ace_*`；suspected=false conf=0.3；15s |
| 快手 `kws19` | jsvmp | **工具选对**（检测器弱） | `Luffy`/`_garp_*`；suspected=false conf=0.3；21s |

## 结论

1. **AI 分流可行**：obfuscator 样本解得动；VM 样本不进 Tier1，避免卡死。
2. **京东 wbc**：本轮 worker 把 `a0_0x(...)` 调用清零，优于此前 3580→664。
3. **快手同族改名**：`Jimbei/_ace_`、`Luffy/_garp_` 与 `Doflamingo/_sabo_` 同构，但 `analyze_jsvmp` 目前只强识别后者 → AI 路由对了，静态 `suspected` 偏弱，需要 `runtime=True` 或扩 marker。
4. **浏览器侧**：本轮 MCP `browser_ok=false`，JSVMP 仅做静态分析；动态插桩复测需先恢复 CDP。

## 与硬分流方案对比

| 做法 | 实战表现 |
|------|----------|
| 流水线自动 `routed_to_jsvmp` | 曾误伤美团；启发式难维护 |
| **AI 看标记选工具（本轮）** | 8/8 路由正确；obfuscator 3/3 可解；VM 5/5 未硬跑沙箱 |
