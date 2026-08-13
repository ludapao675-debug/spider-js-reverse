# 酷我音乐排行榜 API (musicList) 加密分析

## 1. 现状
- **URL**: `https://www.kuwo.cn/api/www/bang/bang/musicList`
- **加密参数**: 请求头中的 `Secret` 字段，以及 Query 中的 `reqId` 参数。
- **问题**: 在发包拦截之前，传统 `xhr.send` 的动态 Hook 无法直接观察到加密生成的内部运算。

## 2. 问题分析与定位
通过使用 `ch_listener_start` 和 `ch_listener_read` 截获发出的真实请求和当时环境的 Cookies：
- 观察到包含关键鉴权的 Cookie：`Hm_Iuvt_cdb524f42f23cer9b268564v7y735ewrq2324`。
- 在底层的 Webpack 代码（`assets/js_samples/ccdf548.js`）中搜索定位到了 `r.a.defaults.headers["Secret"] = f(o, v)` 这行代码。

## 3. 算法原理与闭环
1. **`reqId`**:
   - 依赖本地 `l()()` 方法生成，类似 UUID 的随机哈希标识符。
2. **`Secret`**:
   - 取决于 `v`（常量 `Hm_Iuvt_cdb524f42f23cer9b268564v7y735ewrq2324`）和 `o`（该同名 Cookie 的值）。
   - 函数内部包含 `d = Math.round(1e9 * Math.random()) % 1e8` 随机因子，这会造成每次生成的 `Secret` 都不一样。
   - 最后，这个随机数 `d` 会被补齐 8 位 16 进制字符串，并直接拼接在生成的 `Secret` 结尾。
   - **验证方案**: 我们从真实请求的 `Secret` 结尾截取出 8 字符的十六进制 `d`，代入该 JS 算法，并将网络抓包时的 Cookie 输入。通过本地复现计算得出的 `Secret` 与抓包取得的完整 `Secret` **100% 一致**，完美验证了输入输出闭环。

## 4. 验证样本
验证代码及样板可见同目录下的 `repro.js`。
