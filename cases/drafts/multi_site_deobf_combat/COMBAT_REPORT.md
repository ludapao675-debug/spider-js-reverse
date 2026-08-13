# Multi-site deobf combat（小红书 / 京东 / 快手 / 美团基线）

实战时间：2026-08-05。流水线：`worker → webcrack → Tier1 isolated_decode → Super AST`（未开 Super Obio）。

## 总览

| 站点 | 样本 | 混淆类型 | 结果 | 关键指标 |
|------|------|----------|------|---------|
| 美团 | `default.js` | obfuscator.io 字符串数组 | **强** | decoder calls **3073→0**；Tier1 内联 **2895** |
| 小红书 | `as/v2/ds` | 字符串壳 + **JSVMP 字节码** | 正确跳过 | `__$c` hex VM；硬跑会卡死 |
| 小红书 | `as/v2/fp` | **JSVMP**（`__$c` + 巨量 opcode） | 正确跳过 | 先前无门禁时卡死数分钟 |
| 京东 | `gatherInfo.js` | obfuscator.io | **强** | calls **158→0**；score **45.8→18.7**（worker） |
| 京东 | `wbc.min.js` | obfuscator.io（`a0_0x` 函数返回数组） | **中** | calls **3580→664**；Tier1 `no_string_array_pattern` |
| 快手 | `kwf_sdk.js` | 非字符串数组 | 弱 | 仅 Super AST 轻清理 |
| 快手 | `kws-5/8/19-obfuscated` | 自研 VM（`Doflamingo`/`_sabo_*`） | 弱（类型对） | 非 `_0x` 数组；需 JSVMP/专用 VM 路径 |

产物目录：`cases/drafts/multi_site_deobf_combat/`

## 分站点结论

### 1. 美团 — Tier1 最强场景

- 引擎：`isolated_decode` + `super_ast`（worker/webcrack 被判 format-only）
- `items_count=2895`，解码调用清零
- 注意：混淆分可能略升（展开字符串后 scorer 特征变化），**以 decoder_calls / 明文内联为准**，不要只看 score

### 2. 小红书 — 分流正确才叫稳定

- `ds`/`fp` 都是「字符串数组外壳 + 自研/JSVMP 字节码解释器」
- Tier1 **不应**硬解；正确行为是识别 `__$c` / unicode opcode / opcode switch 后跳过
- 稳定性证据：无门禁时 `fp` 曾挂死；加 JSVMP 门禁后 0 秒跳过

### 3. 京东 — 经典 obfuscator.io，gzip 要注意

- CDN 常返回 **gzip**；不解压会得到二进制垃圾 → score≈0（首轮踩坑已修）
- `gatherInfo`：worker 即可打穿，calls 清零
- `wbc.min`：`function a0_0x258a(){ var _0x...=[...] }` 形态，**Tier1 当前认不出顶层字符串数组**；worker 去掉大部分，仍剩 ~664 次解码调用 → 下一刀应扩 Tier1 的 function-returning array 检测

### 4. 快手 — 标注 obfuscated 的多是 VM

- 直播页真实脚本：`kws-*-obfuscated.*.js`（`Doflamingo` + base64 字节码）
- 不是 obfuscator.io；Super AST 只能做轻量格式/对象清理（score ~41→40）
- 应走 `ch_jsvmp` / 专用 VM 追踪，而不是期待字符串内联

## 稳定性 verdict

1. **对 obfuscator.io 字符串数组：稳定且强**（美团、京东 gatherInfo）。
2. **对 JSVMP / 自研 VM：稳定的前提是分流**，不能硬跑 sandbox（小红书 fp、快手 kws）。
3. **已知缺口**：`a0_0x` 函数返回数组（京东 wbc）Tier1 未覆盖；worker 可部分消化。
4. **抓样注意**：京东等 CDN 需 gzip 解压；否则“解混淆失败”是假阴性。

## 建议下一步（工程）

1. Tier1 支持 `function xxx(){ var _0xarr=[...]; return _0xarr; }` + `a0_0x` 前缀。
2. 流水线入口加轻量 JSVMP/VM 门禁（`__$c` / `Doflamingo` / 超长 base64 bytecode），避免再 hang。
3. 快手 `kws-*` 单独建 case，走 JSVMP 工具链而不是 deobf auto。
