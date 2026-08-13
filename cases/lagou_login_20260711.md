# 案例：拉勾网(passport.lagou.com)登录加密参数逆向与本地复现

- 日期：2026-07-11
- 目标：登录请求中的密码加密参数生成机制，本地离线复现
- 站点：`https://passport.lagou.com/login/login.html`
- 类型：商业招聘站登录（AES+RSA 混合加密）

## 工具链

crypto-hunter-lite MCP（stdio，后端 `http://127.0.0.1:27183`）：
- `ch_cdp_start` 启动 CDP 浏览器并注入请求捕获脚本（`panel/nhsa_req_capture.js` 复用为通用捕获）
- `ch_page_input` / `ch_page_click` 拟人化填表、点击登录
- `ch_page_run_js` 在页面执行 JS（构造加密样本、原生 Web Crypto 交叉验证）
- `ch_script_search` / `ch_scripts_list` 定位加密库与源码

## 关键发现

1. **滑块前置风控**：点击「登录」后弹出「请拖动滑块完成拼图」行为验证（极验/数美类），
   未过滑块则不会发出登录 POST。滑块 ticket 为独立风控机制，不在加密复现范围。
2. **加密库定位**：`@lagou/base-crypto@1.1.49/lib/main.js`（152KB，自研加密库）。
   密码加密函数 `q6`（即内部 `Rt`：`AES-CBC` 封装）通过 `r.d(e,{q6:()=>Rt})` 导出，
   但运行时 `window['lagou-base-crypto']` 为 UMD 空壳对象（真正逻辑在登录页按需 chunk）。
   算法无需运行时调用——从源码已完全掌握。
3. **RSA 公钥硬编码**：库内固定内置 RSA 公钥（见复现脚本 `PUB_PEM`），不随时间/用户变化。

## 加密协议（逆向结论）

| 项 | 算法 | 参数 |
|----|------|------|
| 密码加密 | AES-256-CBC | key=aesKey(随机32字符 UTF-8)；IV=`c558Gq0YQK2QUlMc`（固定）；PKCS7；Base64(CryptoJS) |
| aesKey 加密 | RSA-2048 PKCS1 v1.5 | 固定公钥；输出小写 hex（512 字符，type-2 随机填充） |
| 请求体加密(q6) | AES-256-CBC | 同 key/iv，对业务 JSON 字符串加密得 Base64，包进 `{"data":"<b64>"}` |

密钥生成：`aesKey` 从字母表 `A-Za-z0-9+/=` 随机取 32 字符。

## 本地复现

脚本：`assets/repro/lagou_login_repro.py`（依赖 `pycryptodome`）

```bash
# 交叉验证（固定 aesKey，应输出 hCtVJmxE5L//yutDdxRyHw==）
python assets/repro/lagou_login_repro.py --verify

# 完整复现（随机 aesKey，输出加密后的登录请求体）
python assets/repro/lagou_login_repro.py --account <账号> --password <密码>
```

## 验证证据

- 固定 `aesKey="AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPp"`，明文 `Test@123456`：
  - 本地 Python（pycryptodome AES-CBC+PKCS7）：`hCtVJmxE5L//yutDdxRyHw==`
  - 浏览器原生 Web Crypto（`crypto.subtle.encrypt` AES-CBC 自动 PKCS7）：`hCtVJmxE5L//yutDdxRyHw==`
  - **两者完全一致** => 算法参数（key/iv/模式/填充/编码）精确还原拉勾实现。

## 待补充

- 完整登录请求字段名（滑块 ticket、额外风控参数）需真实登录样本；滑块为独立风控。
- 服务端对 `rsaEncryptData` 的接收字段名（header 或 body）需结合真实请求确认。
- 证据文件：`assets/js_samples/lagou/base-crypto_dec.js`（解密后的加密库源码）、`assets/js_samples/lagou/login_aio.js`。
