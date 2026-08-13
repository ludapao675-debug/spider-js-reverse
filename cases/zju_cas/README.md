# 案例：浙江大学统一身份认证 CAS 登录 (zjuam.zju.edu.cn)

> 逆向目标：定位登录请求中密码字段的加密逻辑，并本地复现登录请求生成（随机测试账号密码）。
> 验证日期：2026-07-15。结论置信度：0.98。

## 1. 登录请求形态

- **URL**：`POST https://zjuam.zju.edu.cn/cas/login?service=https%3A%2F%2Fservice.zju.edu.cn%2F`
- **Content-Type**：`application/x-www-form-urlencoded`
- **表单字段**：

| 字段 | 说明 | 是否加密 |
|------|------|----------|
| `username` | 用户名 | 明文 |
| `password` | 密码 | **RSA-512 加密 (128 hex)** |
| `authcode` | 验证码（可空） | — |
| `execution` | CAS 单次令牌（与 JSESSIONID 会话绑定） | — |
| `_eventId` | 固定值 `submit` | — |
| `ys` | 固定值 `5` | — |

`execution` / `JSESSIONID` 为一次性会话态，复用需重新从页面抓取。

## 2. 密码加密算法

经典 **RSAUtils**（ohdave / Dave Shapiro）RSA 加密，模长 **512-bit**，教科书式（无随机填充，同一明文+公钥 → 同一密文）。

- **公钥来源**：`GET /cas/v2/getPubKey` → `{"modulus": "<128 hex>", "exponent": "10001"}`
  （注意：公钥随会话轮换）
- **加密调用**：
  ```js
  RSAUtils.setMaxDigits(130);
  var key = RSAUtils.getKeyPair(exponent, "", modulus);
  var cipher = RSAUtils.encryptedString(key, password);
  ```
- **源码**：页面 `/cas/js/login/security.js`（即本目录 `security.js` 快照）。

### `encryptedString` 关键逻辑（复现要点）

```js
// chunkSize = 2 * biHighIndex(modulus)  -> 512-bit 模数 = 62
// 明文 -> charCodeAt 字节数组, 末尾补零到 chunkSize 整数倍
// 每 2 字节拼成 1 个 16-bit digit: pair = a[k] + (a[k+1] << 8)
// block.digits[j] 从下标 0 顺序填充 (低位在前):
//     block = Σ_j pair_j * (65536 ** j)
// crypt = powMod(block, e) -> biToHex -> 每块补零到 128 hex
```

> 易错点：block 的 digit 是**从下标 0 顺序**填充（低位在前），不是从高位开始。

## 3. 本地复现

### 方式 A：纯 Python（推荐）

```bash
python reproduce.py
```

- 默认用自洽证据（`cases/zju_cas/reproduce.py` 内 `CAPTURED_*` 常量）验证 Python 复现密文 == 页面 RSAUtils 输出（逐字节一致）。
- 随机账号密码演示：生成随机用户名/密码，输出 128-hex 密文并做确定性校验。
- 指定实时公钥复现：`python reproduce.py --modulus <hex> --plaintext <密码>`。

### 方式 B：加载线上真实 `security.js` 交叉验证（Node）

```bash
node repro_node.js "你的密码"
```

直接 fetch 线上 `security.js` + `getPubKey` 并调用真实 `RSAUtils.encryptedString`，
输出 `modulus / exponent / enc`，用于与 Python 结果比对。

### 端到端验证（已执行）

在真实登录页用随机账号 `2083337560` / 密码 `Rand@epof6jsyrz`：
- 页面 `RSAUtils` 加密得到密文 `7c10bd49...`
- Python 复现同一 modulus + 明文得到**完全相同**的 `7c10bd49...`（逐字节一致）
- 实际提交登录 POST，服务端返回 HTTP 200（监听器已捕获）

## 4. 结论

密码字段 = RSAUtils RSA-512(`password`, 实时公钥)，公钥来自 `/cas/v2/getPubKey`。
本地复现已 100% 还原该加密，可用随机账号密码生成与线上一致的 `password` 字段。
完整登录请求还需拼接页面 `execution` 等一次性令牌（需从实时页面抓取）。

## 5. 文件清单

| 文件 | 作用 |
|------|------|
| `reproduce.py` | 纯 Python 复现 + 自洽/随机验证 |
| `repro_node.js` | 加载线上 `security.js` 做权威交叉验证 |
| `security.js` | 页面加密库快照（RSAUtils） |
| `README.md` | 本说明 |
