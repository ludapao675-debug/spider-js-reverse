# Expedia 机票搜索 API 逆向案例

> **站点**: https://www.expedia.com/cn/Flights  
> **逆向日期**: 2026-08-13  
> **风控层**: Akamai Bot Manager + DataDome  
> **整体状态**: ⚠️ 协议层已完成，Bot 检测层未逆向（靠 Cookie 注入绕过）

---

## 实现状态总览

| 模块 | 状态 | 说明 |
|------|------|------|
| GraphQL 端点 | ✅ 已实现 | `POST https://www.expedia.com/graphql` |
| 两步请求流程 | ✅ 已实现 | FormLoaded → SearchResultsLoaded |
| APQ Hash | ✅ 已实现 | 从真实请求抓包提取，固定值 |
| 请求头结构 | ✅ 已实现 | 含 `x-enable-apq: true` 关键头 |
| 响应数据解析 | ✅ 已实现 | 价格、赞助标注字段路径已确认 |
| TLS 指纹伪造 | ✅ 已实现 | `curl_cffi impersonate=chrome120` |
| `_abck` 生成算法 | ❌ **未实现** | Akamai sensor.js，极度混淆 |
| `bm_sz`/`bm_sv` 生成 | ❌ **未实现** | Akamai 行为评分，服务端绑定 |
| `datadome` 生成算法 | ❌ **未实现** | DataDome JS SDK，设备指纹采集 |
| 无浏览器全自动运行 | ❌ **未实现** | 依赖以上三项未完成 |

---

## ✅ 已实现部分

### API 端点

```
POST https://www.expedia.com/graphql
```

### 两步请求流程

| 步骤 | OperationName | APQ Hash（完整值） |
|------|--------------|------------|
| 1 | `FlightsShoppingPwaFlightSearchFormLoaded` | `d0854dbabaf7f50353b9a08580d90aa60e783ca50e4161253bc955da91001cbb` |
| 2 | `FlightsSearchResultsLoadedQuery` | `ab6332b2d911a61d0002f1abdf1b63f3a987b4682f8d2f0321be0c8304fef6ff` |
| (可选) | `FlightsFlexibleSearchCheapestFare` | `abfc217dc846e91097583eef5463e2f8ae221dce3ac6afe1aa1d44e2c1f75561` |

第一步告知服务端搜索表单已加载（建立 `searchId`），第二步用同一 `searchId` 拉机票列表。两步必须使用同一个 `searchId`（UUID 格式，自行生成即可）。

### 必须携带的请求头

```http
Content-Type: application/json
client-info: flights-shopping-pwa,latest,external
device-user-agent-id: <DUAID Cookie 值>
x-page-id: page.Flight-Search-Roundtrip.Out,F,20
x-enable-apq: true     # 关键！缺少此头 APQ 退化为全量 query，服务端会拒绝
```

### 响应数据解析路径

```
data[0].data.flightsSearch.listingResult.listings[]
  → __typename == "FlightsStandardOffer"       # 过滤，只取航班卡
  → priceDisplay.rows[0].elements[0].price.text # 价格文本，如 "$857"
  → sponsoredAirline.airlineName                # 赞助航班名称（如有）
```

### 验证结果

| 路线 | 日期 | 状态 | 条数 | 价格范围 |
|------|------|------|------|---------|
| LAX → PEK | 2026-08-25 出发，09-02 返程 | ✅ HTTP 200 | 25 条 | $857 ~ $1,217 |

---

## ❌ 未实现部分

### 1. `_abck` Cookie 生成（Akamai Sensor）

**现状**：当前使用从浏览器复制的真实 `_abck`，值末尾 `~-1~-1~-1~-1~-1` 说明 JS 挑战未通过，但在有 `datadome` 的情况下服务端仍返回 200。

**未做的原因**：Akamai `sensor.js` 每周更新，混淆程度极高（业内公认最难逆向之一），逆向成本远超收益。

**后续逆向方向**：
- 工具：`ch_deobfuscate_auto` → `ch_static_analyze`
- 目标脚本：`https://www.expedia.com/dj/tags.js`（内含 sensor 逻辑）
- 关键函数：`bm_sz` 初始化时调用的 Canvas/WebGL 指纹采集函数

---

### 2. `datadome` Cookie 生成（DataDome SDK）

**现状**：`datadome` Cookie 是通过浏览器通过人机验证后才获得的，有效期约 **30 分钟**。过期后需要重新从浏览器复制。

**未做的原因**：DataDome SDK 同样高度混淆，且依赖真实设备指纹（屏幕分辨率、字体列表、Canvas 指纹、鼠标轨迹），纯静态还原难以通过。

**后续逆向方向**：
- 加载 DataDome SDK：`https://dd.expedia.com/tags.js`（需 `ch_fetch_url` 抓取）
- 关键接口：`POST https://api.datadome.co/` 返回 `datadome` Cookie
- 参数：`jsData` 字段（设备指纹 JSON，base64 编码）
- 工具：`ch_hook_crypto` + `ch_trace_crypto_param` 追踪 jsData 生成过程

---

### 3. 无浏览器全自动运行

**现状**：必须依赖真实浏览器的 Cookie，无法完全脱离浏览器运行。

**实现条件**：需要同时完成 `_abck` 和 `datadome` 的本地生成。

---

## 当前可用方案（半自动）

### Cookie 有效期内的使用流程

```
1. 打开 expedia.com/cn/Flights，通过人机验证（约 1 分钟）
2. F12 → Console → document.cookie → 复制
3. 填入 repro.py 的 BROWSER_COOKIE 变量
4. 运行 python repro.py（30 分钟内可反复调用）
```

### 运行脚本

```bash
pip install curl_cffi
python cases/expedia_flight/repro.py
```

---

## 风控分析（供后续逆向参考）

### Akamai Bot Manager 组件

| Cookie | 作用 | 过期/更新规则 |
|--------|------|--------------|
| `_abck` | JS 挑战签名（核心） | 页面加载时由 sensor.js 生成，值末尾计数器超限触发 429 |
| `bm_sz` | Session 请求频率配额 | 值内含 `~4601392~3294770`（第一个是配额总数，第二个是剩余） |
| `bm_sv` | 短期 Session 令牌 | 每次响应后服务端更新 |
| `datadome` | DataDome 人机验证凭证 | 验证通过后获得，约 30 分钟失效 |

### 429 触发条件

| 条件 | 说明 |
|------|------|
| TLS 指纹不匹配 | 标准 `requests` 库触发，`curl_cffi` 可绕过 |
| `bm_sz` 配额耗尽 | 同 IP 同 session 内高频请求（>50 次/分钟）触发 IP 级限速 |
| `datadome` 缺失/失效 | 必须通过浏览器人机验证后才能获取有效值 |
| `_abck` 完全无效 | 极端情况下（无 Cookie 直接请求）触发 |
