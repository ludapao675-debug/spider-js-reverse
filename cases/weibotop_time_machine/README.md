# weibotop.cn 热搜时光机 API 协议

**样本**: `https://www.weibotop.cn/`（微博热搜历史查询）
**状态**: 核心加密协议 100% 还原并本地复现（AES 加解密 + topicId 编码）

## 架构

Next.js 14 App Router + RSC。热搜榜为 SSR 内联，AI 解读/情绪/榜单接口走 `/api/*`，全部经**统一加密通道**。

## 加密协议（前端模块 7374 封装 / 14624 解密）

### 1. 响应解密

```json
{"encrypted": true, "data": "<base64 密文>", "timestamp": 1786549840928}
```

```
明文 = AES-256-CBC-PKCS7 解密(key, iv, 密文) → UTF8 JSON
key = aa6218e56ddc05e908ec0842ae36fb8746b38cd6b7dc140b8df6826ca00b81d8  # 64hex=32B
iv  = fc3c868a2ffa7d1d45bccc0a4b4f4cca                                     # 32hex=16B
```

- 密文为 CryptoJS `CipherParams.toString()` 输出（**标准 base64**，非 URL-safe）
- key/iv 由 `CryptoJS.enc.Hex.parse()` 从 hex 字符串解析

### 2. 请求参数加密（`_e` 参数）

```
_e = AES-256-CBC-PKCS7.encrypt(JSON.stringify(params)).toString()  # base64
URL = "https://www.weibotop.cn/api/xxx" + "?_e=" + _e
```

- 无参数接口（`/api/ai/hotspot`、`/api/sentiment/thermometer`）**裸 GET 即可**
- 有参数接口（`/api/hotlist?limit=50`、`/api/ai/brief`）必须走 `_e`

### 3. 词条 id → topicId 编码（模块 44047）

```js
function T(id) {                      // 编码
  let i = (1518025885 ^ id) >>> 0;    // XOR 0x5A7F55DD
  let a = new Uint8Array([i>>24&255, i>>16&255, i>>8&255, 255&i]);
  return btoa(String.fromCharCode(...a)).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
}
function x(str) {                     // 解码
  let b = atob(str.replace(/-/g,"+").replace(/_/g,"/")), a = new Uint8Array(b.length);
  for (let i=0;i<b.length;i++) a[i]=b.charCodeAt(i);
  if (4 !== a.length) return null;
  return (1518025885 ^ new DataView(a.buffer).getUint32(0,!1)) >>> 0;
}
```

验证样本：`id=834724 → topicId=WneAOQ`（与浏览器抓包捕获的 `_e` 密文解密结果完全一致）

### 4. 鉴权

- `wt_client` cookie 由**服务端 Set-Cookie 下发**（HttpOnly，JWT 风格 `{purpose:"first-party-client-v1",id,iat,exp}.签名`），前端不参与生成
- 本地裸请求无需构造，`session.get(首页)` 自动带上即可
- 接口封装 `Xc`（模块 7374）：`localStorage.auth_token` 存在时非 admin 接口自动带 `Authorization: Bearer <token>`

### 5. 历史快照

`POST /api/history-token` 另有独立人机验证门禁，与 AES 协议无关。本案例不覆盖。

## 已验证接口

| 接口 | 参数 | 说明 |
|------|------|------|
| `/api/hotlist` | `limit` | 实时热搜榜（id/name/hotindex/rank/sessionCount） |
| `/api/ranking/rising` | `limit, timeid?` | 上升最快（rankChange/previousRank/isNew） |
| `/api/ranking/new` | `limit, hours, timeid?` | 新上榜（starttime 首次上榜时间） |
| `/api/ai/hotspot` | - | 今日热点 AI 解读（theme/analysis/trendingTopics） |
| `/api/ai/brief` | `topicId` | 单条词条 AI 简报 |
| `/api/sentiment/thermometer` | - | 情绪温度计（temperature/emotionDistribution/keywords） |

## 复现脚本

```
python repro.py hotspot
python repro.py thermometer
python repro.py hotlist
python repro.py ranking --type rising|new
python repro.py brief --id 834724
```

验证结果：
- `hotspot`：主题/趋势/值得关注全字段解密成功
- `thermometer`：36° 中性主导、情绪分布、关键词（结婚×3/出轨×2）解密成功
- `hotlist`：rank1「朱镕基同志逝世」id=834724 topicId=WneAOQ 热度124万
- `ranking/rising`：rank1「初代网红晚晚开始卖衣服」升6名，`_e` 加密闭环 ✅
- `ranking/new`：rank1「美联储9月加息概率再降」首次上榜，`_e` 加密闭环 ✅
- `brief`：请求协议与前端一致（topicId 编码匹配浏览器抓包），"无效词条"=词条库无该词条 AI 简报（数据时效，非协议问题）

## 踩坑记录

- **PowerShell 转义**：`-c` 内嵌 Python 代码含中文引号易失败，长逻辑用临时 `.py` 文件执行
- **`_e` URL 编码**：前端 `URLSearchParams` 会自动转义 `+/=`，requests 需传原始 `_e`（未编码），服务端可接受
- **topicId 时效**：同一 id 的 brief 可能因词条库过期返回"无效词条"，属服务端数据层
