# a_bogus 完整打包逻辑与双 SM3 拼装机制（最终完结版）

通过对运行日志 (`vm_instr_dump_v4.json`) 的深入交叉比对、针对多个连续样本的 99B 负载 Diff 分析、6-bit 拆分验证，以及 `sdenv` 实测与 DrissionPage 拦截复现，我们成功完成了对抖音 `a_bogus` 算法全链路的逆向分析与自动化产线搭建。

---

## 1. 核心架构拆解

### (1) 99 字节纯环境负载 (Payload)
- 业务代码首先拼装一个 98~99 字节的数组。**此数组不包含 Query/Body 的 SM3 哈希**。
- 绝大多数字节（>90 字节）为恒定指纹（屏幕分辨率、UA、Magic Header `01 0E 9B` 等）。
- 仅少数字节随时间波动（时间戳低位、递增计数器、随机盐）。

### (2) 环境信息膨胀层 (func 148)
- 99 字节 Payload 传入 VM 函数 `148`。
- `func 148` 为类似 **Base64 (3B 变 4B)** 的位运算膨胀拆分器，将 98~99 字节扩展为 **130 字节**。

### (3) 双 SM3 提取与动态密钥流 (Dynamic Keystream)
- 业务层对 `Query` 和 `Body` 分别计算 32 字节的 **SM3 哈希**（及 `dhzx` 相关的 32B 盐哈希）。
- 32B 哈希被送入密钥推导函数（KDF），衍生出长度为 **130 字节** 的动态密钥流 (Dynamic Keystream)。

### (4) 异或混淆装配 (XOR)
- `130B Final Payload = 148_Output (环境时间特征) XOR Dynamic_Keystream (Query/Body 导出流)`
- 将动态时间戳/指纹与参数签名强融合，实现防篡改与环境双校验。

### (5) 附加控制头与最终编码 (func 130)
- 异或后的 130B 拼接 12B Header（版本及密钥对齐控制），形成 142 字节数组。
- 送入自定义 Base64 编码器 (`func 130`，使用混淆字母表 `s2`)。
- $142 \times \frac{4}{3} \approx 189.33$，加上 `==` 补齐，生成约 **192 字符的 final `a_bogus`**。

---

## 2. 数据流拓扑图

```text
[SM3(query) + SM3(body) + Salt] ---> [ 外层 KDF ] ---> Dynamic Keystream (130B)
                                                                 |
[环境/指纹/计数器/时间戳] (99B) ---> [ func 148 膨胀 ] ---> Unpacked Payload (130B)
                                                                 |
                                                          [ XOR 按位异或 ]
                                                                 |
                                                         130B 融合后数据流
                                                                 |
                          [ 拼接 12B Header ] ---> 142B 控制数组 ---> [ func 130 自定义 Base64 ] ---> a_bogus
```

---

## 3. 突破性发现：内外双修隔离混淆

我们在 VM 的 2000+ 完整指令日志中检索 SM3 哈希或其 32B 数组，匹配数为 0；同时也排除了 WASM 与 SubtleCrypto。

这是因为 `bdms.js` 采用了**内外双修**机制：
- **VM 内部**：负责环境 Payload 膨胀 (`func 148`) 和 Base64 编码 (`func 130`)。
- **VM 外部（纯 JS 外壳）**：在被控制流平坦化保护的外层 JS 中计算 SM3 与 KDF，并在外层完成 XOR 异或。
- 外层将异或后的 130B 结果重新送回 VM 内部执行 Base64。

---

## 4. 行业通用攻破方案与实测补环境验证

通过针对技术社区（GitHub、CSDN、博客园及逆向论坛）的行业解法调查，业界对于 `a_bogus` 的攻破手段主要分为以下三种主流路线：

| 方案路线 | 核心原理 | 优点 | 实测验证 / 局限性 |
| :--- | :--- | :--- | :--- |
| **1. 纯 Node.js 补环境 (sdenv)** | 补齐 `process`/`global`/`toString`，补丁 VM `D()` 按 ops 指纹暴露 **func 150**，直接调用生成 `a_bogus` | 无需浏览器 GUI | **已打通业务 a_bogus**：`repro/sdenv_local_sign.py` 多样本 `ok=True`，长度 ~188–192，query 变化则签名变化 |
| **2. 纯算法纯本地还原** | 剥离 JSVMP，纯 Python 复现 99B→148→XOR→Base64 | 最快、零 JS | 未完成；KDF/打散仍在 VM/外壳 |
| **3. 活体 RPC 拦截** | DrissionPage 拦截真实 XHR/fetch 上的 `a_bogus` | 最稳、顺带 `msToken`/`verifyFp` | 需常驻浏览器 |

### 补环境核心突破实证 (`sdenv`)

**坑点（初始化）**：
1. **`process`**：`globals` 注入浏览器态 `process`（`platform: browser`），避免 sdenv-extend 主动抛错。
2. **`Function.prototype.toString` 只读**：eval bdms 前改为 `writable: true`，并容忍 `defineProperty` TypeError。
3. **`global is not defined`**：func 150 字节码会读 `global`；需 `window.global=window` + 间接 `eval('var global = window')`。

**业务 a_bogus（真正本地签，2026-07-24 实证）**：
- 脚本：`server/data/reverse_runs/task_20260723_061837_889ab753/repro/sdenv_local_sign.py`
- 方法：补丁 `D()`，命中指纹后挂 `window.__dy_sign150`；调用  
  `__dy_sign150(1,0,8, queryString, '', UA, 6241, 6383, '1.0.1.19-alpha.01')`
- 结果：返回 **~192 字符** `a_bogus` 字符串（与活体插桩 150 leave 形态一致）
- 注意：`verify_sdenv_signature_complete.py` 截获的是 SDK **遥测 strData**，**不是** 业务 `a_bogus`，勿混淆。
- `func 107` 是 XHR 钩子，**不能**当独立 `encrypt(url)` 调用。

```python
from sdenv_local_sign import sign_a_bogus
r = sign_a_bogus(
    "https://www.douyin.com/aweme/v1/web/tab/feed/?aid=6383&device_platform=webapp&count=1",
    # ms_token="活体截获的会话 msToken",  # 优先传入；否则默认本地随机占位
)
assert r["ok"] and len(r["a_bogus"]) > 80 and r["has_msToken"]
print(r["a_bogus"], r["msToken"], r["ms_via"], r["signed_url"])
# signed_url 已同时挂上 a_bogus + msToken
```

> `msToken`：会话级，mssdk `/web/r/token` 在纯 sdenv 未闭环。解析优先级（生产脚本）：sdenv append 截获 > `me[24]`/`xmst` > 参数注入 > URL > Cookie > 缓存文件 > `local_random`。真校验请注入浏览器 `localStorage.xmst`。

---

## 5. 生产级 RPC 服务使用说明 (`rpc_server.py`)

服务代码位于：`server/data/reverse_runs/task_20260723_061837_889ab753/repro/rpc_server.py`

### 启动命令
```bash
python server/data/reverse_runs/task_20260723_061837_889ab753/repro/rpc_server.py
```

### 调用示例 (Python)
```python
import requests

resp = requests.post("http://127.0.0.1:8089/sign", json={
    "url": "https://www.douyin.com/aweme/v1/web/general/search/single/?query=TEST_QUERY&aid=6383"
})

data = resp.json()
print("a_bogus:", data["a_bogus"])
print("Full Signed URL:", data["full_url"])
```
---

## 6. 实战踩坑经验与 `sdenv` 沙箱调用指南

在 `a_bogus` 的逆向脱壳与补环境过程中，我们踩过了多个关于 Node.js 沙箱环境模拟、V8 引擎差异、DrissionPage 交互以及接口风控机制的坑点。以下为详细记录与解决方案：

### (1) `sdenv` 沙箱环境补充坑点

#### 坑点 1：`sdenv` 补环境瞬间抛出 `ReferenceError: process is not defined` 导致 JS 执行中断
- **现象**：在 `sdenv` 中加载运行 `bdms.js` 时，控制台瞬间抛出 `ReferenceError: process is not defined`。
- **根因**：`sdenv-extend` 内部使用 `Proxy` 代理全局 `window`/`globalThis` 对象。当 Webpack / 混淆代码中检查 `process` 存在性（如 `typeof process !== 'undefined'`）时，Proxy 的 `get` 拦截器由于未在 `target` 中找到该属性，便按沙箱设计主动抛出 `ReferenceError`，强行中断了后续 JS 的初始化流程。
- **解决方案**：在调用 `sdenv` 时，通过 `globals` 字典显式注入一个模拟的浏览器端 `process` 对象：
  ```python
  input_data = {
      "globals": {
          "process": {"env": {}, "version": "", "platform": "browser", "versions": {}, "browser": True}
      }
  }
  ```

#### 坑点 2：`core-js` Polyfill 触发 `TypeError: Cannot assign to read only property 'toString'`
- **现象**：`process` 解决后，运行报 `TypeError: Cannot assign to read only property 'toString' of function ...`。
- **根因**：`bdms.js` 内部打包了 `core-js` polyfill，尝试重写内置函数的 `toString` 属性。Chrome 的 V8 允许对此属性重新赋值，但 Node.js 下 `Function.prototype.toString` 的 Descriptor 默认 `writable: false` 且只读。
- **解决方案**：在 `bdms.js` 执行前注入 `compat_patch`，利用 `Object.defineProperty` 将 `toString` 的 `writable` 属性强制置为 `true`：
  ```javascript
  try {
      var desc = Object.getOwnPropertyDescriptor(Function.prototype, 'toString');
      if (desc && !desc.writable) {
          Object.defineProperty(Function.prototype, 'toString', {
              writable: true, configurable: true, value: desc.value
          });
      }
  } catch(e) {}
  ```

#### 坑点 3：`sdenv_runner.js` 传入 `eval_expression` 被静默忽略
- **现象**：在 Python 侧向 `sdenv` 传入 `eval_expression`，但返回的 JSON 中 `eval_result` 始终为 `None`。
- **根因**：查阅 `server/sdenv_runner.js` 源码发现，`runner` 的 `main()` 函数中只对 `input.js` 执行了 `vm.runInContext(input.js)`，并未实现对 `input.eval_expression` 的读取和评估逻辑。
- **解决方案**：不要使用 `eval_expression` 字段，直接将后置检查/测试代码（如全局变量快照比对、调用 `window.bdms.init()`）拼接到 `input.js` 的末尾一并传入。

#### 坑点 4：`try/catch` 包裹导致 `sdenv` 误报 `ok: true`（假成功）
- **现象**：给 `bdms.js` 套上 `try/catch` 捕获异常后，`sdenv` 返回 `ok: true`，但 `window.bdms` 实际并未挂载成功。
- **根因**：`sdenv_runner` 以 `vm.runInContext` 是否在顶层抛出未捕获异常来判定 `ok` 状态；`try/catch` 吞掉异常后导致 `ok` 被误标记为 `true`。
- **解决方案**：判断补环境是否成功时，**禁止仅依赖 `ok: true` 标记**，必须检查具体的业务挂载点（如 `window.bdms` 对象或 `CRAWLER_FOUND` 日志）。

---

### (2) DrissionPage 与活体 API 调用坑点

#### 坑点 5：DrissionPage `page.cookies` API 接口兼容性异常
- **现象**：调用 `page.cookies.as_dict()` 或 `page.cookies(as_dict=True)` 触发 `AttributeError` 或 `TypeError`。
- **根因**：DrissionPage 在不同大版本中 `cookies()` 方法的返回值和入参规则存在差异。
- **解决方案**：使用通用的返回类型兼容性判断：
  ```python
  cookies_val = page.cookies()
  if isinstance(cookies_val, dict):
      browser_cookies = cookies_val
  elif isinstance(cookies_val, (list, tuple)):
      browser_cookies = {item.get('name'): item.get('value') for item in cookies_val if isinstance(item, dict)}
  else:
      browser_cookies = {}
  ```

#### 坑点 6：搜索接口活体请求返回 `status_code: 2483, 请先登录`
- **现象**：携带生成的 `a_bogus` 请求 `/aweme/v1/web/general/search/single/` 接口时返回 `status_code: 2483`。
- **根因**：抖音搜索等敏感 Web API 对匿名未登录状态进行了二次风控拦截（与签名算法本身无关），必须绑定有效账号的登录 Session/Cookie。
- **解决方案**：验证纯签名算法有效性时，使用无需登录态的公开接口（如推荐流 `/aweme/v1/web/tab/feed/`），返回 `status_code: 0` 及 `aweme_list` 视频数据证明加签成功。

---

## 7. 协议复现延伸：评论爬取（2026-07-24）

本地签 + Cookie/`xmst` 缓存后，已可纯协议拉取评论列表（关浏览器可跑）。

| 文档 | 路径 |
|------|------|
| 心得 / 踩坑 / 用法全集 | [`cases/douyin_comment_crawl/README.md`](../douyin_comment_crawl/README.md) |
| 爬取 CLI 操作说明 | `.../repro/README_crawl_comments.md` |
| 爬取脚本 | `.../repro/crawl_video_comments.py` |

补充踩坑（相对上文）：

| 坑 | 信号 | 修法 |
|----|------|------|
| XHR stub 同步 `onreadystatechange` 死循环 | sdenv 永不返回 | 回调改 `setTimeout(0)` |
| `sdenv-main` 冷启动 ~45s | 签超时误判失败 | 超时 ≥150s；接受首页慢 |
| Cookie 含中文 | `latin-1` UnicodeEncodeError | 组头时过滤非 latin-1 |
| 缓存时间 `+08:00` | Python3.10 `fromisoformat` 异常→local_random | 统一 UTC 存储 |
| 评论接口误以为必须 X-Bogus | 活体常不带 | 以 listener 为准：Cookie+a_bogus+msToken |

实证：`--cache-only` 拉 350 条评论，`status_code=0`，全程无 ERROR。
