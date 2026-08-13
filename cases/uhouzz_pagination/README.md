# uhouzz (异乡好居) 房屋列表分页 API 逆向分析

## 1. 目标接口
- **URL**: `https://www.uhouzz.com/house4.6/api/houseSearch/listing`
- **Method**: POST
- **触发场景**: 在租房列表页点击分页按钮时触发（直接访问带分页参数的 URL 走的是 SSR，不触发此接口）。

## 2. 逆向成果
成功实现了分页请求的本地复现，包括：
1. 请求头签名的加密（`X-Client-Signature`）
2. 响应体数据的解密（`data` 字段）

### 2.1 加密算法
该网站对请求签名和响应数据均使用了 **AES-128-CBC** 加密算法。

- **Secret Key**: `1xPJA7iD2SrhkJnA`
- **IV Key**: `uhomescomleitian`
- **Padding**: PKCS7
- **编码**: Base64

### 2.2 请求头签名 (`X-Client-Signature`)
签名是对特定参数拼接后的字符串进行 AES-CBC 加密得到的。
拼接规则如下：
```python
raw_str = "app_id=63&device_id={device_id}&api_version=1&platform=pc&_time={timestamp}"
```
其中：
- `app_id`: 固定为 `63` (PC端)
- `device_id`: 客户端生成的 UUID，如 `562FDA61-5303-4D1F-B5DF-18F6EBC28977`
- `platform`: 固定为 `pc`
- `_time`: 当前 13 位毫秒时间戳

加密过程：
`X-Client-Signature` = `Base64(AES_CBC_Encrypt(raw_str, SecretKey, IVKey))`

请求时需要将这些字段同时放到 Headers 中（如 `X-Client-Appid`, `X-Client-Deviceid`, `X-Request-Timestamp`）。

### 2.3 响应体解密
接口返回的 JSON 结构为：
```json
{
  "error_code": 0,
  "message": "成功",
  "data": "1eR7RHmbAv0yawOESca+..."
}
```
`data` 字段是一段 Base64 编码的密文。
使用相同的 **Secret Key** 和 **IV Key** 进行 AES-CBC 解密，即可得到包含完整房屋列表 JSON 数据。

## 3. 本地复现
本地复现脚本位于 `repro.py`。
只需运行：
```bash
python repro.py
```
即可成功拉取并解密指定页数的房屋列表数据。

## 4. 分析方法总结
1. 监听网络请求：识别到直接访问分页 URL 为 SSR 渲染，而点击分页按钮会触发异步 API 请求。
2. 请求链分析：通过全局请求链路抓取到目标 API `/houseSearch/listing`，并注意到其含有复杂的 `X-Client-Signature` 以及加密的响应体。
3. 静态内存审计：避开无限单步调试，直接拉取 `assets/js_samples/il5XaGgK.js` 等核心 Chunk 文件，通过 Python 脚本进行正则搜索提取出加解密函数的源码。
4. 算法还原：分析提取出的 JS 源码（`getSignature` 和 `decrypt`），确认其为标准 `CryptoJS.AES` 加解密，无需执行 JS 即可使用纯 Python 闭环。
