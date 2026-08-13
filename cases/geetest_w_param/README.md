# geetest 极验 3.0 w 参数逆向评估报告

**来源**: B 站登录验证码（`passport.bilibili.com/login`）
**状态**: 混淆结构已分析、逆向路径已规划；w 生成算法**未完成**（第三方深度混淆，工程量评估如下）

## 验证码链路（已确认）

```
点击登录 → B 站风控接口下发 {gt, challenge}
        → initGeetest() 加载 geetest.6.0.9.js（SDK 壳）
        → gettype.php → 返回 type=fullpage + 各组件 JS 路径
        → get.php?is_next=true&type=click → 返回验证码参数(c/s/pic)
        → 用户点击 → 前端生成 w 参数 → ajax.php?w=<加密> → result=click
        → 校验通过回填 validate/seccode → B 站 login 接口
```

| 参数 | 值 |
|------|-----|
| gt | `ac597a4506fee079629df5d8b66dd4fe`（固定） |
| challenge | 动态下发，3 分钟过期（过期报 `old challenge`） |
| 验证类型 | click（点击文字验证），`pic_type=word`，`spec=1*1` |
| get.php 数据 | `c:[12,58,98,36,43,95,62,15,12]`（9 元素，疑似 AES key 偏移提示）、`s`、`pic` |

## 混淆结构分析（已下载样本）

| 文件 | 大小 | 混淆类型 | 估算评分 | 特征 |
|------|------|---------|---------|------|
| `click.3.1.2.js` | 226KB | obfuscator.io CFF + 字符串数组 | ~50 | `$_HBIp`/`$_DA` 访问器，34 while/93 switch |
| `geetest.6.0.9.js` | 208KB | obfuscator.io 强混淆 | ~80 | `B2BB.y9r` 控制流，306 while/306 switch，`\x` 转义 2263 处 |
| `fullpage.9.2.0-guwyxh.js` | - | 同上（`$_HBIp`） | - | 壳组件 |

**关键发现**：
- 全部 3 个 JS **无 AES/RSA/CryptoJS/setPublicKey/encrypt 明文关键字**（加密全被混淆为访问器+数字索引）
- `click.3.1.2.js` 的 `oe()` 仅是 XHR 封装，**w 生成在 `geetest.6.0.9.js` 的 CFF 控制流深处**
- `\x` 十六进制转义 + `fromCharCode(7次)` + 单 decodeURI = 字符串数组以转义形式内联

## w 参数结构（社区公开结论，供参考）

geetest 3.0 click 验证的 w 参数（公开逆向资料）：
```
w = 对称加密( RSA加密(随机密钥) + 载荷 )
载荷 = {u:"", t:时间戳, l:[点击坐标轨迹], e:"", v:"9.2.0", a:环境指纹, d:收集数据}
第一层: AES-CBC 或 RC4（密钥随机，key=16 字节）
第二层: RSA-1024 加密 AES 密钥（公钥由 get.php 下发）
```
（本次样本的 `c:[12,58,98,36,43,95,62,15,12]` 为 get.php 下发的位移/偏移数组）

## 逆向路径（按推荐顺序）

1. **开源方案（最快）**: geetest 3.0 w 生成器开源实现（GitHub 搜索
   `geetest w 参数 生成` / `geetest click verify`），确认与 click.3.1.2 版本算法一致后直接复用
2. **动态 Hook**: 在 geetest iframe 内（CDP `Page.addScriptToEvaluateOnNewDocument` 或
   `Runtime.evaluate` 进 iframe document）Hook `XMLHttpRequest.prototype.send` +
   `JSON.stringify`，捕获 w 生成点明文载荷，对比社区算法
3. **解混淆管道**: `ch_deobfuscate_auto` 需拆分处理（单文件 200KB+ 超时 120s）：
   - 先用 `ch_static_analyze` 定位 `geetest.6.0.9.js` 中 w 赋值点
   - 分段解混淆（每段 <50KB）→ 定位加密链
   - `ch_sdenv_verify_code` 复现验证

## 工程评估

| 方案 | 工作量 | 成功率 | 备注 |
|------|-------|-------|------|
| 开源复用 | 1-2h | 高 | 需验证版本匹配 |
| 动态 Hook | 2-3h | 中 | 需处理 iframe 跨域注入 |
| 全量解混淆 | 5h+ | 中 | 200KB+ CFF 强混淆，工具超时需分段 |

## 已归档样本

- `tmp_click.js`（click.3.1.2.js 226KB）
- `tmp_geetest.js`（geetest.6.0.9.js 208KB）

（位于工作区根目录，可移动至 `cases/geetest_w_param/samples/` 存档）
