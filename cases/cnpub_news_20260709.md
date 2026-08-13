# cnpub.com.cn API 加密逆向

- 日期：2026-07-09
- 类型：AES-128-CBC + PKCS7 padding（请求/响应双向加密），无 WAF / 无令牌校验 / 无需验证码
- 站点：https://cnpub.com.cn/information.html#/search （中国新闻出版广电网 · 信息检索 SPA）

## 目标请求（已确认）

```
POST https://cnpub.com.cn/prod-api/api/index/newsList
Content-Type: application/json;charset=UTF-8
Body: <AES-CBC 加密后的 hex 密文>
```

- `newsList` 返回行业动态列表，`searchDataCate` 需要登录态。
- 请求体和响应体均为 AES-CBC 加密的 hex 字符串。

## 加密方案

| 参数 | 值 |
|------|-----|
| 算法 | AES-128-CBC |
| Key | `16weizifuchuan16` (16 字节) |
| IV | `1suibianshurude6` (16 字节) |
| Padding | PKCS7 |
| 编码 | hex |

## 加密位置

- webpack 模块 `994a`（CryptoJS 封装），位于 `chunk-common.5c047c0f.js`
- 解密函数: `g["b"] = (e, key, iv) => AES.decrypt(hex.parse(e), key, {iv, mode: CBC, padding: Pkcs7}) → utf8.stringify`
- 加密函数: `g["d"] = (e, key, iv) => AES.encrypt(utf8.parse(JSON.stringify(e)), key, {iv, mode: CBC, padding: Pkcs7}) → hex`

## 离线复现

```python
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import json

KEY = b"16weizifuchuan16"
IV  = b"1suibianshurude6"

def encrypt(data: dict) -> str:
    plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
    cipher = AES.new(KEY, AES.MODE_CBC, iv=IV)
    return cipher.encrypt(pad(plain, AES.block_size)).hex()

def decrypt(hex_data: str) -> dict:
    raw = bytes.fromhex(hex_data)
    cipher = AES.new(KEY, AES.MODE_CBC, iv=IV)
    plain = unpad(cipher.decrypt(raw), AES.block_size)
    return json.loads(plain.decode("utf-8"))
```

## 验证结果

- newsList 第 1 页 5 条 → `code:200`，`total:3231`，返回真实新闻标题/作者/平台
- 往返加解密测试 → encrypt→decrypt 完全一致
- searchDataCate → 预期 `code:401`（需登录 token）

## 证据

- 复现脚本：`assets/repro/cnpub_com_cn.py`
- JS 源码来源：webpack module `994a`（`chunk-common.5c047c0f.js` 偏移 341409）

## 踩坑记录

1. **误判**：直接 GET 请求 notice API 返回 hex 密文，以为是二进制编码。
   **真实原因**：所有 `/prod-api/api/` 下的接口都走 AES-CBC 双向加密。
   **识别信号**：响应为 128 字符 hex（64 字节，刚好是 4 个 AES 块），字符集为 0-9a-f。
   **修复方式**：从 webpack chunk 中搜索 `encrypt`/`decrypt`/AES 关键词定位加密模块。

2. **误判**：newsList POST 带 JSON body → `"No content to map"`
   **真实原因**：请求体也需要 AES-CBC 加密成 hex 密文后才能发送。
   **识别信号**：服务端报"no content to map"而非正常的 JSON 解析错误，说明服务端先解密再解析。
   **修复方式**：将 JSON body 先 encrypt → 发送 hex 密文字符串。

3. **误判**：以为需要携带 token/cookie/session。
   **真实原因**：newsList 接口无需登录，searchDataCate 才需要。
   **识别信号**：newsList 不带 cookie 即可正常返回数据，searchDataCate 返回 401。
   **修复方式**：区分公开接口和需登录接口。

## 可复用规则

- hex 密文响应（128 字符全员 hex）→ 优先怀疑 AES-CBC + hex 编码
- "no content to map" + 正常 JSON body → 请求体可能也需要加密
- webpack chunk 搜索 `AES`/`encrypt`/`decrypt` + `CBC`/`Pkcs7` 快速定位加密模块

## 回归说明

- 易变点：Key/IV 可能定期轮换（当前为明文硬编码，易于替换）
- 下次升级先检查：① chunk 文件名是否变化；② module ID 是否变化；③ Key/IV 是否更换
