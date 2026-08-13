# 解混淆功能等价性验证报告（抖音 webmssdk.es5.js 1.0.0.53）

> 验证日期：2026-08-04
> 目标：确认纯静态解混淆（webcrack worker）**不仅结构干净，且语义正确**——
> 解码器还原后输出与原始运行时一致。

## 1. 样本

- 原始混淆样本：`webmssdk.es5.js`（322,568 字节，抖音 `byted_acrawler` SDK 1.0.0.53）
- 静态解混淆输出：`webmssdk_worker_out.js`（webcrack worker 引擎产出）
- 关键解码函数：`w_0x5c3140`（hex→字符串数组解码器，纯函数、确定性）

## 2. 结构干净指标（已验证）

| 指标 | 原始 | 解混淆后 |
|------|------|----------|
| `while(!![])` 控制流平坦化 | 大量 | **0** |
| `_0xNNNN(0x...)` 字符串数组间接调用 | 大量 | **0** |
| 可读字符串常量 | 极少 | **196+** |
| 业务函数（frontierSign/getReferer/report） | 被包在 VM | **保留** |

## 3. 功能等价性验证（核心闭环）

**方法**：在 Node 中同时运行两份 `w_0x5c3140` 纯解码段，共享**同一份 live 真实 `_0x458f30` 字符串数组**，对**同一条 live 配置串**（数组索引 5，542 字符 hex）解码，比较输出的 `_0x408609` 字符串数组是否逐元素相等。

- `raw_short.js`：从 live 页抽取的原始 `w_0x5c3140`（保留 `w_0x25f3` 字符串解码器间接调用，切割到 `return _0x408609`）
- `w5c_deob_short.js`：webcrack 静态还原后的纯解码（已内联 `String.fromCharCode`/`slice`，无 `w_0x25f3` 调用）
- `live_arr.js`：live 页抓取的 616 元素 `_0x458f30` 真实数组
- `live_hex.txt`：live 页配置串

**结果**：

```
errA: null
errB: null
aLen: 12  bLen: 12
same: true      ← raw 与 deob 解码数组逐元素相等
```

**结论**：纯静态解混淆在解码器层面与原始运行时**语义等价**，闭环成立。

## 4. 回归测试

- `tests/server/test_deobfuscate_pipeline.py::test_semantic_equivalence_raw_vs_deobfuscated_decoder`
  通过子进程调用 `equivalence_node_test.js`，复用上述 live 样本，断言 `same: true`。
- 运行：`python tests/server/test_deobfuscate_pipeline.py`（需 Node 可用）
- 全部测试：string_array / super_obio_contract / no_eval_runtime / **semantic_equivalence** 均通过。

## 5. 已知边界（诚实记录）

- `ch_deobfuscate_js` 的 MCP 层 `timeout_ms` 已从 120s 放宽到 300s 默认（HTTP 窗口 330s），
  不再被 2 分钟提前切断。
- 但后端 worker 引擎有 **~300s 内部硬封顶**（`server.py:723` `min(300, ...)`）。
  单文件 >300s（如 322KB 的 webmssdk）仍会超时——这**不是** MCP 超时问题，而是 worker 引擎自身上限。
  超大文件应改用 `engine=super_obio` 并升档 `deep`（默认 600s，可提到 3600s），或分段处理。
- 解混淆**禁止运行时执行 JS**（`ch_deobfuscate_auto` / `ch_deobfuscate_js` 均为纯静态 AST；
  仅 `ch_decode_obfuscated_array` 作为显式只读探针允许页面内执行）。
