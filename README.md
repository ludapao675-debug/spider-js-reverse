# JS Reverse & Protocol Lab

Web / API 加密参数逆向、签名还原、验证码与协议复现实战库。

本仓库已经把 `cases/` **全量上传**。根 README 必须按真实库存展示，而不是只挑几个校园登录和机票站点当门面。

## 规模（2026-08-13 全库盘点）

| 统计项 | 数量 | 说明 |
|------|------|------|
| 案例目录 | **54** | `cases/<name>/`，含 README 或 repro |
| 单篇案例笔记 | **16** | `cases/*_YYYYMMDD.md` |
| 草稿 | **5** | `cases/drafts/`，未升格 |
| 合计可检索入口 | **75** | 目录 + 笔记 + 草稿 |
| 旧 README 展示 | **7** | Expedia / 天巡 / JNU / CHSI / NJU / PKU / 阅文 |
| 漏列比例 | **约 90%** | 旧矩阵把库写成了「6 个校园登录 + 2 个机票」 |

旧 README 还把 clone 地址写成 `crypto-hunter-lite`，目录树假装有 `server/` 分析工具。那是工具仓的结构，不是本仓。本仓是案例库：`https://github.com/ludapao675-debug/spider-js-reverse`。

更细的分族说明见同目录 `cases/overview.md`。

## 状态图例

| 标记 | 含义 |
|------|------|
| 闭环 | 有文档 + 本地脚本，且对过页面/接口返回（假账号或公开接口） |
| 文档+脚本 | README 与 repro 都在，闭环程度以该目录说明为准 |
| 仅文档 | 有分析、缺可运行 repro（或 repro 在别的路径） |
| 仅脚本 | 有 repro，缺 README |
| 草稿 | `cases/drafts/`，未整理 |

算法列写**该案主结论**，不把 README 里的对比站点算法算进来。

---

## 1. 登录 / CAS / SSO（27）

校园金智 AES、东软 `strEnc`、RSA/JSEncrypt、国密 SM2、Steam protobuf、Facebook `#PWD_BROWSER:5` 都在这一族，不是只有 4 所高校。

| 站点 | 核心技术 | 状态 | 文档 |
|------|----------|------|------|
| 学信网 CHSI | 明文 HTTPS | 文档+脚本 | [chsi_login](cases/chsi_login/README.md) |
| 南京大学 NJU | AES-128-CBC 动态盐 | 闭环 | [nju_login](cases/nju_login/README.md) |
| 北京大学 PKU | RSA-2048 PKCS#1 v1.5 base64 | 文档+脚本 | [pku_login](cases/pku_login/README.md) |
| 暨南大学 JNU | 东软 `strEnc` 自定义 3DES | 闭环 | [jnu_login](cases/jnu_login/README.md) |
| 山东大学 SDU | `strEnc`（字段名 `rsa` 是误导） | 闭环 | [sdu_cas_login](cases/sdu_cas_login/README.md) |
| 浙江大学 ZJU | RSA-512 教科书式 hex | 闭环 | [zju_cas](cases/zju_cas/README.md) |
| 清华大学 | 国密 SM2 C1C3C2 | 文档+脚本 | [tsinghua_id_login](cases/tsinghua_id_login/README.md) |
| 武汉大学 WHU | 金智 AES-128-CBC + 滑块脚本 | 闭环 | [whu_login](cases/whu_login/README.md) |
| 成都理工 CDUT | RSA-2048，`password=__RSA__+b64` | 文档+脚本 | [cdut_cas_login](cases/cdut_cas_login/README.md) |
| 中南大学 CSU | 金智 AES-128-CBC | 仅文档 | [csu_login](cases/csu_login/README.md) |
| 昆明理工 KMUST | JSBN RSA-1024 教科书式 hex | 仅脚本 | [kmust_cas_login](cases/kmust_cas_login/) |
| 四川大学 SCU | SM2，公钥动态拉取 | 仅脚本 | [scu_login](cases/scu_login/) |
| 河北 CA | CAS RSA | 仅文档 | [hebic_cas_login](cases/hebic_cas_login_20260708.md) |
| 阅文通行证 | RSA-1024 PKCS#1 v1.5 **hex** JSONP | 闭环 | [yuewen_login](cases/yuewen_login/README.md) |
| B 站 | RSA 登录 + 极验链路 | 文档+脚本 | [bilibili_login](cases/bilibili_login/README.md) |
| Facebook | `#PWD_BROWSER:5` AES-GCM + NaCl | 闭环 | [facebook_login](cases/facebook_login/README.md) |
| Steam | RSA PKCS#1 v1.5 + protobuf WebAPI | 闭环 | [steam_login](cases/steam_login/README.md) |
| 房天下 | RSA-1024 `encryptedString` | 文档+脚本 | [fang_login](cases/fang_login/README.md) |
| 闲鱼 Goofish | RSA / 阿里安全登录 | 仅文档 | [goofish](cases/goofish/README.md) |
| 问财 iwencai | RSA 公钥脚本 | 文档+脚本 | [iwencai_login](cases/iwencai_login/README.md) |
| find-rent | 明文 HTTPS | 仅文档 | [find_rent_login](cases/find_rent_login/README.md) |
| 天翼云 | HMAC / SHA256 登录踩坑 | 仅文档 | [ctyun_login](cases/ctyun_login_lessons_20260706.md) |
| 当乐网 | RSA PKCS#1 v1.5 | 仅文档 | [dcn_login](cases/dcn_login_20260708.md) |
| 滴滴出行 | passport RSA + `wsgsig` | 仅文档 | [didichuxing_login](cases/didichuxing_login_20260709.md) |
| 凤凰云智 | 阿里 idp 登录 | 仅文档 | [iyunzhi_login](cases/iyunzhi_login_20260709.md) |
| 拉勾网 | RSA + AES 登录 | 仅文档 | [lagou_login](cases/lagou_login_20260711.md) |
| 学信网探针 | 与 CHSI 同源的 session 探测 | 仅脚本 | [chsi_cas](cases/chsi_cas/) |

---

## 2. 签名 / 风控参数（12）

字节系 `a_bogus` / `X-Bogus` / acrawler、拼多多 `anti_content`、雪球 `md5__1038`、小红书 `mnsv2`。这是库里工程量最大的一块，旧 README **一个都没挂**。

| 站点 / 课题 | 核心技术 | 状态 | 文档 |
|-------------|----------|------|------|
| 抖音 a_bogus 算法打包 | 99B 指纹 → func148 → 双 SM3 XOR | 仅文档 | [a_bogus](cases/a_bogus/README.md) |
| 抖音双签名长文 | WASM `bdms` + X-Bogus | 仅文档 | [douyin_a_bogus_20260714](cases/douyin_a_bogus_20260714.md) |
| 抖音 X-Bogus 抽样 | `byted_acrawler.frontierSign` 验证 JSON | 仅脚本 | [douyin_a_bogus](cases/douyin_a_bogus/) |
| 抖音 webmssdk | acrawler 解码器 + 离线 X-Bogus | 文档+脚本 | [douyin_webmssdk_xbogus](cases/douyin_webmssdk_xbogus/README.md) |
| 抖音评论协议 | a_bogus + msToken + Cookie | 仅文档 | [douyin_comment_crawl](cases/douyin_comment_crawl/README.md) |
| 今日头条 a_bogus | `bdms.js` JSVMP，非抖音 WASM | 仅文档（目录 82 文件） | [toutiao_a_bogus](cases/toutiao_a_bogus/README.md) |
| 头条 acrawler `_signature` | `_$jsvmprt` JSVMP | 仅文档 | [toutiao_acrawler_sign](cases/toutiao_acrawler_sign_20260711.md) |
| 头条 acrawler 工程 | 字节码 / replay / 多份 trace | 仅脚本（52 文件） | [toutiao_acrawler](cases/toutiao_acrawler/) |
| 拼多多商品评论 | `anti_content` + TLS 通道绑定 | 文档+脚本 | [pdd_goods_comments](cases/pdd_goods_comments/README.md) |
| 小红书 mnsv2 | `x-s` / `x-t`，不是 JSVMP | 仅脚本 | [xhs_acrawler](cases/xhs_acrawler/) |
| 雪球搜索 | `md5__1038` = SHA-256 切片 | 仅文档 | [xueqiu_md5_1038](cases/xueqiu_md5_1038/README.md) |
| 京东 cactus | `behavior_report` 行为上报 | 仅文档 | [jd_cactus_behavior_report](cases/jd_cactus_behavior_report/README.md) |

---

## 3. 直播 / IM / 弹幕（3）

| 站点 | 核心技术 | 状态 | 文档 |
|------|----------|------|------|
| 抖音 Web 私信 | protobuf + 会话票据 | 仅文档 | [douyin_web_im_send](cases/douyin_web_im_send/README.md) |
| 抖音 Web 直播发言 | `/webcast/room/chat/` | 仅文档 | [douyin_web_live_chat](cases/douyin_web_live_chat/README.md) |
| 快手 PC 直播弹幕 | protobuf over WebSocket + `__NS_hxfalcon` | 仅文档 | [kuaishou_live_danmu](cases/kuaishou_live_danmu/README.md) |

---

## 4. 验证码 / 滑块（4）

| 站点 / 组件 | 核心技术 | 状态 | 文档 |
|-------------|----------|------|------|
| 京东礼品卡 JCAP | WASM 滑块 + headless Blink | 文档+脚本 | [jd_giftcard_jcap](cases/jd_giftcard_jcap/README.md) |
| kgCaptcha | 接口原图缺口 + 拖拽回弹 | 仅文档 | [kgcaptcha_slider](cases/kgcaptcha_slider/README.md) |
| 快手自研滑块 | `captcha.zt.kuaishou.com` | 仅文档 | [kuaishou_slider](cases/kuaishou_slider/README.md) |
| 极验 3.0 `w` | B 站链路已摸清，`w` 未闭环 | 仅文档 | [geetest_w_param](cases/geetest_w_param/README.md) |

---

## 5. 列表 / 搜索 / 资讯（16）

| 站点 | 核心技术 | 状态 | 文档 |
|------|----------|------|------|
| 采招网 | 搜索分页本地复现 | 文档+脚本 | [bidcenter_search_pagination](cases/bidcenter_search_pagination/README.md) |
| 查策网 | 响应 AES-CBC `myDecrypt` | 闭环 | [chacewang_pagination](cases/chacewang_pagination/README.md) |
| 甘肃公资 | SM2 `encryptedPost`，响应明文 | 闭环 | [gansu_ggzyjy_list_search](cases/gansu_ggzyjy_list_search/README.md) |
| 异乡好居 | `X-Client-Signature` AES-128-CBC | 闭环 | [uhouzz_pagination](cases/uhouzz_pagination/README.md) |
| 酷我排行榜 | 请求头 `Secret` + Cookie | 闭环 | [kuwo_rank](cases/kuwo_rank/README.md) |
| 米画师 stalls | WASM 分页 | 文档+脚本 | [mihuashi_stalls_list](cases/mihuashi_stalls_list/README.md) |
| 微博评论 | 明文 + SUB / XSRF | 闭环 | [weibo_comment](cases/weibo_comment/README.md) |
| 微博热搜 | 明文 + Referer 反爬 | 闭环 | [weibo_hot_realtime](cases/weibo_hot_realtime/README.md) |
| 热搜时光机 | AES `_e` 通道 | 闭环 | [weibotop_time_machine](cases/weibotop_time_machine/README.md) |
| 天天基金定投排行 | JSONP 无加密 | 仅脚本 | [eastmoney_dingtou_yndt](cases/eastmoney_dingtou_yndt/) |
| 观鸟活动 | RSA + AES 请求体 | 仅脚本 | [birdreport_activity](cases/birdreport_activity/) |
| 中国土地市场 | 请求头 SHA256 | 仅文档 | [landchina_supply_plan](cases/landchina_supply_plan_20260709.md) |
| 南山医院招标 | AES+RSA ECB | 仅文档 | [zbcg_sznsyy](cases/zbcg_sznsyy_home_notice_20260709.md) |
| 中国版本图书馆 | AES 新闻列表 | 仅文档 | [cnpub_news](cases/cnpub_news_20260709.md) |
| 招投标 ctbpsp | 翻页 recommand | 仅文档 | [ctbpsp_recommand](cases/ctbpsp_recommand_20260709.md) |
| spa2.scrape.center | AES 分页（教学站） | 仅文档 | [spa2_scrape_center](cases/spa2_scrape_center_20260709.md) |

---

## 6. 阅读 / 内容（3）

| 站点 | 核心技术 | 状态 | 文档 |
|------|----------|------|------|
| 书旗网 | 章节 `contentfree` 协议 | 文档+脚本 | [aliwx_reader](cases/aliwx_reader/README.md) |
| 书旗网笔记 | 与上条同接口的过程稿 | 仅文档 | [aliwx_reader_contentfree](cases/aliwx_reader_contentfree_20260709.md) |
| 番茄小说 | Web 字体映射反爬 | 文档+脚本 | [fanqie_novel_font](cases/fanqie_novel_font/README.md) |

另有根目录 `cases/qidian_reader_sdenv.py`（起点阅读补环境草稿，未单独立项）。

---

## 7. 机票 / 出行（2）

| 站点 | 核心技术 | 状态 | 文档 |
|------|----------|------|------|
| Expedia | GraphQL APQ + Akamai / DataDome | 文档+脚本 | [expedia_flight](cases/expedia_flight/README.md) |
| 天巡 Skyscanner | `web-unified-search` 会话协议 | 闭环 | [skyscanner_flight](cases/skyscanner_flight/README.md) |

根目录还有 `expedia_flight_repro.py` / `skyscanner_flight_repro.py` 与目录内 `repro.py` 重复，以及 7.8MB 的 `expedia_lax_pek_result.json`（抓包结果，不宜当案例正文）。

---

## 8. 翻译 / Protobuf / 题库（3）

| 站点 / 课题 | 核心技术 | 状态 | 文档 |
|-------------|----------|------|------|
| 有道翻译 | MD5 签名 + AES 响应 | 仅文档 | [youdao_translate](cases/youdao_translate_20260708.md) |
| Protobuf 能力验证 | wire / gzip / gRPC 帧 | 仅文档 | [protobuf_capability](cases/protobuf_capability_deep_test_20260804.md) |
| 猿人学第 9 题 | 动态 cookie `m` | 仅文档 | [yuanrenxue_match9](cases/yuanrenxue_match9_dynamic_cookie2/README.md) |

---

## 草稿（未升格，5）

| 名称 | 说明 |
|------|------|
| [jd_sso_rac_h5st_wasm](cases/drafts/jd_sso_rac_h5st_wasm_20260718.md) | 京东 SSO `h5st` 5.3 + WASM |
| [xueqiu_md5_1038 草稿](cases/drafts/xueqiu_md5_1038_20260718.md) | 雪球签名过程稿 |
| `drafts/meituan_login_test/` | 美团登录解混淆对照 |
| `drafts/multi_site_deobf_combat/` | 京东 / 快手 / 美团 / 小红书 多站解混淆作战 |
| `drafts/deob_test/` | webmssdk 等价性试验 |

---

## 重复与关联（读库时不要当成 70 个互不相关的站）

字节系被拆成了算法笔记、工程目录、验证 JSON 三层，旧 README 全漏：

- 抖音：`a_bogus/` + `douyin_a_bogus_20260714.md` + `douyin_a_bogus/` + `douyin_webmssdk_xbogus/` + 评论 / 私信 / 直播
- 头条：`toutiao_a_bogus/`（JSVMP `bdms`）与 `toutiao_acrawler/`（`_signature`）不是同一条签名链
- 学信网：`chsi_login` 正式案，`chsi_cas` 只是探针
- 书旗：目录版与 `aliwx_reader_contentfree_20260709.md` 同接口
- 雪球：正式 README 指向仓库外 `scratch/`，本仓只有摘要

---

## 方法论

- [JS 定位方法](docs/js_positioning_methods.md)
- [MCP 踩坑日志](docs/mcp_pitfalls.md)
- [案例写法](cases/case_template.md)

---

## 快速开始

```bash
git clone https://github.com/ludapao675-debug/spider-js-reverse.git
cd spider-js-reverse

pip install pycryptodome requests
# 部分案例另需：gmssl / pynacl / curl_cffi / tls-client / Node
```

例：阅文登录与网页 JSONP 返回对齐

```bash
python cases/yuewen_login/repro.py
```

例：天巡机票

```bash
python cases/skyscanner_flight/repro.py
```

不要从本仓找 FastAPI / MCP / CDP，那些在工具仓 `crypto-hunter-lite`。

---

## 免责声明

1. 仅供学术交流、安全研究与技术探讨。
2. 禁止用于未授权访问、商业抓取或攻击。
3. 遵守目标站 `robots.txt` 与当地法律；后果由使用者自负。
4. 站点认为侵权可联系删除。
