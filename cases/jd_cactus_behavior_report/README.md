# 京东 cactus behavior_report

## 结论

| 项 | 结果 |
|---|---|
| 接口 | `POST https://cactus.jd.com/behavior_report` |
| 请求编码 | `JSON → XOR5 → urlencode → data=` |
| 生成脚本 | `js-security-v3-rac.js` 函数 `_$w3` + `_$Co.post` |
| 响应 cFlag | `_$w4`=`XOR7+JSON.parse`；`uts/b6` 语义 XOR7 |
| 非目标 | h5st / `TDEncrypt`（`pc-tk.js`） |

## 复现

```bash
# 解码活体样本
python scratch/jd_cactus_wasm_20260719/cactus_behavior_codec.py
python scratch/jd_cactus_wasm_20260719/verify_xor_only.py
# 字符串表
node scratch/jd_cactus_wasm_20260719/run_strtable_node.js
```

## 活体复核（2026-07-20 MCP）

| 项 | 结果 |
|---|---|
| 任务 | `task_20260720_133849_ba0b905b` |
| 捕获 | `request_id=24900.259`，`POST /behavior_report` 200，body 4831B |
| XOR5 往返 | `roundtrip_ok=true`（`cactus_behavior_codec.py`） |
| 生成栈 | `bu2` → `js-security-v3-rac.js?v=20260720:5:17582` |
| 资源确认 | `performance` 已加载 `js-security-v3-rac.js`（DOM `script[src]` 可能不保留） |
| 响应 cFlag | `uts/b6` XOR7 → `window` / `prototype` / `XMLHttpRequest...` |

## 深度动态调试（2026-07-20）

| 项 | 结果 |
|---|---|
| 任务 | `task_20260720_141020_c167c5ac` |
| XOR5 断点 | `rac.js` L5 C≈18518，`evaluateOnCallFrame` dump `_$wV`（53 keys） |
| Co.post 栈 | `(anon):5:18757 → _$we:1:24358 → (anon):5:18695` |
| 密文现场 | `_$ww.data` 长度 ~4042，前缀 `~'nhF'?^X)...`（XOR5） |
| 闭包 | `_$w8` + 模块大闭包；同帧 `_$w0`/`_$Vz` 为 function |
| 详记 | `scratch/jd_cactus_wasm_20260719/DYN_DEBUG.md` |
| dump | `scratch/jd_cactus_wasm_20260719/dyn_xor5_wV_dump.json` |

## MCP 稳定链路复跑（2026-07-20 修复后）

| 项 | 结果 |
|---|---|
| 工具链 | `set_breakpoints` → `wait_paused(after_pause_seq, reason_contains=XOR5)` → `pending_scopes(peek)` |
| 断点 | `.*js-security-v3-rac[.]js.*` L5 C18471，61ms 命中 pause_seq=1 |
| `_$wV` | 53 keys；eid/jsToken/canvas/webglFp 与历史 dump 一致 |
| `_$ww.data` | 4039B，前缀 `~'nhF'?^X)...`（XOR5 密文） |
| eval 四段 | meta/km/sample/ctx 均成功（seq=1）；custom key 无覆盖 |
| 产物 | `scratch/jd_cactus_wasm_20260719/dyn_xor5_mcp_live_20260720.json` |

## km* 深度动态（2026-07-20 续）

| 项 | 结果 |
|---|---|
| 组装函数 | `_$w0` @ L5 C7234–7775（return `_$wH`） |
| 管线 | L5:17570 `_$w0()` → `_$Vz()` → XOR5 → `_$Co.post` |
| 静态映射 | `kmC=_$wJ, kmMD=_$wB, kmMM=_$wI, kmTS=_$wU, kmTEC=_$wL.length` 等 |
| 事件缓冲 | `_$Vm.push` → `_$VT`/`_$Vl` 双队列 |
| 冷启动 | `kmTEC=0`，km 数组均为 `[]`（需真实交互才非空） |
| 详记 | `scratch/jd_cactus_wasm_20260719/KM_DEEP.md` |
| 产物 | `dyn_deep_km_v2_capture.json` / `dyn_deep_km_post_capture.json` |

## 产物路径

均在 `scratch/jd_cactus_wasm_20260719/`：

- `behavior_report_20260720_plain.json`
- `behavior_report_20260720_live_mcp_plain.json`（本次 MCP 活体明文）
- `behavior_report_20260720_live_mcp_verify.json`
- `verify_live_mcp_capture.py`
- `cactus_behavior_codec.py`
- `rac_xor5_call_context.js`
- `CACTUS_DECODE.md`
- `DYN_DEBUG.md` / `dyn_xor5_wV_dump.json` / `dyn_xor5_fixed_capture.py`
