# 查策网产业政策项目分页 API 逆向

## 1. 目标

- 页面：`https://www.chacewang.com/chanye/index#`
- 接口：`GET https://web.chace-ai.com/api/ccw/project/evaluation/getList/`
- 触发：列表页 ElementUI 分页点击（`page=1/2/...`）

## 2. 结论摘要

| 项 | 结论 |
|----|------|
| 请求签名 | **无**（仅普通 Query + Referer/Origin） |
| 响应加密 | `data` 字段为自定义包装 + **AES-CBC / PKCS7** |
| 前端入口 | `jsapp.*.js` 模块 `myDecrypt`（webpack id `2fb2`） |
| 本地复现 | `repro.py` 纯 Python，无需浏览器 |

## 3. 请求协议

```text
GET /api/ccw/project/evaluation/getList/
  ?page=1
  &size=20
  &industry=
  &area=RegisterArea_HNDQ_Guangdong_SZ
  &dept=
  &partition=
  &pe_name=
  &currentArea=RegisterArea_HNDQ_Guangdong_SZ
  &query_date=0
  &full_search=0
  &sort_type=0
```

关键 Header：

- `Accept: application/json, text/plain, */*`
- `Origin: https://www.chacewang.com`
- `Referer: https://www.chacewang.com/`

分页只改 `page` 即可；不需要 Cookie / Token / 请求签名。

## 4. 响应解密（`myDecrypt`）

响应形态：

```json
{"code": 200, "message": "成功", "data": "<Base64>"}
```

`Base64` 解码后的字符串结构：

```text
[0:10]   随机前缀 prefix10
[10:18]  固定标记 "ccwfp___"
[18:50]  mid32（参与密钥派生）
[50:]    十六进制密文
```

密钥派生：

```text
seed = prefix10 + mid32
h0 = md5_hex(seed)
持续: h_{n+1} = md5_hex(h_n + seed)，拼接直到长度 >= 48
derived = concat[:48]
key = derived[:32]   # Utf8 字符串，AES-256
iv  = derived[32:48] # Utf8 字符串，16 字节
```

解密：

```text
AES_CBC_Decrypt(HexDecode(cipher_hex), key, iv) -> UTF-8 JSON
```

明文通常是项目对象数组，字段含 `id/mid/pe_name/over_view/...`。

> 部分展示字段（如时间）前端另有字体映射混淆（`decrypt_` + 动态 woff），与列表分页密文解包无关；本案例只还原分页列表明文。

## 5. 验证样本

| 样本 | request_id | page | 结果 |
|------|------------|------|------|
| 活体1 | `20744.82` | 1 | `code=200`，解密得 list，首条含 `pe_name` |
| 活体2 | `20744.106` | 2 | `code=200`，解密得另一页 list |
| 负向 | 篡改 mid32 / 截断 hex | - | AES unpad 失败 |

## 6. 本地复现

```bash
# 默认第 1 页
python cases/chacewang_pagination/repro.py

# 指定页码
python cases/chacewang_pagination/repro.py --page 2
```

依赖：`requests`、`pycryptodome`。

## 7. 分析方法

1. Listener 抓到 `web.chace-ai.com/.../getList/?page=`，确认分页参数明文。
2. 响应 `data` Base64 解码出现 `ccwfp___` 标记。
3. 静态审计 `jsapp.*.js`，定位 `e.myDecrypt=u` 与 MD5 链式派生。
4. Python 还原后对 page=1/2 活体请求解密闭环。

## 8. 踩坑记录

- 误判 -> 以为需要请求签名；真实原因 -> 请求无签名，难点在响应解密。
- 识别信号 -> Header 极简 + `data` 长 Base64 + 解码含 `ccwfp___`。
- 修复方式 -> 按 `myDecrypt` 切片/派生/AES，不要当普通 Base64 JSON。
- 可复用规则 -> 查策网 `web.chace-ai.com` 同类接口优先搜 `myDecrypt` / `ccwfp___`。
