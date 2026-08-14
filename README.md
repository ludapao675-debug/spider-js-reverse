# Spider JS Reverse — JS 加密逆向与协议复现案例库

Web / API 加密参数逆向的**可运行案例集**：每个目录 = 一份逆向文档（算法结构、定位过程、踩坑记录）+ 一套本地跑通的复现脚本。

**收录标准**：本地脚本已跑通，输出与页面或接口返回一致（假账号走业务错误码也算闭环）。
**不收录**：验证码求解、只有分析文档没有可运行代码的条目。

覆盖类型：登录密码加密（RSA / AES / SM2 / 3DES / AES-GCM）、动态 Cookie 挑战、请求签名（MD5 / BLAKE2s / ChaCha / WASM）、响应解密、protobuf 协议、动态字体反爬。当前 **31 个闭环案例**。

## 快速开始

```bash
git clone https://github.com/ludapao675-debug/spider-js-reverse.git
cd spider-js-reverse
pip install pycryptodome requests
# 按案例另需：pynacl / curl_cffi / gmssl / fonttools / protobuf，以及 Node.js
```

依赖：Python 3.9+（快手案例建议 3.10+），部分案例需要 Node.js。

---

## 登录加密

| 站点 | 算法 | 闭环验证 | 文档 |
|------|------|----------|------|
| 学信网 | 明文 HTTPS | 假账号提交，协议负向通过 | [chsi_login](cases/chsi_login/README.md) |
| 暨南大学 | 东软 `strEnc` 3DES | 官方 `des.js` 加解密往返逐字节一致 | [jnu_login](cases/jnu_login/README.md) |
| 山东大学 | `strEnc`（字段名 `rsa`） | 与页面样本逐字节一致 | [sdu_cas_login](cases/sdu_cas_login/README.md) |
| 浙江大学 | RSA-512 hex | 密文格式与确定性校验通过 | [zju_cas](cases/zju_cas/README.md) |
| 成都理工 | RSA-2048 `__RSA__`+base64 | 公钥拉取 + PKCS#1 自检 | [cdut_cas_login](cases/cdut_cas_login/README.md) |
| 南京大学 | AES-128-CBC（动态盐） | 固定 key/iv 与浏览器 `getAesString` 逐字节一致 | [nju_login](cases/nju_login/README.md) |
| 武汉大学 | AES-CBC（随机前缀+密码） | Python==页面 MATCH + 密文解密还原密码 + 实战 401 负向 | [whu_login](cases/whu_login/README.md) |
| 北京大学 | RSA-2048 PKCS#1 v1.5 | 自生成密钥加解密闭环，长度与 JSEncrypt 一致 | [pku_login](cases/pku_login/README.md) |
| 清华大学 | 国密 SM2（C1C3C2） | `--self-test` 前缀/长度/字段名通过，与页面 `sm2Util` 同结构 | [tsinghua_id_login](cases/tsinghua_id_login/README.md) |
| Steam | RSA-2048 + protobuf WebAPI | 页面真实密文用私钥解密还原明文（PASS）+ 200 结构兼容 | [steam_login](cases/steam_login/README.md) |
| Bilibili | RSA（`getKey`） | 假账号返回 -105（格式正确证据）；极验 `w` 未闭环 | [bilibili_login](cases/bilibili_login/README.md) |
| 阅文通行证 | RSA-1024 PKCS#1 v1.5 hex | JSONP `code`/`message` 与网页一致 | [yuewen_login](cases/yuewen_login/README.md) |
| Facebook | `#PWD_BROWSER:5` AES-GCM + NaCl SealedBox | 假账号 GraphQL 返回凭据错误 1348131 | [facebook_login](cases/facebook_login/README.md) |

```bash
python cases/nju_login/repro.py        # 自动拉取动态盐并加密
python cases/whu_login/repro.py        # 另含 repro_slider.py 滑块 sign 复现
python cases/pku_login/repro.py
python cases/tsinghua_id_login/repro.py --self-test
python cases/steam_login/steam_login.py
python cases/bilibili_login/repro.py
python cases/yuewen_login/repro.py
python cases/chsi_login/repro.py
python cases/sdu_cas_login/repro.py
python cases/zju_cas/reproduce.py
python cases/cdut_cas_login/repro.py
python cases/facebook_login/repro.py
node cases/jnu_login/repro.js
```

## 动态 Cookie / JS 挑战

| 站点 | 算法 | 闭环验证 | 文档 |
|------|------|----------|------|
| 同花顺行情 | chameleon `hexin-v`（43B buffer → strhash 校验和 → XOR 流 → 自定义 base64） | Node vm 沙箱执行原脚本生成 v：200 正样本 + 401 负样本 | [ths_q_hexin_v](cases/ths_q_hexin_v/README.md) |

```bash
cd cases/ths_q_hexin_v
node run_sandbox.js      # 沙箱执行 chameleon 原脚本，产出 v_sandbox.txt
./validate.ps1           # 多样本正/负向验证（Windows PowerShell）
```

要点：401 挑战 + `chameleon.*.js` 直接沙箱整体执行调 `qn.update()`，不要手工还原字节布局；验证 gate 必须带随机 query 穿透 CDN 缓存。

## 签名 / 协议

| 站点 | 算法 | 闭环验证 | 文档 |
|------|------|----------|------|
| 猫眼专业版 | `signKey` = MD5(拼接串) + WOFF 动态字体拓扑解密 | 单接口拿全量解密数据，字体随机码点实时映射 | [maoyan_dashboard](cases/maoyan_dashboard/README.md) |
| 快手直播弹幕 | `__NS_hxfalcon`（BLAKE2s 变体 + LFSR + ChaCha20 变体）+ protobuf WS | 纯 Python 签名 `result=1`，全链路拉取弹幕 | [kuaishou_live_danmu](cases/kuaishou_live_danmu/README.md) |
| 微博评论 | `mid` base62 解码 + 评论接口 | 本地解码反向校验 + 29 条评论完整解析 | [weibo_comment](cases/weibo_comment/README.md) |
| 抖音 webmssdk | X-Bogus 离线 | `OFFLINE_XBOGUS_OK` | [douyin_webmssdk_xbogus](cases/douyin_webmssdk_xbogus/README.md) |

```bash
python cases/maoyan_dashboard/repro.py
python cases/kuaishou_live_danmu/kuaishou_live_danmu.py --room <短号> --count 20   # 需 pip install curl_cffi
python cases/weibo_comment/repro.py --mid Rd3GvlX2Q --uid <uid> --cookie "SUB=..; XSRF-TOKEN=.."
node cases/douyin_webmssdk_xbogus/repro_offline_xbogus.js
```

快手案例需一次性浏览器 Cookie（`did`/`kwfv1` 访客身份），脚本可自动从已连接调试浏览器采集并缓存；签名本身纯 Python 生成。

## 列表 / 搜索 / 资讯

| 站点 | 算法 | 闭环验证 | 文档 |
|------|------|----------|------|
| 查策网 | 响应 AES-CBC（MD5 链式派生 key/iv） | 解密得到分页条目 | [chacewang_pagination](cases/chacewang_pagination/README.md) |
| 采招网 | 搜索分页解密 | 解密顶层字段成功 | [bidcenter_search_pagination](cases/bidcenter_search_pagination/README.md) |
| 甘肃公资 | SM2 请求体加密 | `code=0` 且返回列表 | [gansu_ggzyjy_list_search](cases/gansu_ggzyjy_list_search/README.md) |
| 异乡好居 | AES `X-Client-Signature` | 解密房源分页 | [uhouzz_pagination](cases/uhouzz_pagination/README.md) |
| 酷我排行榜 | 请求头 `Secret` | 与抓包 Secret 逐字节一致 | [kuwo_rank](cases/kuwo_rank/README.md) |
| 米画师 | WASM `M-S`/`M-T` | 拉到 stalls 列表 | [mihuashi_stalls_list](cases/mihuashi_stalls_list/README.md) |
| 微博热搜 | 明文 + Referer | 返回热搜榜 | [weibo_hot_realtime](cases/weibo_hot_realtime/README.md) |
| 热搜时光机 | AES `_e` | `hotspot` 接口返回主题分析 | [weibotop_time_machine](cases/weibotop_time_machine/README.md) |
| 天天基金定投排行 | JSONP 无加密 | 返回排行表 | [eastmoney_dingtou_yndt](cases/eastmoney_dingtou_yndt/README.md) |

甘肃案例需先 `cd cases/gansu_ggzyjy_list_search && npm install`。

```bash
python cases/chacewang_pagination/repro.py
python cases/gansu_ggzyjy_list_search/repro.py
python cases/uhouzz_pagination/repro.py
python cases/weibo_hot_realtime/repro.py
python cases/weibotop_time_machine/repro.py hotspot
python cases/eastmoney_dingtou_yndt/repro.py
node cases/kuwo_rank/repro.js
```

## 阅读 / 内容

| 站点 | 算法 | 闭环验证 | 文档 |
|------|------|----------|------|
| 书旗网 | 章节 `contentfree` 解密 | 拉到正文 | [aliwx_reader](cases/aliwx_reader/README.md) |
| 番茄小说 | Web 动态字体码点映射 | 3/3 样本精确还原 | [fanqie_novel_font](cases/fanqie_novel_font/README.md) |

```bash
python cases/aliwx_reader/repro.py
python cases/fanqie_novel_font/repro.py
```

## 机票

| 站点 | 算法 | 闭环验证 | 文档 |
|------|------|----------|------|
| 天巡 | `web-unified-search` 会话链 | 返回可报价航班 | [skyscanner_flight](cases/skyscanner_flight/README.md) |
| Expedia | 会话 + 参数还原 | HTTP 200，25 条真实航班报价 | [expedia_flight](cases/expedia_flight/README.md) |

```bash
python cases/skyscanner_flight/repro.py
python cases/expedia_flight/repro.py
```

---

## 案例写法

每个案例目录遵循统一结构，写法见 [cases/case_template.md](cases/case_template.md)：

```
cases/<site>_<target>/
├── README.md    # 算法结构 + 定位过程 + 误判点 + 验证结果 + 可复用规则
└── repro.py     # 可独立运行的复现脚本（或 repro.js / .ps1）
```

踩坑记录统一格式：**误判 → 真实原因 → 识别信号 → 修复方式 → 可复用规则**。

## 说明

- 登录案例使用随机或占位账号，不收集、不提交真实凭据；案例中出现的密钥均为站点公开公钥或自生成测试密钥。
- 依赖真实登录态的案例（微博、快手）需要自行提供 Cookie，脚本不做硬编码。

## 免责声明

仅供学术交流与安全研究。禁止用于未授权访问或违法抓取。遵守目标站规则与当地法律，后果自负。
