# 小红书（xiaohongshu）mnsv2 签名逆向分析证据

## 基本信息

- 目标名称：xiaohongshu（小红书 Web 签名 x-s / x-t）
- 目标类型：Web API 请求签名（anti_param / seccore_signv2）
- 日期：2026-07-13
- 负责人：逆向工具自动化分析（crypto-hunter-lite）

## 问题描述

- 现象：上一轮用 `analyze_jsvmp` 分析 XHS 代码时返回 `suspected=true, confidence=0.7`，
  但实际并非 JSVMP 字节码 VM；`ch_jsvmp_target(target="xiaohongshu")` 因适配器占位返回
  `missing_code`（需先抓源码）。
- 失败表现：通用 `switch` 启发式把 TS 异步状态机误判为 VM 派发；适配器无真实特征，
  无法给出 sign_entry / bytecode_locator。
- 复现步骤：浏览器打开小红书 → 捕获 vendor_dynamic.js → 定位 `window.mnsv2` 调用链。

## 证据

- 目标请求：`https://edith.xiaohongshu.com/api/sns/web/v1/feed`（sample_url）
- 关键参数：请求头 `x-s` / `x-t`；`x3 = mnsv2(url, md5(url), md5(data))`
- 相关源码：
  - `xhs_signV2Init.js`（576KB）：自解密入口 `function signV2Init(){ var code=String.raw(__makeTemplateObject([...])); eval(code); }`
  - `xhs_obcode_full.js`（288KB）：`eval(code)` 执行的 ob 混淆代码主体
  - `xhs_mnsv2_real.js`（51KB）：`glb[_0xe762c0(0x73)]=function(_0x1f8d7a,_0x4ede15,_0xb2668e){...}` 真身
- 运行时变量：`mnsv2` 真身挂载 key 经 `_0xe762c0(0x73)` 解密为 `_AUuXfEG27Xa3x`，
  对外暴露为 `window.mnsv2(url, md5(url), md5(data))`，输出 `"XYS_"+自定义base64(JSON{x0..x4})`
- 网络记录：`x-s` = `XYS_` 前缀 + 自定义 base64 表
  `ZmserbBoHQtNP+wOcza/LpngG8yJq42KWYj0DSfdikx3VT16IlUAFM97hECvuRX5`

## 超级补环境

- 是否启用：否（当前仅静态定性 + 离线复现验证，未做完整补环境重放）
- 判定原因：mnsv2 离线复现被反调试 loader 阻断（见下），需浏览器原环境或专用重放
- 触发信号：反调试 loader `glb['_AUuXfEG27Xa3x'](__$c,[...])` 重写 `Function.prototype.toString`
- 补环境建议：复现需在 Node 中提供完整 `window/document/navigator/performance/TextEncoder`
  垫片，并在调用前保持 `Function.prototype.toString` 为原生外观，绕过 `err:d93135` 校验

## 验证应对

- 验证类型：静态定性 + 检测器扩展 + 适配器落地
- 处理路由：`jsvmp_detector.analyze_jsvmp` → 新增 obfuscator 维度；`jsvmp_analyzer.targets.xiaohongshu` 落地
- 是否需要人工接力：否（自动定性完成）；离线 x-s 复现为后续增强项
- 识别信号：obfuscator.io 变体五大特征（见"真正原因"）
- 证据包摘要：`cases/xhs_acrawler/{xhs_signV2Init.js, xhs_obcode_full.js, xhs_mnsv2_real.js}`

## 分析过程

- 类型判断：先排除 JSVMP（无 `_$jsvmprt` / `13*X%241` / 十六进制字符串取指），
  确认为 **obfuscator.io 变体自解密混淆**（非字节码 VM）。
- 入口定位：`seccore_signv2` → `xhsSign` → `window.mnsv2(c, u, p)`；
  真身在 `signV2Init` 内 `String.raw(__makeTemplateObject([...]))` 拼出的 ob 代码里，
  由 `glb[_0xe762c0(0x73)]=function(...)` 挂载。
- 环境补丁：Node 执行需 `global.window=global` + `__makeTemplateObject` 垫片 +
  `String.raw` 捕获式拦截（绕过模块顶层 helper 剥离导致的调用断裂）。
- 复现方法：见 `xhs_save_real.py`（捕获式 eval 触发 `eval(code)` 挂载 mnsv2 真身）。

## 误判点

- 误判点 1：上一轮 `analyze_jsvmp` 对 XHS 代码 `suspected=true` —— 实为通用 `switch`
  启发式把 TS 异步状态机（`switch(_a.label){case 0/1/2...}` 连续小整数）误判为 VM 派发。
- 误判点 2：把 mnsv2 当作"自研 VM 或强混淆"的占位猜测，未定位真实源码。
- 误判点 3：页面内 `mnsv2.toString()` 抛 `RangeError: Maximum call stack size exceeded`
  误以为是源码读取失败，实际是反调试 loader 重写了 `Function.prototype.toString`（陷阱）。

## 真正原因

- 真正原因：mnsv2 是 **obfuscator.io 变体自解密混淆**，不是 JSVMP 字节码 VM。
  其结构：`String.raw(__makeTemplateObject([...]))` 拼出 ob 代码 → 末尾 `eval(code)` →
  `_0x5ae8` 密码本 + `_0xe762c0(0xNN)` 十六进制解密 + `(function(_0x...){...})(_0x5ae8,0xNNN)`
  自解密 IIFE + `glb[_0xe762c0(0x73)]=function(_0x1f8d7a,_0x4ede15,_0xb2668e){...}` 动态挂载。
- 识别信号（ob 五大特征，已写入 `jsvmp_detector._find_obfuscator_markers`）：
  1. `String.raw(__makeTemplateObject([...]))` + `eval(code)` 自解密入口
  2. `_0x5ae8=['doeZk',...]` 十六进制命名变量 + 大字符串数组（密码本）
  3. `_0xe762c0(0x73)` 十六进制参数解密调用
  4. `(function(_0x...){...})(_0x5ae8,0xNNN)` 自解密 IIFE
  5. `glb[_0xe762c0(0x73)]=function(...)` 动态挂载（签名真身）
- 修复方式：
  - `jsvmp_detector`：新增 `_find_obfuscator_markers`（ob 维度，独立于 JSVMP 评分）；
    新增 `_is_sequential_state_machine` 排除 TS 顺序状态机 switch 误报；
    `detect()` 汇总 `obfuscator` 分数，强混淆（ob>=0.5 且无 VM 运行时标记）时抑制 VM 误判；
    `analyze_jsvmp` 返回增加 `obfuscator` 字段并给出分类指引。
  - `jsvmp_analyzer/targets/xiaohongshu.py`：从占位改为真实特征
    `vm_family="obfuscator"`、`sign_entry="window.mnsv2"`、
    `bytecode_locator` 指向 ob 特征、`replay_supported=False`（err:d93135 阻断）。

## 验证结果

- 生成位置：mnsv2 真身 = `glb[_0xe762c0(0x73)]`（解密 key `_AUuXfEG27Xa3x`），
  外层 `window.mnsv2(url, md5(url), md5(data))`。
- 本地复现方式：
  - 静态定性：`analyze_jsvmp(obcode)` → `suspected=False, obfuscator=0.9`（实测）。
  - 真身捕获：`xhs_save_real.py` 经 Node 捕获式 eval 触发 `eval(code)`，
    挂载 mnsv2 真身到 `global["_AUuXfEG27Xa3x"]`（51KB 函数体）。
  - 离线调用：传 `(url, md5(url), md5(data))` 触发 `err:d93135:í` —— 首参需特定 hex
    编码 payload，属预期强混淆，需浏览器原环境/专用重放才能完整复现 x-s。
- 验证结果（端到端 `run_target("xiaohongshu", obcode)`）：
  `engine.suspected=False`、`engine.confidence=0.1`、`obfuscator.detected=True`、
  五阶段流水线全部跑通、`next_actions` 给出 obfuscator 分类指引。误报已消除，正确归类。

## 可复用规则

- 规则 1：遇到 `String.raw(__makeTemplateObject([...]))` + `eval(code)` 即 ob 自解密混淆，
  优先走 obfuscator 检测分支，而非 JSVMP VM 假设。
- 规则 2：`switch(X){case 0/1/2...}` 连续小整数 = TS 编译状态机，不是 VM 派发，检测时需排除。
- 规则 3：页面内 `.toString()` 抛 `RangeError` 递归，通常是反调试 loader 重写了
  `Function.prototype.toString`（典型的 mnsv2/obfuscator 手法），应转 Node 离线分析。
- 规则 4：ob 混淆代码经 `eval` 挂载的函数，若模块顶层 helper（如 `__makeTemplateObject`）
  被剥离，需在全局作用域补全定义并预声明其闭包变量，才能成功触发 `eval(code)`。

## 回归说明

- 哪些点容易变：
  - `_0xe762c0(0x73)` 解密出的挂载 key（当前 `_AUuXfEG27Xa3x`）随版本迭代会变。
  - `_0x5ae8` 密码本与 `_0xe762c0` 解密偏移随时更换。
  - `err:d93135` 参数校验逻辑可能调整首参格式。
- 下次升级时先检查什么：
  - 重新抓 `vendor_dynamic.js`，确认 `String.raw(__makeTemplateObject` + `glb[...]=function`
    仍为主结构；若改用其他混淆器（如 rust/wasm），需更新 `_find_obfuscator_markers` 特征。
  - 跑 `scratch/xhs_verify.py` 回归：确认 `suspected=False & obfuscator>=0.5` 仍成立。

## 踩坑记录

- 误判 -> 真实原因 -> 识别信号 -> 修复方式 -> 可复用规则：
  - "XHS 是 VM" -> mnsv2 是 obfuscator 自解密混淆 -> ob 五大特征 ->
    新增 obfuscator 检测维度 + 适配器 `vm_family=obfuscator` -> 规则 1/2。
  - "TS 状态机 switch 被当 VM 派发" -> 连续小整数 case 是控制流序列化 ->
    `_is_sequential_state_machine` 排除 -> 规则 2。
  - "页面 toString 抛栈溢出无法读源码" -> 反调试 loader 重写原型方法 ->
    Node 离线捕获式 eval -> 规则 3/4。
  - "Node eval 报 templateObject_1 is not defined" -> 模块顶层 helper 剥离 +
    间接 eval 全局作用域解析 -> 补全 `__makeTemplateObject` 并 `global.templateObject_1=undefined` -> 规则 4。
