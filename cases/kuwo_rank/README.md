# 酷我音乐排行榜 API (musicList) 加密分析

## 1. 现状
- **URL**: `https://www.kuwo.cn/api/www/bang/bang/musicList`
- **加密参数**: 请求头中的 `Secret` 字段，以及 Query 中的 `reqId` 参数。
- **问题**: 在发包拦截之前，传统 `xhr.send` 的动态 Hook 无法直接观察到加密生成的内部运算。

## 2. 问题分析与定位
抓包可见请求头 `Secret` 与 Cookie `Hm_Iuvt_cdb524f42f23cer9b268564v7y735ewrq2324`。
Webpack 中定位到 `headers["Secret"] = f(o, v)`：`o` 为该 Cookie 值，`v` 为同名常量。

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

## 5. 闭环验证（需运行时自动获取抓包样本）
仓库不携带真实 Cookie/Secret（敏感数据）。运行方式：

```bash
# 无参数：演示加密算法输出
node repro.js

# 闭环验证：传入真实抓包样本（Cookie 与 Secret 必须来自同一次请求）
node repro.js <真实Cookie> <真实Secret>
```

**自动获取步骤**：
1. 浏览器打开酷我音乐排行榜页（https://www.kuwo.cn/rankList）
2. DevTools → Network 过滤 `musicList` 请求，点击查看 Headers
3. 复制请求头 `Cookie` 中的 `Hm_Iuvt_cdb524f42f23cer9b268564v7y735ewrq2324` 值 → 作为第 1 个参数
4. 复制请求头 `Secret` 值 → 作为第 2 个参数
5. 运行 `node repro.js <Cookie> <Secret>`，输出 ✅ 即闭环验证通过
