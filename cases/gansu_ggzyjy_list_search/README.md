# 甘肃公共资源交易中心列表分页 API 逆向

## 1. 目标

- 页面：`https://sjfz.ggzyjy.gansu.gov.cn:19002/#/list-search`
- 接口：`POST https://sjfz.ggzyjy.gansu.gov.cn:19002/api/renren-api/ESProjectList/searchByPage`
- 触发：列表页分页 / 筛选查询（`page=1/2/...`，`pageSize`）

## 2. 结论摘要

| 项 | 结论 |
|----|------|
| URL `params=` | **不是**接口参数；仅 `pako.gzip + base64 + encodeURIComponent` 的路由状态 |
| 列表请求 | `encryptedPost`：body = `"04" + sm2.doEncrypt(JSON, pubkey, 1)` |
| 算法 | **SM2**（`sm-crypto`，cipherMode=`1` = C1C3C2） |
| 公钥（压缩） | `03702057B53C16031D786D9E06D839163F3DD5867E6E161292F61E1340FDF6DE24` |
| 响应 | **明文 JSON**（axios 拦截器不解密；`code/data.list/data.total`） |
| Cookie/Token | 公开列表 `noLogin`，可不带 token |
| 本地复现 | `repro.py`（Node `sm-crypto` 加密 + Python `requests`） |

## 3. 路由 params（与分页接口无关）

示例 URL：

```text
#/list-search?pop=true&params=H4sI...
```

解码：`decodeURIComponent` → base64 → gunzip →

```json
{"tradeType":"1","link":"ALL","platformCode":""}
```

仅用于前端初始化筛选态。

## 4. 分页请求协议

```text
POST /api/renren-api/ESProjectList/searchByPage
Content-Type: application/json;charset=UTF-8
X-Requested-With: XMLHttpRequest
Origin/Referer: https://sjfz.ggzyjy.gansu.gov.cn:19002

Body（原始字符串，不是再 JSON 包一层）:
04<SM2密文hex>
```

明文 params（与 `list-search-*.js` 中 `u.params` 一致）：

```json
{
  "platformCode": "",
  "noticeName": "",
  "tradeType": "1",
  "queryType": "1",
  "link": "ALL",
  "pageSize": 10,
  "page": 1,
  "important": "",
  "remote": ""
}
```

分页只改 `page` / `pageSize` 后重新 SM2 加密即可。

### 特殊交易类型分支

`tradeType` ∈ `{7,8,14}` 时**不走** `encryptedPost`，改为明文：

```text
GET /sunshinePruchase/getSunshinePruchaseInfo
```

参数字段变为 `pageNo/pageSize/projectCategory/...`。

## 5. 前端定位

| 位置 | 说明 |
|------|------|
| `assets/index-*.js` | `getEncrypted` / `encryptedPost` / `getGzip` |
| `assets/list-search-*.js` | `T()` 查询：`p.encryptedPost("/ESProjectList/searchByPage", u.params)` |
| `window.SITE_CONFIG.apiURL` | `.../api/renren-api` |

关键片段：

```javascript
getEncrypted: e => "04" + gn.sm2.doEncrypt(
  e,
  "03702057B53C16031D786D9E06D839163F3DD5867E6E161292F61E1340FDF6DE24",
  1
)
encryptedPost(e, t, o) {
  return pa({
    url: e,
    method: "post",
    headers: { "Content-Type": "application/json;charset=UTF-8", ...o },
    data: this.getEncrypted(JSON.stringify(t))
  })
}
```

另有前端内嵌 `doDecryptStr` 私钥（用于其它本地解密工具），**本列表响应未使用**。

## 6. 验证结果

| 样本 | 结果 |
|------|------|
| page=1, tradeType=1, link=ALL | `code=0`, `total=250`, `list.length=10` |
| page=2, 同条件 | `code=0`, 列表 id 与 page1 **无交集** |
| 负向：明文 JSON body | `code=500`, `msg=服务器内部异常` |

任务证据：`server/data/reverse_runs/task_20260728_020050_9b8920b5/`

## 7. 复现

```bash
cd cases/gansu_ggzyjy_list_search
npm install
python repro.py --page 1 --trade-type 1 --link ALL
python repro.py --page 2 --trade-type 1 --link ALL
```

## 8. 踩坑记录

| 误判 | 真实原因 | 识别信号 | 修复 |
|------|---------|---------|------|
| URL `params=H4sI` 是接口密文 | 只是路由 gzip 状态 | gunzip 后是短 JSON | 抓 `encryptedPost` 才是业务包 |
| CDP 启动后 tab 连不上 | 直开目标站超时/launcher exit | `urlopen timed out`、9222 无监听 | 先静态扒包 + HTTP 复现 |
| Content-Type=json 要把密文再 stringify | axios 对 string data 原样发送 | 明文 body 直接 500 | `requests.post(..., data=密文字节)` |
