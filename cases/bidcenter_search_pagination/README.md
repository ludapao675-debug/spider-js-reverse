# 采招网（bidcenter.com.cn）搜索分页请求本地复现

> 逆向目标：翻页时的网络请求 + 加密响应本地解密复现
> 工具链：crypto-hunter-lite MCP（attach 模式接管用户已开 Chrome）+ 定位 + 抓包 + 静态审计
> 日期：2026-08-02

## 一、目标接口（定位结论）

- **主接口**：`POST https://interface.bidcenter.com.cn/search/GetSearchProHandler.ashx`
- **翻页机制**：layui 分页组件（`a.layui-laypage-next`，`data-page=N`），点击触发 Ajax，**非 URL 跳转**
- **请求体**（form-urlencoded，无签名参数）：
  ```
  from=6137&guid=<guid>&location=6138&token=&next_token=&keywords=<词>&mod=0&page=<N>
  ```
  - `token` / `next_token` 恒为空 → **翻页请求本身无签名/加密**
  - `guid` 来自首次访问 Cookie 的 `bidguid`
  - `from`/`location` 为地区编码（6137=全国/省份，6138=对应城市）

## 二、响应解密算法（核心逆向点）

响应体为 Base64 密文，前端用 CryptoJS 解密。源码 `searchv16.js`：

- **算法**：AES-128-CBC
- **key**（CryptoJS WordArray，line 49）：`words=[863652730, 2036741733, 1164342596, 1782662963]`，大端拆 16 字节
- **iv**（line 50）：`words=[1719227713, 1314533489, 1397643880, 1749959510]`，大端拆 16 字节
- **padding**：ZeroPadding
- **输出**：解密后 UTF-8 字符串 → `JSON.parse`

⚠️ **字节序坑**：CryptoJS `WordArray.words` 每个 int 是 32 位**大端**整数，转字节必须用 `struct.pack(">I", w)`，小端（`<I`）会解出乱码。

## 三、复现脚本

`repro.py`（依赖 `requests` + `pycryptodome`）：

```bash
E:\aicode\.venv\Scripts\python.exe repro.py
```

- `fetch_page(keywords, page, guid, cookies=None)`：发请求 + 解密
- `parse_list` / `extract_items`：提取 `pageSearchJson` 内 `zhaobiao/daili/zhongbiao/hangye` 明细
- 登录态：把浏览器 Cookie（含 `biduid` 等）传入 `cookies=` 参数拿明细列表

## 四、验证结果

| 项 | 结果 |
|---|---|
| 请求层（A 层） | ✅ 直接 POST 返回 200 + 密文 |
| 解密层（B 层） | ✅ AES-128-CBC 解出合法 JSON |
| 分页统计 | ✅ `recordcount=800, pagecount=20, pagesize=40` |
| 明细列表 | ⚠️ 未登录态仅返回聚合统计（`msg=请登录/注册后操作`，`retbs=201`）；登录后传 Cookie 可拿明细 |

## 五、风控提示

- 页面加载了阿里滑块验证码（`g.alicdn.com/captcha-frontend/FeiLin`），`challenge_suspected=true`
- 高频翻页可能触发验证；`guid` 需从真实访问 Cookie 获取
- 本项目逆向的是**请求协议 + 响应解密**，登录墙属业务逻辑，非加密/签名阻挡

## 六、证据来源

- 监听器 `lst_a95b549c53cf40a9` 捕获 `1896.556`（主分页请求，完整 POST body + 响应密文）
- `ch_fetch_url` 抓 `searchv16.js` line 49/50/1766-1776 解密函数
- 真实密文样本见 `captured_cipher.txt`
