# zbcg.sznsyy.cn 通知公告(homeNotice)列表翻页复现

- 站点：深圳市南山区人民医院招采系统 `https://zbcg.sznsyy.cn/homeNotice`
- 日期：2026-07-09
- 类型：请求参数 + 响应数据双重加密（AES-ECB + RSA），无 WAF / 无行为验证
- 来源：项目内已有旧资料 `reverse_practice2/zbcg_sznsyy/`（liyf 2022 方案），**当前站点仍有效，直接复用**

## 目标请求

```
POST https://zbcg.sznsyy.cn/sz/purchaser/public/frontPageAnnouncementList
Content-Type: application/json;charset=UTF-8
```

请求体（加密前明文，JSON）：
```json
{
  "noticeName": null,
  "pageNum": 1,
  "pageSize": 10,
  "tenderCategory": "6",
  "noticeType": null,
  "tenderClass": null
}
```
翻页只改 `pageNum`。

## 参数生成位置 / 算法

来自旧 `demo.js`（`get_params` / `decrypt`）：

1. 客户端随机生成 16 位 key（62 字符集：`0-9A-Za-z`）
2. **请求加密**：`content = AES_ECB_Pkcs7(key, JSON(payload))`；`aesKey = RSA_encrypt(pub_p1, key)`
   - 发送 `{content, aesKey}`
3. **响应解密**：服务端返回 `{content, aesKey}`
   - `key = RSA_decrypt(priv_f1, aesKey)`；`data = AES_ECB_Pkcs7_decrypt(key, content)`

关键点：**前端 JS 里硬编码了 RSA 私钥 `f1`**（设计缺陷），所以无需服务端配合即可完整离线复现。

密钥（硬编码于站点 JS，已收录到复现脚本）：
- 公钥 `p1`（X.509，`MIGfMA0G...AQAB`）：加密请求用的随机 key
- 私钥 `f1`（PKCS#1，`MIICdwIB...`）：解密响应里的 aesKey

## 运行时证据

探针（2026-07-09）实测：
- 当前接口仍返回 `{aesKey, content}` 结构，AES+RSA 解密成功
- `total = 20978`，`pageSize = 10`，每页 `rows` 10 条
- 样本首条：`水动力辅助吸脂系统（一次性无菌吸脂治疗系统）（临采）变更公告`，`publishTime = 2026-07-09T09:25:59`

## 复现脚本

- `scratch/zbcg_home_notice.py`：Python 完整复现（pycryptodome 的 AES-ECB + RSA PKCS1_v1_5）
- `scratch/zbcg_sample.json`：3 页样本（30 条）
- 运行：`python scratch/zbcg_home_notice.py <页数>`

为什么用 Python 而非旧 demo.js：
- 旧 `demo.js` 依赖 `crypto-js` + `jsencrypt` + Node，本环境用 Python `pycryptodome` 即可等价实现，更可控、无需 Node 运行时

## 验证结果

- 3 页全部 `200`，翻页有效，`total` 一致（20978），无重复、无频率拦截（已加 1s 间隔 + Session 保持）
- 字段：`bulletinName`(标题)、`publishTime`、`noticeType`、`middleId`、`tenderProjectCode`、`tenderCompanyName`

## 失败坑点（固定格式）

1. 误判：站点 2026 已升级加密/WAF，需重新逆向
   → 真实原因：前端仍用 2022 旧方案且 RSA 私钥硬编码，可直接离线复现
   → 识别信号：旧 `demo.js` 含明文 `f1` 私钥与 `p1` 公钥，`get_params/decrypt` 完整
   → 修复方式：一步探针复用旧算法即通
   → 可复用规则：**遇到已有旧资料先探针验证，不盲目重分析**（呼应 `docs/reverse_lessons.md`）

2. 误判：RSA 公钥/私钥字符串可直接 `load`
   → 真实原因：从 JS 提取的是裸 base64，缺 PEM 头尾
   → 识别信号：`ValueError: No PEM start marker`
   → 修复方式：补 `-----BEGIN PUBLIC KEY-----` / `-----BEGIN RSA PRIVATE KEY-----`
   → 可复用规则：**从 JS 提取的密钥匙串需补 PEM 包装**

3. 误判：用 `rsa` 库即可加解密
   → 真实原因：`rsa` 库 `load_pkcs1` 解析该 PKCS#1 私钥报 `Sequence` 错（密钥结构/版本差异）
   → 识别信号：`TypeError: int() ... not 'Sequence'`
   → 修复方式：改用 `pycryptodome` 的 `RSA.import_key` + `PKCS1_v1_5`（与 jsencrypt 同 padding）
   → 可复用规则：**RSA 加解密优先用 pycryptodome 的 PKCS1_v1_5，规避 jsencrypt/rsa 库差异**

4. 误判：必须在浏览器跑 `demo.js`（crypto-js + jsencrypt）
   → 真实原因：算法是纯 AES+RSA，无环境指纹/行为校验，可用 Python 完整复现
   → 识别信号：算法不含运行时环境依赖
   → 修复方式：Python `pycryptodome` 重写
   → 可复用规则：**纯 AES+RSA 类优先 Python 离线复现**

5. 误判：翻页第 2 页失败 = 算法算错
   → 真实原因：批量请求加间隔更稳（呼应 landchina 频率坑）
   → 识别信号：首页成功、后续页偶发失败
   → 修复方式：`Session` 会话保持 + 1s 间隔
   → 可复用规则：**批量翻页先加间隔/会话保持**

## 延伸（本次未做，旧 demo 已覆盖）

- **详情接口**：`/sz/purchaser/public/getBulletinDetailInfo`，参数 `epcos`（同样 AES+RSA 加密），返回公告详情密文
- **文件下载**：`/sz/file/download`，`Aeskey` 头 + `epcos` 参数，返回 PDF
- 本次仅交付"列表翻页拿数据"，详情与下载按需再扩展

## 工具链验证（2026-07-09 实测，本轮重点）

本轮**不采信旧 demo 结论**，直接用 crypto-hunter 浏览器工具链对当前站点做真实探查，重点测工具功能。

### 真实流量捕获（绕过 listener 故障）
- `ch_page_navigate` 导航到 homeNotice ✅
- `ch_listener_start` 故障（返回空 `error`），无法启动监听 ❌
- 改用 `ch_page_run_js` 注入 fetch/XHR 拦截器 + 点击翻页（副作用生效，`clicked:true`），再用 `ch_page_get_storage` 读回 localStorage 捕获 ✅
- **真实请求**（当前站点 2026-07-09）：`POST /sz/purchaser/public/frontPageAnnouncementList`，body `{"content":"...","aesKey":"..."}`
- **真实响应**：`{"aesKey":"...","content":"..."}`
- 结论：当前加密结构与 2022 旧方案**完全一致（AES-ECB + RSA，{content,aesKey}/{aesKey,content}），站点未升级**

### 工具功能测试矩阵（修复后 2026-07-09）
| 工具 | 状态 | 说明 |
|------|------|------|
| ch_cdp_status / ch_health / ch_browser_list_tabs | ✅ | 正常 |
| ch_page_navigate | ✅ | 正常 |
| ch_page_run_js | ✅ | 已修复：`result` 正常回传 IIFE/async IIFE 返回值（42 / 7），表达式读取正常；无 return 的注入语句返回 None 不报错 |
| ch_page_get_storage | ✅ | 正常，成功读回捕获 |
| ch_listener_start | ✅ | 已修复：`task_id` 为空时自动生成，server 端正常注册 5 个 Network 回调并抓到真实 POST 请求 |
| ch_cipher_search | ✅ | 连带恢复：listener 恢复后其数据源可用 |

### 工具缺陷（已于 2026-07-09 定位并修复，端到端验证通过）
1. **`ch_listener_start` 返回 `{"ok":false,"error":"error"}`**
   - 根因：`mcp_service.py` 的 `ch_listener_start` 在 `task_id` 为空时直接返回字面量 `"error"`，未自动生成。server 端 `listener_start` 逻辑本身完整（注册回调/注入 hook/返回 listener_id 均正常）。
   - 修复：`server/mcp_service.py` 第 3310 行起，`task_id` 为空时改为 `task_id = "task_" + uuid4().hex[:12]` 自动生成。
   - 验证：独立脚本调用修复后 `BrowserRegistry.listener_start`，返回 `ok=True`、`network_enabled=True`、5 回调注册、`hook_injected=True`；触发真实 fetch 后 `listener_read` 捕获到 1 个 `POST`。
2. **`page_run_js` 返回值始终为 `null`**
   - 根因：`browser_runtime.py` 的 `page_run_js` auto-detect 把含分号的 IIFE 判为 `as_expr=False`（语句模式）。DrissionPage 在 `as_expr=False` 下把 IIFE 再包一层 `function(){(function(){...})()}`，内层 IIFE 无 return → 返回 `undefined`。另：CDP 路径（有 wait 条件时）返回未提取的 CDP 原始结构，与 DrissionPage 路径值结构不一致。
   - 修复：`server/browser_runtime.py` ① auto-detect 增加 IIFE/函数/类/return 开头 → `as_expr=True`（走 `Runtime.evaluate(awaitPromise=True)` 才能取值）；② 两处 CDP 路径返回值用 `_extract_runtime_value` 提取，与 DrissionPage 路径结构一致。
   - 验证：DrissionPage 直连确认 `as_expr=False`→`None`、`as_expr=True`→`42/7/'hello'`（async IIFE 也 await 返回 7）；独立脚本调用修复后 `page_run_js`，IIFE→42、async IIFE→7、表达式读取→123，全部正确。
3. **`cipher_search` 依赖 listener 数据** —— 随 listener 恢复而自然恢复，无需单独改。

### 可复用规则
- listener 不可用（已修复）时，仍可用 `page_run_js` 注入 fetch/XHR 拦截器把证据写入 `localStorage`，再用 `ch_page_get_storage` 回读作为兜底。
- 纯 `AES+RSA` 类加密优先用 Python `pycryptodome` 离线复现，避免依赖浏览器；JS 提取的裸 base64 RSA 密钥需补 PEM 头尾。
- 测工具功能时，先 `ch_health` 确认健康，再逐项验证，避免把工具故障误判为站点防护。
- 修复 `page_run_js`/`listener` 等后端工具后，可用独立脚本 `import` 修复后的 `browser_runtime` 模块、连接已运行的 Chrome CDP 端口做端到端验证，无需重启 server。

## 合规提示

仅供学习交流，勿用于商业/非法用途。
