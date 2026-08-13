# 京东礼品卡 JCAP 逆向交接（HANDOFF）

> 更新：2026-07-31（缺口换算修正：减去 `cropOffsetX`）
> 目标：礼品卡绑定页拼图验证码协议复现；当前卡在二次 `/check` → `code:16807`。
> 原则：**加密链路已通（AwPF）**；用户确认 `16807` = **滑块位置不对**的标准返回（非轨迹风控）。
> `web_jcap_report` / `sgm` 可忽略。

---

## 0. 本轮（2026-07-31）核心进展摘要

| 事项 | 结论 |
|------|------|
| 肉眼多轮对照 | ✅ 用户确认：拖距**系统偏大约 10~20px**（不是 ±2~4） |
| 偏大根因 | ✅ **换算公式错**：把 `bestX`（块**内容**左缘应对齐的底图 x）直接当滑块位移；未减去 b2 左侧黑边/透明 `cropOffsetX`（常见 5~12，再加取整/描边可达 ~10–20） |
| 正确公式 | `offsetCss ≈ (bestX - cropOffsetX) * (trackW / bgW)`；旧式 `bestX * scale` 会多拖 |
| `touche_message` / `touchList` 采集机制 | ✅ **已完整静态还原**（见 §4.2） |
| 注入合成 `touche_message` | ✅ `tk` 2k→3.1k；注入后仍 16807（当时主要是缺口拖距偏大） |
| OpenCV 稳定性 | ⚠️ 密纹理图仍可能分叉/飘（如某轮 bestX=209）；换算修完后需再肉眼验 |

> ⚠️ 关键转折：用户明确纠正「16807 = 滑块位置不对的标准返回」（手动滑错位置也返回这个），推翻了早期"轨迹风控"的过度推断。注入 `touchList` 后仍 16807，强烈指向**缺口位置检测仍不准**，或 `tk` 还差活体 ~2k（3143 vs 5170）的 `A` 侧未补齐。

---

## 1. 当前状态总览

| 阶段 | 状态 | 证据/备注 |
|------|:----:|-----------|
| Cookie + `querySid/pc` → `si` | ✅ | `jd_cookies.json`（len 2310） |
| `POST /cgi-bin/api/fp` | ✅ | `ct` 前缀 **AwPF**，`code:0`，返回 `st`/`fp` |
| 一次 `/check` 拉图 `tp=30` | ✅ | `img.b1` 底图 / `img.b2` 滑块 |
| 提交密文 `tk/ct/cs` | ✅ | 页内 WASM，前缀均为 **AwPF** |
| `touche_message` 注入对齐 | ✅ | `f.touchList`=10 元素已确认进 WASM |
| 二次 `/check` 过验 | ❌ | `code:16807`，`s_code:16130`，msg「验证失败，请重新验证」 |
| JSDOM / sdenv 纯 Node | ❌ | 易产出 **AAHE**，勿作正式通道 |

**复现最新对照（CDP attach 真实 Edge，2026-07-31）**

| 轮次 | 注入 | `tk.len` | `ct.len` | `cs.len` | gap offsetCss | code |
|------|:----:|--------:|--------:|--------:|--------------:|:----:|
| 注入前 | ❌ | 2012 | 1948 | 1522 | 154 | 16807 |
| 注入后#1 | ✅ | 3186 | 1948 | 1522 | 158 | 16807 |
| 注入后#2 | ✅ | 3143 | 1948 | 1543 | 169 | 16807 |
| 活体成功 | — | **~5170** | ~1948 | ~1522 | (手滑对) | 0 |

- `ct`/`cs` 与活体量级已对齐 → 差距**只剩 `tk`**（3143 vs 5170，差 ~2k）。
- `tk = k([a, s, A, JSON.stringify(f)])`，`f` 已注入对齐 → **剩余 ~2k 差距大概率在 `A` 侧**（几何 + list + 动态混淆键），或 `f` 合成内容仍不够"像活体"。

---

## 2. 请求链（活体与复现一致）

```text
1) POST .../giftcard/querySid/pc          → si
2) POST https://jcap.m.jd.com/cgi-bin/api/fp   → ct(AwPF), st, fp
3) GET  https://jcapmonitor.m.jd.com/web_jcap_report?...&status=0
        interfaceId: 268435458=/fp , 268435460=/check , 268435459=失败后
        → 遥测，非过验条件
4) POST .../cgi-bin/api/check             → tp=30 拼图 + 新 st（二次 check 必须用此 st）
5) POST sgm-w.jd.com/h5                   → 埋点，可忽略
6) 拖滑块后 POST .../cgi-bin/api/check    → tk/ct/cs；成功 code:0 / 失败 16807
7) 失败后 POST .../cgi-bin/api/refresh    → 重新发题（tp=30，新 b1/b2/n1）
```

### 16807 归因（已验证 + 用户确认）

| 请求 / 因素 | 是否导致 16807 |
|------|:--------------:|
| `web_jcap_report?status=0` | **否**（复现照发仍 16807） |
| `sgm-w.jd.com/h5` | **否** |
| `touche_message` 缺失 | **曾导致 tk 偏短**，但注入后仍 16807 → 非唯一因素 |
| **滑块位置不对** | **是**（用户：手动滑错位置也返回 16807） |
| 缺口 `bestX` 检测不准 | **高度怀疑**（OpenCV 三策略分叉 81/140/171） |

SDK 内 `16807` → 文案映射约 `code_14`（验证失败），不是缺上报。

---

## 3. 加密管线（断点已坐实）

脚本：`jcap_ujb96b.js` **v2.8.5**（832KB / 39 行压缩；`storage.360buyimg.com/.../jcap_ujb96b.js`）
断点文本：`k([a,s,A,JSON.stringify(f)])`（函数 `FA`，源码偏移 `@600868`）

```js
s = e.st;  // 注意：二次 check 用「一次 check」返回的 st，不是 /fp 的 st
A = encodeURI(A);  // UI 几何 + list + 动态混淆键
f = { touchList: q.d("touche_message") };
C = wA.getSensorInfo(u, t);
Q = {
  si: a, lang: c,
  tk: k([a, s, A, JSON.stringify(f)]),   // → WASM getTK
  ct: x([a, C]),                         // → WASM getCTData
  cs: "", version: 3, client: B
};
// cs = F([si, JSON.stringify({rec, fpt})])
// interfaceId = 268435460, interface = "check"
```

| WASM/闭包 | 作用 |
|-----------|------|
| `k` → `getTK` | 轨迹+touch 加密 |
| `x` → `getCTData` | 传感器/环境 |
| `F` | stack/file 路径类 `cs` |

**禁止**在 Node/JSDOM 重写 `k/x` 当正式方案；环境指纹与 `/fp` 同约束，JSDOM → AAHE。

> ⚠️ `scratch/` 目录在本仓库**不存在**（HANDOFF 早期版本引用的 `scratch/jcap_check_encrypt_analysis.md` / `scratch/pause_scope.json` 已丢失）。如需原始 pause 数据，需重新在活体 `FA` 断点导出。

---

## 4. SDK 轨迹采集（已完整还原）

### 4.1 拼图滑块 `xyList` → 上报字段 `A.list`

源码要点（`jcap_ujb96b.js`）：

```js
// start
moveX = pageX; moveY = pageY; lastTime = Date.now();
xyList.push([0, 0, 0]);

// move（document.onmousemove）
i = pageX - moveX;                    // 相对按下点的水平位移
c = pageY - moveY;                    // 垂直漂移
a = main_img.width - slot_img.width;  // 最大可拖距离
if (0 <= i && i <= a) {
  // translate 滑块/拼图块
  xyList.push([Number(i.toFixed(2)), Number(c.toFixed(2)), Date.now() - lastTime]);
  lastTime = Date.now();
}

// end
if (xyList.length < 2) reset;
else → 组装 A = { ht, wt, bw, sw, mw, list: xyList, ii, /*动态键*/ }
     → checkCaptcha → FA 加密提交
```

- 第三维是 **与上一点的时间差 dt（ms）**，不是累计时间（活体序列会出现 273→215 回落）。
- 活体 `y` 恒为 `0`；几何：`ht≈179, wt/sw≈290, bw≈48, mw≈69`。
- DOM 实测：bg natural 275×170，display 271.27×167.69；handle 48×48；trackW=271.27。

### 4.2 `touche_message` → `f.touchList`（✅ 已完整静态还原）

**存储后端 = `localStorage`**（源码偏移 `@176400–177100`）：

```js
// getter N(A)：优先 localStorage.getItem，失败回退内存 M["captcha_storage"][A]
function N(A){
  try { return JSON.parse(window.localStorage.getItem(A) || "{}"); }
  catch(e){ return M["captcha_storage"][A]; }
}
// setter R(A,t)：写 localStorage.setItem(A, JSON.stringify(t))
function R(A,t){ try { localStorage.setItem(A, JSON.stringify(t)); } catch(A){} }
```

- `q.d(k)` = 取（→`N`），`q.l(k)` = 清（→`localStorage.removeItem` + `delete M[...]`），`q.n(k,v)` = 存（→`R`）。
- key 即字面字符串 **`"touche_message"`**。

**采集监听器**（源码偏移 `@128000–130300`）：

```js
var c={}, g=0;
document.addEventListener("touchstart", function(A){
  c.did=...; c.cn=...; c.time=Date.now(); c.pt=[]; g=Date.now();
});
document.addEventListener("mousemove", function(A){
  c.pt.push([r.clientX, r.screenY, r.pageX, r.pageY, Date.now()-g]); g=Date.now();
});   // ⚠️ PC 端无 touchstart → c.pt 未定义 → push 抛错被 try/catch 吞 → 不写入
document.addEventListener("touchend", function(A){
  // 把本次手势 c（含 pt）压入全局数组 i，裁剪到末 10 个，q.n("touche_message", i)
});
document.addEventListener("click", function(A){
  g={did, cn, sx:A.screenX, sy:A.screenY, px:A.pageX, py:A.pageY, time:Date.now(), type:"click"};
  s = q.d("touche_message"); s.push(g); 裁剪到末 10; q.n("touche_message", s);
});
```

**关键结论（PC 端 `client:"pc"`）：**

- `touche_message` = 数组（**≤10 个元素**，超过则 `slice` 保留末 10）。
- 元素为**异构**两种形状：
  - 触摸手势：`{did, cn, time, pt:[[clientX, screenY, pageX, pageY, dt], ...]}`
  - 鼠标点：`{did, cn, sx, sy, px, py, time, type:"click"}`
- **PC 端只有 `click` 监听写入**（因为 `c.pt` 仅 `touchstart` 初始化，纯鼠标无 touchstart）。
- 成功时（`code==0`）`Object(q.l)("touche_message")` **清空**（源码偏移 `@622291`）。
- 这是**跨整个会话累积**的行为数据，不是单次滑块轨迹。

**复现脚本根因**：旧 `page.mouse.move` 游走（40+25 次）全是 `mousemove`、无 `click` → SDK 完全没录入 → `touche_message` 空 → `tk` 仅 ~2k。

### 4.3 活体样本

文件：`track_sample_live.json`（由 `extract_live_track.py` 从 `scratch/pause_scope.json` 抽出，scratch 已丢失需重导）

| 项 | 值 |
|----|-----|
| 点数 | 25 |
| 终点 x | 130 |
| Σdt | 7803 ms |
| 长停顿 dt | 800 / 909 / 600 / 3204 |
| y | 全 0 |

重采样：`resample_track.py` / 脚本内 `resampleTrack(sample, bestX)`。

### 4.4 注入修复（已实现，见 `repro_node_headless_blink.js`）

拖拽前在页内注入（`page.evaluate`）：

1. 合成 `touche_message` 数组 = 9 个 `{...type:"click"}` 环境点击点 + 1 个 `{did,cn:"move-img",time,pt:[[clientX,screenY,pageX,pageY,dt]...]}` 拖拽手势（pt 23 点，x 从 0 到 offset）。
2. 覆写 `Storage.prototype.getItem`：当 `key==="touche_message"` 返回合成 JSON（**避免被滑块 mouseup 触发的 click 覆盖**）。
3. hook `JSON.stringify`：捕获实际提交的 `f`（含 `touchList`）→ `window.__captured`，脚本末尾回读存 `result.capturedTouchList`。
4. 拖拽后把本轮 `b1/b2` 落盘 `debug/b1_cur.png` / `debug/b2_cur.png` 供离线核验。

**验证结果**：`f.touchList` 实际提交 = 10 元素（9 click + 1 手势），`tk` 2012→3143。**仍 16807**。

---

## 5. 缺口算法

| 方法 | 文件 | 说明 |
|------|------|------|
| OpenCV 多策略 | `solve_gap_opencv.py` | Canny/灰度 `matchTemplate` + 白边；**约束 y 在 piece 高度带**；过滤 `inf` |
| 页内 JS 启发式 | `repro_node_headless_blink.js` → `computeGapFromDataUrls` | 竖边能量；易不准，作兜底 |
| 坐标换算 | `offsetCss = (bestX - cropOffsetX) * (trackW / bgW)` | **已修**：旧式 `bestX*scale` 会多拖约 `cropOffsetX`（10~20px） |

已知坑：

- 灰度全图匹配可能漂到水珠纹理（错误 y）→ 必须 y-band
- 带 mask 的 `matchTemplate` 偶发 `score=Infinity` → 已改为无 mask + 过滤非有限值
- JS 与 OpenCV 曾差 ~12px（108 vs 120）足以导致失败
- **2026-07-31 实测：同一图 OpenCV 三策略严重分叉** —— edge→171、gray→140、white_outline→81，`bestY=70`。最终选 edge 171（offsetCss 169）仍 16807。**缺口检测稳定性是当前最大疑点。**

公开参考：`TM_CCORR_NORMED` + 样本轨迹重采样（同类京东滑块文）。

---

## 6. 落地脚本用法

主脚本：`repro_node_headless_blink.js`（已含 §4.4 注入修复）

```bash
cd cases/jd_giftcard_jcap
npm i

# A) 真机 attach（推荐继续调轨迹）
set JCAP_CDP=http://127.0.0.1:9222
node repro_node_headless_blink.js

# B) 独立 Headless / Headed
set JCAP_HEADED=1
node repro_node_headless_blink.js
```

| 退出码 | 含义 |
|:------:|------|
| 0 | `/check` 通关 |
| 3 | AwPF 密文已出，验证失败（缺口/轨迹） |
| 2 | 其它失败 |
| 1 | 异常中止 |

产物：`repro_node_output.log`、`repro_check_result.json`（含 `gap`/`drag`/`reports`/`finalCheck`/`capturedTouchList`/`injectedTouchList`）、`debug/b1_cur.png`、`debug/b2_cur.png`、`run_out.txt`。

辅助：

| 文件 | 作用 |
|------|------|
| `solve_gap_opencv.py` | CLI：`--json {b1,b2}` 或 `--b1/--b2` |
| `extract_live_track.py` | 从 pause_scope 抽 list |
| `resample_track.py` | `--best-x N` 重采样 |
| `track_sample_live.json` | 活体轨迹样本 |
| `repro_node_sdenv_perfect.js` | JSDOM 探针（AAHE 风险，仅调试） |
| `analyze_jcap.py` / `analyze_jcap_context.py` | 早期静态分析草稿 |

---

## 7. 证据与历史 ID（便于回查）

| 项 | 值 |
|----|-----|
| Task | `task_20260730_102333_04111ac9` |
| 活体断点 | `k([a,s,A,JSON.stringify(f)])` @ jcap_ujb96b.js `@600868` |
| 活体成功 check 样本 | entry **335**，`tk≈5170` |
| CDP attach | port **9222**，`capture_profile=safe_capture`，Edge pid 27348，tab `8ED955455AA4017C3DFAB292E5B886C0` |
| 源码定位 | FA `@600868`；成功清空 `@622291`；采集监听器 `@128000–130300`；存储后端 `@176400–177100` |
| 本轮复现日志 | `run_out.txt`、`repro_check_result.json`、`debug/b1_cur.png`、`debug/b2_cur.png` |
| 加密分析稿 | ~~`scratch/jcap_check_encrypt_analysis.md`~~（已丢失，需重导） |
| Pause 原文 | ~~`scratch/pause_scope.json`~~（已丢失，需重导） |

---

## 8. 后续逆向待办（按优先级）

### P0 — 缺口位置精确性（当前最大疑点）

1. **离线核验 `debug/b1_cur.png`/`b2_cur.png`**：用 `solve_gap_opencv.py --b1 debug/b1_cur.png --b2 debug/b2_cur.png` 单独跑，人工核对真实缺口 x；当前 OpenCV 三策略分叉 81/140/171，可信度低。
2. 让用户**多次手动滑动**观察：脚本滑到 `offsetCss≈169` 时拼图块是否真的对准缺口（用户已要求实地观看）。
3. 评估 `ddddocr` 或「只匹配白描边」专用分支；考虑固定 `bestY`（piece 高度带）后再只搜 x。
4. 确认拖距应对 `G(i, a, a)` 映射：过验看的是**滑块位移 i**，还是拼图块 `g`；piece 在 b2 内 `pieceBox.x=12` 有偏移，需确认是否要 `+cropOffsetX`。

### P0 — `A` 侧体积对齐（tk 仍差活体 ~2k）

1. 注入 `touchList` 后 `tk=3143` vs 活体 `5170`，差 ~2k；`ct/cs` 已对齐 → 差距在 `tk` 的另一个输入 `A`。
2. `A = encodeURI(A)`，A = 几何 + `list` + **动态混淆键**。需在 `FA` 断点导出**完整 `A` 字符串**与活体对比长度/字段。
3. 复现用的是 `track_sample_live.json` 重采样 25 点；活体 `A.list` 结构是否含更多字段（动态键）未知。
4. 方案：hook `k` 或 `encodeURI` 抓 `A`；或抓活体 `A` 落盘后离线复现。

### P1 — `touche_message` 活体样本采集

1. 合成 `touchList` 虽进 WASM，但内容是随机点；服务端若校验行为合理性（如点击点分布/时序）仍可能拒。
2. 在活体**手动成功滑一次**时，`FA` 断点导出真实 `f.touchList`（完整 10 元素），与合成对比；用真实样本重采样替换合成。
3. 注意：成功时 `q.l` 会清空 `touche_message`，断点需在清空前抓（`FA` 在清空之前执行）。

### P1 — `st` 两阶段与会话

1. 二次 check 的 `st` 必须来自一次 check 响应（脚本已由页内 SDK 自动带，纯协议复现时勿用错）。
2. `s_code:16130` 含义未在 SDK 明文搜到，可对报文/错误码表再挖。

### P1 — 环境

1. 正式通道保持 **真实 Blink**（CDP attach 优先）。
2. 页面残留 `#captcha_dom` / `.captcha_drop` 会挡点击，脚本已尝试 remove。
3. 不要把当前稳定页切回 `capture_profile=full` 硬注；缺证据时用隔离实例。
4. 后端须用 `d:\python_work\venv` 启动（系统 Python310 缺 uvicorn）。

### 已完成（本轮）

- ✅ `touche_message` 全链路静态还原（采集/存储/清空）
- ✅ 复现脚本 bug 修复（注入合成 `touchList`，`tk` 2k→3.1k）
- ✅ b1/b2 落盘供离线核验

### 不做 / 已排除

- 补发 `web_jcap_report` / `sgm` 当过验手段
- JSDOM 补环境冲 AwPF（已证伪）
- 盲目 F11 跟栈（加密入口已定位到 `FA`/`getTK`）
- 把 16807 归因为"轨迹风控"（用户已纠正：就是位置不对）

---

## 9. 建议的下次启动步骤

```text
1. ch_health / 确认 Edge --remote-debugging-port=9222（attach 模式）
2. 读本 HANDOFF（重点 §0 摘要 + §4.2 还原 + §8 待办）
3. 离线核验缺口：python solve_gap_opencv.py --b1 debug/b1_cur.png --b2 debug/b2_cur.png
   对照 run_out.txt 里 OpenCV 三策略分叉（81/140/171），人工定真实 bestX
4. 让用户实地观看：改 repro 为多轮循环（不关浏览器），按计算 offset 滑几次，
   用户肉眼判断拼图块是否对准缺口
5. 若缺口确认对准仍 16807 → 转 P0「A 侧体积对齐」：FA 断点导出完整 A 字符串
6. 通关后：多样本 + 负向样本 → ch_task_finish / 归档 README
```

通关判定：二次 `/check` `code:0`，且业务侧不再「验证失败」；加密 AwPF alone 不足。
