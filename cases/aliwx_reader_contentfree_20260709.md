# 案例：书旗网(aliwx) reader 章节内容请求逆向

## 基本信息

- 目标名称：aliwx.com.cn reader 章节内容接口 `contentfree/`
- 目标类型：签名型（实际为服务端预签名 URL，非客户端计算）
- 日期：2026-07-09
- 负责人：MCP 逆向（crypto-hunter-lite）

## 问题描述

- 现象：用户贴出 `GET .../pcapi/chapter/contentfree/?bookId=6813923&chapterId=674177&ut=1754876996&num=1&ver=1&aut=1754876998&sign=e39057b1f61224711e812c52214d3d70`，质疑 `sign` 为何不能客户端逆向。
- 失败表现：首次分析仅看 PAGEDATA 静态值就下“服务端签名不可逆”结论，未跑运行时证据，且漏看 `reader.js` 里 `sign` 出现 0 次这一关键事实。
- 复现步骤：`ch_cdp_start` 注入 hook → `ch_listener_start` → 读取 PAGEDATA → 触发章节加载 → 对比请求 URL 与 PAGEDATA 后缀 → 注入 crypto hook 验证无客户端加密。

## 证据

- 目标请求：
  ```
  GET https://c13.shuqireader.com/pcapi/chapter/contentfree/
      ?bookId=6813923&chapterId=674177&ut=1754876996&num=1&ver=1&aut=1754876998
      &sign=e39057b1f61224711e812c52214d3d70
  ```
- 关键参数：`sign`(32hex=MD5)，`ut`(每章固定)，`aut`(全局常量 1754876998)，`num=1`,`ver=1`。
- 相关源码：`reader.js` 的 `_getContByCid` → `d = freeContUrlPrefix + n.contUrlSuffix` → `$.ajax({url:t})`。`sign` 在 reader.js 中 **0 次出现**。
- 运行时变量：`window.readerObj.chapters[i].contUrlSuffix` 已含完整 `sign`；`window.PAGEDATA` 无 sign 计算。
- 网络记录：listener 捕获的真实请求 URL 与 PAGEDATA 的 `contUrlSuffix` **逐字符一致**（initiator=XHR.send，jQuery ajax 第 526 行，无中间变换）。

## 超级补环境

- 是否启用：否
- 判定原因：纯前端拼接 + fetch，无需补环境。

## 验证应对

- 验证类型：离线 replay + 算法解码验证
- 处理路由：直接复用 PAGEDATA 预签名 URL，无需破解 sign
- 是否需要人工接力：否

## 分析过程

- 类型判断：签名型，但 sign 不在客户端计算（静态分析 `sign:0` + 运行时对比）。
- 入口定位：`readerObj.chapters[i].contUrlSuffix` 即为带 sign 的完整后缀。
- 复现方法：replay 预签名 URL + `_decodeCont` 解码响应。

## 误判点

- 误判点 1：看到 `sign` 参数 + hook 捕获到 `sign=9bf8a190...` 就以为是内容签名。真相：那是 **AWSC/collina.js 反爬遥测 beacon**（`wpk-header=...&sign=9bf8a190...`），与内容 URL 无关。
- 误判点 2：认为 `ut` 是客户端动态时间戳。真相：`ut` 是 PAGEDATA 里**每章固定的预签名值**（674174→1472714703，674177→1754876996），`aut` 全局常量。
- 误判点 3：首次只静态看 PAGEDATA 就断言“不可逆”，未用 MCP 运行时对比证明无客户端变换。

## 真正原因

- 真正原因：content 的 `sign = MD5(明文 + 服务端密钥)` 由服务端在渲染页面时算好，直接埋进 PAGEDATA 每章的 `contUrlSuffix`；`reader.js` 仅做字符串拼接后发请求，**浏览器端不存在任何 sign 计算**。已用 MD5 多种明文拼接爆破验证：无盐值匹配，确认需服务端密钥。
- 识别信号：动态分析中 `sign` 在业务脚本 0 次出现；listener 请求 URL == PAGEDATA 后缀；MD5/AES/RSA/WebCrypto hook 对内容请求 0 命中。
- 修复方式：变更为“replay 预签名 URL”策略，不纠结破解 sign。

## 验证结果

- 生成位置：服务端渲染 PAGEDATA（每章 `contUrlSuffix`）。
- 本地复现方式：`scratch/aliwx_replay.py` —— 直接 GET `freeContUrlPrefix + contUrlSuffix`，对 `ChapterContent` 跑 `_decodeCont`（字母表 ROT 替换 + 手写 base64 + UTF-8）。
- 验证结果：`state:200`，解码出正确正文“蒹葭海再往东去有一片森林……”（2066 字），算法确认无误。

## 可复用规则

- 规则 1：业务脚本里 grep 目标参数出现 0 次 → 大概率服务端预埋或别的脚本算，先看 PAGEDATA/全局变量。
- 规则 2：hook 抓到的 `sign` 要先通过 `ch_cipher_search`/请求归属区分是业务请求还是反爬 SDK（AWSC/collina）的遥测埋点。
- 规则 3：CDN 返回 `x-swift-cachetime: 2592000`（30 天）说明预签名 URL 长期有效，优先 replay 而非破解。

## 回归说明

- 哪些点容易变：预签名 URL 可能过期（看 `x-swift-cachetime`）；`freeContUrlPrefix` 域名（c13.shuqireader.com）可能切换；付费章走 `reqEncryptType=1` base64 加密 ID 模式（末章已观察到）。
- 下次升级时先检查什么：重新读取 PAGEDATA 的 `contUrlSuffix` 是否仍含 `sign`；`_decodeCont` 算法是否更换。

## 踩坑记录

- 误判(服务端签名不可逆) → 真实原因(预签名 URL 直接复用) → 识别信号(listener URL==PAGEDATA后缀 + hook 0 命中) → 修复方式(replay+decode) → 可复用规则(见上)。
