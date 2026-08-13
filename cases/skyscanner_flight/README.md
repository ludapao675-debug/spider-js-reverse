# 天巡 (Skyscanner) 机票搜索 API 逆向与协议复现案例

> **版本**：v1.0 | **日期**：2026-08-13 | **目标**：`https://www.tianxun.com/`

---

## 一、 现状 - 问题 - 方案 - 原理

### 1. 现状（分析结论）
* **目标接口**：`https://www.tianxun.com/g/radar/api/v2/web-unified-search/`
* **交互模式**：`POST` 初始化搜索获取 `sessionId` 游标 $\rightarrow$ `GET` 带 Token 轮询拉取实时低价机票。
* **复现效果**：成功做到 100% 协议级离线复现，抓取洛杉矶-北京、上海-东京等多航线各合作航司与代理平台的低价报价。

---

### 2. 接口列表与参数结构

#### 接口 1: 搜索初始化 (`POST /g/radar/api/v2/web-unified-search/`)

* **Request Body**：
```json
{
  "adults": 1,
  "cabinClass": "ECONOMY",
  "childAges": [],
  "legs": [
    {
      "legOrigin": {"@type": "entity", "entityId": "27536211"},
      "legDestination": {"@type": "entity", "entityId": "128668664"},
      "dates": {"@type": "date", "year": "2026", "month": "08", "day": "21"}
    },
    {
      "legOrigin": {"@type": "entity", "entityId": "128668664"},
      "legDestination": {"@type": "entity", "entityId": "27536211"},
      "dates": {"@type": "date", "year": "2026", "month": "08", "day": "28"}
    }
  ]
}
```

* **核心 Header**：
  * `X-Skyscanner-ChannelId: website`
  * `X-Skyscanner-ViewId`: 动态 UUID
  * `X-Skyscanner-TrustedFunnelId`: 动态 UUID
  * `X-Skyscanner-Traveller-Context`: 动态 UUID

#### 接口 2: 轮询拉取机票列表 (`GET /g/radar/api/v2/web-unified-search/<sessionId>`)

* **Response Context**：
```json
{
  "context": {
    "status": "complete",
    "sessionId": "KLUv_SDKbQQAQskfH7Drd0m-ln9J..."
  },
  "itineraries": {
    "results": [ ... ],
    "agents": [ ... ]
  }
}
```

---

### 3. EntityId 城市实体映射库

| 城市 / 机场 | IATA 代码 | Skyscanner 内部 EntityID |
| :--- | :--- | :--- |
| **洛杉矶** | `LAX` / `LAXA` | `27536211` |
| **北京** | `PEK` / `BJS` | `128668664` |
| **上海** | `SHA` / `PVG` | `27539656` |
| **东京** | `TYO` / `HND` / `NRT` | `27545090` |
| **香港** | `HKG` / `HKGA` | `27539446` |

---

## 二、 复现脚本使用方法

运行 `cases/skyscanner_flight/repro.py`：

```bash
python cases/skyscanner_flight/repro.py
```
