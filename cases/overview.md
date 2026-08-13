# 案例库说明

这里存放已经完成验证的逆向案例。

## 作用

- 复用已经确认过的入口定位方法
- 复用环境补丁和运行时取证方式
- 复用离线复现脚本
- 记录站点升级后的变化点

## 文件命名

- 使用小写字母和下划线
- 建议格式：`站点_目标_日期.md`
- 示例：`youdao_sign_20260703.md`

## 每个案例至少要写清楚

- 目标站点或接口
- 请求路径和关键参数
- 参数生成位置
- 运行时证据
- 复现脚本
- 验证结果
- 失败坑点
- 失败坑点建议写成固定格式：误判 -> 真实原因 -> 识别信号 -> 修复方式 -> 可复用规则

## 什么时候新增案例

- 成功定位了新参数生成逻辑
- 成功做出了本地复现
- 成功解决了同类站点的升级变化
- 成功确认某类浏览器问题的稳定修复方案
- 如果某个坑点会在别的站点重复出现，优先把它写进案例末尾的「踩坑记录」，必要时再抽成独立通用规则
- `ch_task_finish` 结束任务后会自动生成案例草稿到 `cases/drafts/`，先看草稿再整理为正式案例
- 如果本次验证依赖补环境，草稿里会自动记录「超级补环境」判断，后续优先复用这层判断而不是手工回忆
- 如果任务遇到验证码/验证挑战，优先用 `ch_verification_assess` 先分类，再决定是 AI 辅助、补环境还是人工接力，不要直接当成普通脚本错误
- 如果滑块是 hover 后才出现，先用 `ch_page_hover` 触发显露，再拖拽，不要一开始就假设滑块节点已经在 DOM 里可见

## 案例列表

| 日期 | 案例 | 类型 | 坑数 | 要点 |
|------|------|------|------|------|
| 0708 | [有道翻译](youdao_translate_20260708.md) | MD5签名 + AES解密 | 5个 | 反爬假数据 / urlsafe-base64 / 新旧API共存 |
| 0708 | [当乐网登录](dcn_login_20260708.md) | RSA加密 | — | PKCS#1 v1.5 |
| 0708 | [河北CA登录](heibic_cas_login_20260708.md) | CAS单点 | — | — |
| 0709 | [landchina供地计划](landchina_supply_plan_20260709.md) | 请求头Hash(SHA256) | 4个 | 旧资料复用/SSL误判/频率限制 |
| 0709 | [zbcg南山医院通知公告](zbcg_sznsyy_home_notice_20260709.md) | AES+RSA(ECB)请求/响应加密 | 5个 | 旧资料复用/RSA私钥硬编码/Python复现 |
| 0706 | [天翼云登录](ctyun_login_lessons_20260706.md) | — | — | — |
| 0711 | [今日头条签名](toutiao_acrawler_sign_20260711.md) | JSVMP签名(_$jsvmprt) | 3个 | 检测盲区修复/hex取指/操作数推断 |
| 0714 | [抖音双签名](douyin_a_bogus_20260714.md) | WASM签名(bdms)+X-Bogus | 4个 | X-Bogus入口已验证/a_bogus降级禁用/会话ID失效规避 |
| 0718 | [京东SSO rac h5st（草稿）](drafts/jd_sso_rac_h5st_wasm_20260718.md) | h5st 5.3 + WASM | — | `s`=ParamsSign appId`73806`；WASM `ws_js/wasm/single.min.js` 待拆；勿与 AKS 混淆 |
| 0719 | [成都理工CAS登录](cdut_cas_login/README.md) | RSA-2048 + `__RSA__` | 1 | JSEncrypt；公钥 `/cas/jwt/publicKey`；`password=__RSA__+b64` |
| 0719 | [清华统一身份登录](tsinghua_id_login/README.md) | 国密 SM2 C1C3C2 | 4 | `sm2Util.doEncryptStr`；detect 误报 plaintext；listener 丢文档 POST body |
| 0722 | [暨南大学 CAS 登录](jnu_login/README.md) | 东软3DES + 易盾挑战 | 2 | `strEnc` 逐字节验证；真实验证码只读取证，不把页面身份当作通过 |
| 0722 | [房天下登录](fang_login/README.md) | 第三方安全验证挑战 | — | 只读 smoke；`inspect/plan` 不执行拖拽，必须绑定当前 attempt 的显式验证事实 |
| 0722 | [查策网产业分页](chacewang_pagination/README.md) | 响应 AES-CBC (`myDecrypt`/`ccwfp___`) | 1 | 请求无签名；data=Base64 包装 + MD5 链式派生 key/iv |
| 0722 | [Facebook 登录](facebook_login/README.md) | `#PWD_BROWSER:5` AES-GCM + NaCl SealedBox | 3 | GraphQL `useCDSWebLoginMutation`；公钥 `caa_password_encryption_data`；勿混用 IG key_id=132 |
| 0724 | [抖音评论协议爬取](douyin_comment_crawl/README.md) | a_bogus(fn150)+msToken+Cookie | 8 | sdenv 本地签；Cookie/xmst 缓存可关浏览器；comment/list 每页重签；勿把遥测当 a_bogus |
| 0724 | [a_bogus 算法打包](a_bogus/README.md) | 99B→148→双SM3 XOR→130 Base64 | — | func 150 leave==活体；工程解 sdenv，纯算法未闭环 |
| 0725 | [抖音 Web 私信发送](douyin_web_im_send/README.md) | protobuf 私信 + 三模式 + `--to` | 11 | conversation_id 换人；identity/ticket 服务端票据；裸 HTTP 解析必挂；控频防验证码 |
| 0725 | [抖音 Web 直播弹幕发送](douyin_web_live_chat/README.md) | GET `/webcast/room/chat/` | 6 | 长 `room_id`；短号走 enter 的 `enter_room_id`；Cookie 即可，a_bogus 非强依赖 |
| 0728 | [甘肃公共资源列表分页](gansu_ggzyjy_list_search/README.md) | SM2 请求体加密 (`encryptedPost`) | 3 | URL `params` 仅 gzip 路由态；`/ESProjectList/searchByPage`；响应明文 |
