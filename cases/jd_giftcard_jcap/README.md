# 京东礼品卡 JCAP 落地（Headless Blink + `/check`）

> WASM / AwPF 补环境沿用方案 B：真实 Blink 跑官方 `jcap_ujb96b.js` + `jcap_fp.wasm`（JSDOM → AAHE，禁止当正式通道）。
> **完整交接与待办见 [`HANDOFF.md`](./HANDOFF.md)**（2026-07-31 接力第 2 轮）。

## 已打通

| 步骤 | 结果 |
|------|------|
| Cookie + querySid | ✅ |
| `POST /cgi-bin/api/fp` | ✅ `ct` **AwPF**，`code:0`，拿 `st` |
| `POST /cgi-bin/api/check`（拉拼图 tp=30） | ✅ |
| 页内 WASM 生成提交密文 | ✅ **`tk`/`ct`/`cs` 均为 AwPF** |
| `touche_message` 采集机制还原 | ✅ **完整静态还原**（localStorage + click-only on PC） |
| `touchList` 注入对齐 | ✅ 合成结构已进 WASM，`tk` 2k→3.1k |
| 拼图缺口过验 | ❌ 仍 **`16807`**（缺口检测分叉 81/140/171 + tk 仍差活体 ~2k） |

## 关键结论（16807）

- **`web_jcap_report` / `sgm-w`：可忽略**，不是失败原因。
- **用户确认：`16807` = 滑块位置不对的标准返回**（手动滑错也返回这个），非轨迹风控。
- `touche_message` 缺失曾致 `tk` 偏短，但**注入后仍 16807** → 非唯一因素。
- **当前两大疑点**：① 缺口位置检测不准（OpenCV 三策略严重分叉）；② `A`（几何+list+动态键）体积未对齐活体（tk 3143 vs 5170）。
- 二次 `/check` 的 `st` 来自一次 check，不是 `/fp`。

## 运行

```bash
cd cases/jd_giftcard_jcap
npm i

# 推荐：附着已开调试端口的 Edge
set JCAP_CDP=http://127.0.0.1:9222
node repro_node_headless_blink.js

# 或独立浏览器
set JCAP_HEADED=1
node repro_node_headless_blink.js
```

退出码：`0` 通关；`3` AwPF 已出但验证失败；`2` 其它失败。
产物：`repro_node_output.log`、`repro_check_result.json`（含 `capturedTouchList`/`injectedTouchList`）、`debug/b1_cur.png`、`debug/b2_cur.png`、`run_out.txt`。

## 核心文件

| 文件 | 作用 |
|------|------|
| **`HANDOFF.md`** | **逆向交接：请求链、加密、SDK 轨迹全还原、注入修复、待办** |
| `repro_node_headless_blink.js` | 落地主脚本（已含 touche_message 注入修复） |
| `solve_gap_opencv.py` | b1/b2 缺口（`--b1/--b2` 或 `--json`） |
| `track_sample_live.json` | 活体 xyList 样本 |
| `extract_live_track.py` / `resample_track.py` | 样本抽取与重采样 |
| `jcap_ujb96b.js` / `jcap_fp.wasm` | 官方 SDK |
| `jd_cookies.json` | Cookie（勿提交敏感环境） |
| `debug/b1_cur.png` / `b2_cur.png` | 本轮挑战原图（供离线核验缺口） |
| `run_out.txt` | 最近一次复现完整输出 |

> ⚠️ `scratch/` 目录已丢失（`jcap_check_encrypt_analysis.md` / `pause_scope.json` 不存在），如需活体原始 pause 数据需重新断点导出。

## 下次接着做

1. **离线核验缺口**：`python solve_gap_opencv.py --b1 debug/b1_cur.png --b2 debug/b2_cur.png`，对照三策略分叉定真实 bestX。
2. **用户实地观看**：改 repro 为多轮循环（不关浏览器），按计算 offset 滑几次，肉眼判断拼图块是否对准缺口。
3. 若缺口对准仍 16807 → **`FA` 断点导出完整 `A` 字符串**，对比活体长度/字段，补齐 `A` 侧体积。
4. 活体手动成功滑一次，断点 `FA` 导出真实 `f.touchList`，用真实样本替换合成。
5. 通关后：多样本 + 负向样本 → `ch_task_finish` / 归档。

细节与优先级见 [`HANDOFF.md` §8](./HANDOFF.md)。
