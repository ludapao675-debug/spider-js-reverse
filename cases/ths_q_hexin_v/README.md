# 同花顺行情中心 hexin-v（Cookie v）逆向

## 基本信息

- 目标名称：同花顺行情中心 `q.10jqka.com.cn` 股票列表接口
- 目标类型：动态 Cookie（hexin-v，Cookie 名 `v`）+ JS 挑战
- 日期：2026-08-13
- 任务 ID：`task_20260813_151634_e932b9c0`

## 问题描述

- 现象：股票列表页 `https://q.10jqka.com.cn/index/index/board/all/field/zdf/order/desc/page/{N}/ajax/1/` 服务端直连返回 **401**，响应体是 chameleon 挑战页（加载 `s.thsi.cn/js/chameleon/chameleon.1.7.min.*.js` 后 JS 写 Cookie 并 `location.href` 自跳转）。
- 失败表现：无 `v` Cookie 且缓存 MISS 时一律 401；高频请求后升级为 200 软挑战（重定向 `upass.10jqka.com.cn/login`）。
- 复现步骤：`Invoke-WebRequest` 带 UA 无 Cookie 请求任意 `?probe=<随机>` 穿透缓存的列表 URL。

## 证据

- 目标请求：`GET https://q.10jqka.com.cn/index/index/board/all/field/zdf/order/desc/page/1/ajax/1/`（listener `lst_d39f8d4b50774db9`，cipher_search 命中 `request_headers.cookie` 中的 `v`）
- 关键参数：Cookie `v`（64 字符，域 `.10jqka.com.cn`，2050 年过期，非 HttpOnly；样本值已脱敏，由 `run_sandbox.js` 本地生成）
- 相关源码：`chameleon.1.7.min.js`（26,759 字节，本目录存有原件与 `chameleon.readable.js` 常量回代版）
- 运行时变量：`TOKEN_SERVER_TIME`（401 挑战页内联的服务端秒级时间戳）
- 网络记录：401 挑战页 `Set-Cookie: vvvv=1`；响应头含 `X-Cache`（squid CDN，`max-age=60`）

## 算法结构（核心结论）

编码链：**43 字节 buffer → strhash 低 8 位校验和 → XOR 流 → 自定义 base64**

1. buffer（`Un`，18 槽定宽，实测总宽 43 字节）：

| 偏移 | 宽度 | 字段 | 沙箱实测 |
|------|------|------|----------|
| 0-3 | 4 | 会话随机 ID（`Gn.random()`） | `305e725e` |
| 4-7 | 4 | 创建时 serverTime（秒） | `6a7ddb29` |
| 8-11 | 4 | 时间相关字段 2 | `6a7de487` |
| 12-15 | 4 | 最近 serverTime | `668f3821` |
| 16-18 | 3 | 指纹：ver/feature/platform | `010a00` |
| 19-36 | 18 | 行为计数（鼠标/键盘/点击，无交互=0） | 全 0 |
| 37-39 | 3 | 更新计数 | `000000` |
| 40-41 | 2 | 保留 | `0000` |
| 42 | 1 | 尾标志 | `03` |

2. 校验和 `d(n)`：对原始字节数组做 `strhash`（`a=(a<<5)-a+byte`，32 位回绕）取低 8 位，包头为 `[0x03, checksum]`。
3. XOR 流 `f()`：`a[i]=n[i] ^ (u & 0xff)`，然后 `u = ~(u * 0x83)`（32 位回绕），初始 `u = checksum`。
4. 自定义 base64 `g()`：字母表 `A-Za-z0-9-_`，3 字节 → 4 字符，无 padding。

## 超级补环境

- 是否启用：否（未走 sdenv_auto_reproduce，改用 Node `vm` 隔离沙箱直接执行原脚本）
- 判定原因：chameleon 为自包含 IIFE，DOM 依赖面小（document.cookie/navigator/createElement/setInterval），stub 成本低
- 触发信号：无
- 补环境建议：见 `run_sandbox.js` 的 stub 清单（document/navigator/location/localStorage/setInterval 全 no-op；探针插入点在源码最后的 `}()` 之前，与 `qn` 同作用域）

## 验证应对

- 验证类型：JS Cookie 挑战（非验证码），可全自动
- 处理路由：沙箱执行原脚本 → `qn.update()` 取 token → 携带 Cookie 重放
- 是否需要人工接力：否
- 识别信号：401 + body 含 `chameleon.*.js` + `window.location.href` 自跳转
- 证据包摘要：`validate.ps1` 输出 sample1 200/17958B、sandbox_v 200/17771B、负向（无 v）401

## 分析过程

- 类型判断：动态 Cookie 型（行为指纹 + 时间戳打包）
- 入口定位：cipher_search 命中 listener 请求 Cookie → 401 挑战页锁定生成脚本 chameleon
- 环境补丁：`decode_strings.js` 提取 4 个常量数组 + 4 个异或解码器（Xn/Hn/Kn/Vn）全量常量回代得 `chameleon.readable.js`
- 复现方法：`run_sandbox.js`（Node vm 完整执行原脚本，探针调 `qn.update()`），**不手工拼字节**

## 误判点

- 误判点 1：以为裸请求 200 代表无防护 → 实为命中 squid CDN 缓存（`X-Cache`/`Age`/`max-age=60`），`?probe=随机` 穿透后才暴露 401
- 误判点 2：按 readable 源码静态推导 buffer 宽度（54 字节）→ 实测 payload 43 字节；可读版的 `parseInt(常量)` 回代不完整，宽度必须以真实密文解码 + 沙箱 buffer 探针为准
- 误判点 3：手工拼 payload 的 `gen_v.js` 被 401 → 字段布局与线上不符；改用沙箱执行原脚本后 200

## 真正原因

- 真正原因：gate 校验 Cookie `v` 的结构与内容（时间戳字段需为合理值），格式合法即放行；行为计数可为 0
- 识别信号：沙箱原脚本生成的 60 字符 v 直接 200；手工拼的 60 字符 v 被 401
- 修复方式：放弃手工布局，沙箱执行原脚本取 `qn.update()` 输出

## 验证结果

- 生成位置：chameleon 内层 IIFE 的 `qn.update()`（`E.toBuffer()` → `Qn.encode`）
- 本地复现方式：`node run_sandbox.js` → `v_sandbox.txt`（每次运行随机 ID/时间戳都不同）
- 验证结果（2026-08-13 23:2x）：

| 样本 | 请求 | 结果 |
|------|------|------|
| 真实 v + cache-bust | page1 | 200 / 17771B |
| 沙箱 v #1 + cache-bust | page1 | 200 / 17771B |
| 沙箱 v #2 + cache-bust | page5 | 200 / 17958B |
| 无 v（负向） | page7 | 401 挑战页 |
| 高频探测后（含真实 v） | page6/8/9 | 200 软挑战（upass 重定向，IP 级限流） |

## 可复用规则

- 规则 1：同花顺系站点（10jqka/thsi）遇到 401 + `chameleon.*.js` 挑战，直接沙箱执行原脚本调 `qn.update()`，不要手工还原字节布局（版本间宽度会变）
- 规则 2：CDN 缓存会掩盖反爬——验证 gate 必须带随机 query 穿透缓存，并检查 `X-Cache`/`Age`
- 规则 3：`ch_fetch_url`/`requests` 服务端直连是判定"有无加密参数"的最快对照实验（有 Cookie vs 无 Cookie、有 UA vs 无 UA 矩阵）
- 规则 4：高频 cache-bust 探测会触发 IP 级软挑战（200 + upass 重定向），控制频率或换 IP

## 解码工具用法（真实 hexin-v 运行时自动获取）

`decode_v.js` 仓库中不携带真实 Cookie，需传入浏览器中实际生成的 hexin-v 值：

```bash
# 无参数：输出使用说明
node decode_v.js

# 传参解码：输出 payload 布局字段与校验和验证
node decode_v.js <hexin-v Cookie 值>
```

**自动获取步骤**：
1. 浏览器打开同花顺行情页（https://q.10jqka.com.cn），触发一次列表请求（401 挑战通过后）
2. DevTools → Application → Cookies → `q.10jqka.com.cn`
3. 复制名为 `hexin-v`（或 `v`）的 Cookie 值，作为命令行参数传入
4. 输出 `重算校验和: N ✔ 匹配` 且 payload 长度符合预期即解码成功

## 回归说明

- 哪些点容易变：chameleon 版本号（挑战页引用的 `chameleon.1.7.min.<时间戳>.js` 会滚动更新）、buffer 宽度布局、XOR 乘数（当前 0x83）、base64 字母表
- 下次升级时先检查什么：401 挑战页的脚本 URL 与 `TOKEN_SERVER_TIME`；用 `decode_v.js` 解新 Cookie 核对 payload 长度是否仍为 43

## 踩坑记录

1. 误判：裸请求 200 = 无防护 → 真实：CDN 缓存命中 → 信号：`X-Cache: MISS/HIT` + `Age` → 修复：随机 query 穿透 → 规则：先穿透缓存再下结论
2. 误判：readable 源码宽度可直接用 → 真实：常量回代不完整导致 54≠43 → 信号：真实密文 base64 解码后 payload 长度 → 修复：沙箱 buffer 探针取一手字节 → 规则：静态推导必须用运行时锚点校正
3. 误判：手工拼 payload 可过 gate → 真实：401 → 信号：同样长度同样编码链仍被拒 → 修复：沙箱执行原脚本 → 规则：自包含混淆脚本优先整体执行而非手工复刻
