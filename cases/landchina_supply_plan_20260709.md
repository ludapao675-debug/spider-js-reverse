# landchina.com supplyPlan 翻页数据请求逆向

- 日期：2026-07-09
- 类型：请求头 Hash 校验（SHA256），无 WAF / 无加密响应 / 无验证码
- 站点：https://www.landchina.com/#/supplyPlan （中国土地市场网 · 供地计划 SPA）

## 目标请求（已确认）

```
POST https://api.landchina.com/tGyjh/plan/list
Content-Type: application/json
Body: {"pageNum":N, "pageSize":10, "startDate":"", "endDate":""}
```

- `pageNum` 是常规 query-body 字段（**不是** ctbpsp 那种路径段），`pageSize=10` 每页条数。
- 响应明文 JSON：`{code:200, msg:"操作成功", data:{total:1346, list:[...]}}`，无 DES/AES 解密。

## 防护链路（单层，已验证）

1. **仅请求头 `Hash` 校验**：缺 `Hash` → `code:301 "发生错误！请联系系统管理员！"`。
2. **无 WAF 挑战页、无客户端令牌、无验证码**（与 ctbpsp 的多层防护不同，本项目轻得多）。
3. **翻页频率限制**：连续请求过快返回非 JSON，加 `sleep(1.5)` + `Session` 会话保持即可。

## Hash 生成位置

- webpack 模块 `lPiR`（自实现 SHA256，CryptoJS 风格），入口 `i("lPiR")`；另依赖 `Ib8C`(CryptoJS 基础库)、`yLpj`(this 指针)。
- 调用点（axios header 拦截器）：
  ```js
  e.Hash = n(navigator.userAgent + (new Date).getDate() + a[a.length - 1])
  // a = url.split("/")，a[a.length-1] === "list"
  ```
- 即 `Hash = sha256_hex( UA + 当天日期(日,1-31) + "list" )`

## 算法（一句话）

**Hash = hex( SHA256( ua + day + "list" ) )**，其中 `day = new Date().getDate()`（浏览器本地时区「日」）。

## 离线复现（Python）

见 `scratch/landchina_supply_plan.py`：

```python
import hashlib, datetime
def make_hash(ua):
    day = str(datetime.datetime.now().day)
    return hashlib.sha256((ua + day + "list").encode()).hexdigest()
# headers["Hash"] = make_hash(UA) 后 POST 即可
```

> 注：`verify=False` 仅为绕过本机环境的证书校验问题（TLS 层，非站点防护）；翻页需 `sleep(1.5)` 避免频率限制。

## 验证结果

- 多页验证：page 1/2/3 各 10 条，`total=1346`，`gyjhGuid` 无重复 → 翻页有效。
- 不带 Hash → `301` 失败；带 Hash → `200` 成功。
- 样本保存：`scratch/landchina_sample.json`。

## 证据

- 旧逆向资料（复用）：`reverse_practice2/landchina/demo.py` + `demo.js`（liyf 2022 仓库）。
- 探针脚本：`scratch/landchina_probe.py`（带/不带 Hash 对比）。
- 复现脚本：`scratch/landchina_supply_plan.py`。

## 踩坑记录（误判 → 真实原因 → 识别信号 → 修复方式 → 可复用规则）

1. **误判**：站点 2022 后已升级，需重新逆向。
   **真实原因**：旧 `Hash` 方案当前仍完全有效，仅"可不带 Hash"变为"必须带"。
   **识别信号**：一步探针（带/不带 Hash 对比）即确认 200 vs 301。
   **修复方式**：直接复用旧 SHA256 算法，无需重新扣 webpack。
   **可复用规则**：遇项目内已有旧资料，**先一步探针验证当前有效性**，再决定复不复用（避免盲目重分析，也避免盲目信任）。

2. **误判**：直接 `requests` 报 SSL 错误 = 站点 WAF。
   **真实原因**：本机 CA/代理导致 TLS 证书校验失败，是**环境问题非站点防护**。
   **识别信号**：错误为 `SSLCertVerificationError`（TLS 层握手阶段），并非 HTTP 挑战页。
   **修复方式**：`verify=False` 临时绕过（生产应配正确 CA）。
   **可复用规则**：**TLS 层证书错误先查本地证书/代理，不当 WAF 处理**（呼应 `docs/reverse_lessons.md` 坑点 6 的镜像）。

3. **误判**：旧注释"不携带 Hash 也能拿到数据"可信。
   **真实原因**：当前服务端强制校验 Hash，缺则 301。
   **识别信号**：不带 Hash 返回 `code:301`。
   **修复方式**：必须带 `Hash` 头。
   **可复用规则**：旧资料里"可不带/可省略"类描述，**以当前实测为准**。

4. **误判**：翻页第 2 页 JSON 解析失败 = Hash/算法随 `pageNum` 变化算错。
   **真实原因**：连续请求触发**频率限制**，返回空/非 JSON。
   **识别信号**：第 1 页成功、第 2 页起非 JSON，加间隔后恢复。
   **修复方式**：请求间 `sleep(1.5)` + `requests.Session()` 会话保持。
   **可复用规则**：**翻页批量失败先排除频率限制（加间隔/保持会话），再怀疑算法**。

## 可复用规则（汇总）

- 先查项目内旧资料 → 一步探针验证当前有效性 → 有效则直接复用。
- TLS 证书错误 ≠ WAF，先排查本地 CA/代理。
- 旧资料"可不带"类描述以当前实测为准。
- 翻页批量失败先加间隔 / 保持会话，排除频率限制。

## 回归说明

- 易变点：Hash 算法是否被替换为更复杂签名；是否新增 WAF / 验证码。
- 下次升级先检查：① 不带 Hash 是否仍 301；② 是否出现挑战页 / 令牌；③ 频率限制阈值。
- 脆弱点：`Hash` 用本地「日」，跨时区 / 午夜切换可能与服务端差一天 → 生产建议用服务端时间。
