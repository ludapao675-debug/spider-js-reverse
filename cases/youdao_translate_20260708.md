# 有道翻译 (fanyi.youdao.com) 签名逆向 — 本地复现

## 基本信息

- 目标名称：有道翻译网页版 `fanyi.youdao.com`
- 目标类型：Web API / MD5 签名 / AES-128-CBC 解密
- 日期：2026-07-08
- 负责人：crypto-hunter-lite
- 源码文件：`reverse_practice2/youdao_translate.py`
- JS 来源：`shared.ydstatic.com/dict/translation-website/1.0.0/js/app.bdbada07.js`

## 问题描述

- 现象：有道翻译网页版每次翻译请求都携带 `sign` 参数，响应为 AES 加密密文
- 核心接口：
  - `GET dict.youdao.com/webtranslate/key` → 获取动态 secretKey
  - `POST dict.youdao.com/webtranslate` → 发送翻译请求，返回 AES 密文
- 复现链路：获取 secretKey → MD5 签名 → POST 请求 → AES-128-CBC 解密

## 证据

- 目标请求：`POST https://dict.youdao.com/webtranslate` (application/x-www-form-urlencoded)
- 关键参数：`sign`, `mysticTime`, `keyid`, `i`(待翻译文本)
- 签名公式：`MD5("client=fanyideskweb&mysticTime={ts}&product=webfanyi&key={secretKey}")`
- 解密方案：AES-128-CBC, key = MD5(固定常量), iv = MD5(固定常量), URL-safe base64 → Decrypt → unpad
- JS 源码定位：`app.bdbada07.js` module 34917, functions `I()`, `C()`, `N()`, `U()`, `x()`

## 分析过程

- 类型判断：MD5 签名 + AES 对称解密，属于中等难度规则型加密
- 入口定位：`app.bdbada07.js` module 34917, `function I(e,t)` → 签名生成, `function U(e,t,o)` → 解密
- 关键 JS 代码：
  ```javascript
  // 签名: function I (module 34917)
  I = (e, t) => w(`client=${g}&mysticTime=${e}&product=${h}&key=${t}`)
  // w = MD5(str).toString()
  
  // 翻译请求: function N (module 34917)
  N = (e, t) => POST("dict.youdao.com/webtranslate", {...e, ...C(t)})
  
  // 解密: function U (module 34917)  
  U = (e, t, o) => {
    const key = Buffer.alloc(16, MD5(t))
    const iv = Buffer.alloc(16, MD5(o))
    const cipher = createDecipheriv("aes-128-cbc", key, iv)
    return cipher.update(e, "base64", "utf-8") + cipher.final("utf-8")
  }
  ```
- 复现方法：`reverse_practice2/youdao_translate.py`

## 踩坑记录（本次最核心的部分）

### 坑 0: 两套 API 共存导致方向错误

| 项目 | 新版 `/translate/enhance` | 旧版 `/webtranslate` |
|------|--------------------------|---------------------|
| 签名复杂度 | genParamV3（20+ 字段排序 MD5） | 固定 3 字段 MD5 |
| Python 调用结果 | 始终 500 | **成功** |
| 失败原因 | 疑似 TLS 指纹/客户端检测 | — |
| 浏览器是否在用 | 是 | **也是**（`function N` 路径） |

**教训**：JS 源码里同时存在多个 API 版本时，先全部列出来，分别测试。不要在第一个遇到的接口上死磕。

**识别信号**：同一个 JS 文件中有 `function N`（旧）和 `function Y`（新），两者参数格式完全不同。旧版 sign 只有 3 个字段，新版有 20+。

---

### 坑 1: 服务端返回"随机假数据"而非错误码

| 项目 | 详情 |
|------|------|
| **误判** | 「解密输出是合法 JSON 且有中文，说明签名正确、解密正确」 |
| **真正原因** | POST body 缺少 `keyid: 'webfanyi'`，服务端不报错，返回随机数据库记录 |
| **为什么坑** | 合法 JSON + 中文字符 → 营造了"一切正常"的假象，让人反复检查签名和密钥 |

**识别信号**：
- 同一文本（如 "hello world"）多次请求返回完全不同的翻译结果
- `src` 字段显示正确输入，但 `tgt` 完全是随机内容
- 响应结构正确（`translateResult` 中有 `src`/`tgt`），但内容错乱

**修复方式**：检查所有固定/必需参数是否完整。对比浏览器实际发送的 POST body 列表，逐一核对。

**可复用规则**：
> 🔴 **规则 1 — 反爬假数据检测**：解密输出为合法 JSON 但内容随机时，暂停怀疑签名/密钥，先对比浏览器实际发送参数，逐字段核对缺失项。很多时候是**请求参数不完整**而非**加解密逻辑错误**。

---

### 坑 2: URL-safe base64 当作普通 base64 解码

| 项目 | 详情 |
|------|------|
| **误判** | 「padding 错误 → 密钥不对，需要换 key/iv 方案」 |
| **真正原因** | 服务端返回的是 `urlsafe_b64decode` 格式（`-_` 替代 `+/`），用普通 `b64decode` 会失败 |
| **为什么坑** | padding 错误的直觉反应是「密钥错了」，但其实只是 base64 变体 |

**识别信号**：解密时出现 `Incorrect padding` 错误
**修复方式**：`base64.urlsafe_b64decode(text)` 替代 `base64.b64decode(text)`
**可复用规则**：
> 🔴 **规则 2 — Base64 变体优先排查**：看到密文含 `_` 或 `-` 字符时，先试 URL-safe base64。这是前后端通信中最常见的变体，比密钥错误概率高得多。

---

### 坑 3: 手动 PKCS7 unpadding 不准

| 项目 | 详情 |
|------|------|
| **误判** | 手动 `decrypted[:-padding_len]` 可能因边界情况出错 |
| **真正原因** | pycryptodome 有 `Crypto.Util.Padding.unpad` 标准方法 |
| **修复方式** | 统一使用 `unpad(cipher.decrypt(data), AES.block_size)` |

**可复用规则**：
> 🔴 **规则 3 — 用标准 unpadding**：永远用 `Crypto.Util.Padding.unpad` 而非手动 slice。手动 unpadding 在 buffer 边界或中文编码时可能截断字节。

---

### 坑 4: `appVersion` 值不同直接影响结果

| 项目 | 详情 |
|------|------|
| **JS 源码** | `appVersion: "12.0.0"` |
| **实际可用** | `appVersion: "1.0.0"` |
| **错误表现** | 用 `12.0.0` 导致所有请求返回随机假数据 |
| **修复方式** | 参考社区验证过的值 `1.0.0` |

**可复用规则**：
> 🔴 **规则 4 — JS 里的常量不一定是服务端接受的值**：JS 源码中的版本号可能是前端渲染用的，服务端不一定按此校验。优先以浏览器实际发送的请求参数为准，其次参考社区已验证的值。

---

### 坑 5: `signSecretKey` 同时出现在签名和参数中造成混淆

| 项目 | 详情 |
|------|------|
| **混淆点** | 新版接口的 `signSecretKey` 既是请求参数，又是签名密钥 |
| **后果** | 签名时会同时包含字段 `signSecretKey=xxx` 和 `key=xxx`（相同值），看起来像重复 |

**可复用规则**：
> 🔴 **规则 5 — 签名密钥作为请求字段是常见模式**：`signSecretKey`、`token` 这类字段可能既出现在签名计算中，也作为独立参数发送，这是正常设计，不是 bug。

---

## 真正原因总结

| # | 现象 | 真正原因 | 修复 |
|---|------|---------|------|
| 0 | /translate/enhance 始终 500 | TLS 指纹检测（推测） | 换用 /webtranslate 旧版 |
| 1 | 解密出随机假翻译 | POST 缺少 `keyid:'webfanyi'` | 补全字段 |
| 2 | AES padding 错误 | URL-safe base64 | `urlsafe_b64decode` |
| 3 | 解密内容误判 | 手动 unpadding | `unpad()` |
| 4 | code=50 错误 | `appVersion` 值不对 | 改为 `1.0.0` |

## 验证结果

- 生成位置：`app.bdbada07.js` module 34917 `function I()`
- 本地复现：`reverse_practice2/youdao_translate.py`
- 验证命令：`python youdou_translate.py`
- 验证结果：
  ```
  [en→zh-CHS] 'hello world' → '你好世界'        ✅
  [en→zh-CHS] 'good morning' → '早上好'          ✅
  [zh-CHS→en] '你好世界' → 'HELLO WORLD'         ✅
  ```

## 可复用规则（速查清单）

| # | 规则 | 触发条件 |
|---|------|---------|
| 1 | 反爬假数据：合法JSON但内容随机 → 先核对POST字段完整性 | `translateResult` 有 `src` 但 `tgt` 错乱 |
| 2 | base64 变体：密文含 `_`/`-` → `urlsafe_b64decode` | `Incorrect padding` |
| 3 | 标准 unpadding：用 `unpad()` 而非手动 slice | 解密后末尾字节异常 |
| 4 | JS常量 ≠ 服务端常量：以浏览器实际请求为准 | 服务端返回异常数据 |
| 5 | 签名密钥可同时作为请求字段 | 看到 `key=xxx` 和 `secretKey=xxx` 同值 |

## 回归说明

- **容易变化的点**：
  - `keyid` 值（当前 `webfanyi-key-getter-2025`，后缀年份可能递增）
  - `KEY_GETTER_SECRET` 固定密钥（当前 `yU5nT5dK3eZ1pI4j`）
  - AES 固定常量（当前 `ydsecret://query/key/...` 和 `ydsecret://query/iv/...`）
- **下次升级时先检查**：
  1. 抓 JS 文件中的 `keyid` 和 `KEY_GETTER_SECRET`
  2. 确认接口地址是否变 (`webtranslate` vs 新路径)
  3. 确认 AES 常量是否更新 (`ydsecret://query/...`)
  4. 先用浏览器发一次请求，抓完整 POST body 参数列表
