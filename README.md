# JS Reverse & Protocol Lab

Web / API 加密参数与协议复现案例。收录标准：本地脚本已跑通，输出与页面或接口返回一致（假账号走业务错误码也算）。

不收录验证码求解，也不收录只有分析文档、没有可运行代码的条目。

依赖：Python 3.9+，部分案例需要 Node.js。

```bash
git clone https://github.com/ludapao675-debug/spider-js-reverse.git
cd spider-js-reverse
pip install pycryptodome requests
# 个别案例另需：pynacl、Node 与对应 package.json
```

## 登录

| 站点 | 算法 | 验证 | 文档 |
|------|------|------|------|
| 学信网 | 明文 HTTPS | 假账号提交，协议负向通过 | [chsi_login](cases/chsi_login/README.md) |
| 暨南大学 | 东软 `strEnc` | 官方 `des.js` 加解密往返 | [jnu_login](cases/jnu_login/README.md) |
| 山东大学 | `strEnc`（字段名 `rsa`） | 与页面样本逐字节一致 | [sdu_cas_login](cases/sdu_cas_login/README.md) |
| 浙江大学 | RSA-512 hex | 密文格式与确定性校验通过 | [zju_cas](cases/zju_cas/README.md) |
| 成都理工 | RSA-2048 `__RSA__`+base64 | 公钥拉取 + PKCS#1 自检 | [cdut_cas_login](cases/cdut_cas_login/README.md) |
| 阅文通行证 | RSA-1024 PKCS#1 v1.5 hex | JSONP `code`/`message` 与网页一致 | [yuewen_login](cases/yuewen_login/README.md) |
| Facebook | `#PWD_BROWSER:5` AES-GCM + NaCl | 假账号 GraphQL 返回凭据错误 1348131 | [facebook_login](cases/facebook_login/README.md) |

```bash
python cases/yuewen_login/repro.py
python cases/chsi_login/repro.py
python cases/sdu_cas_login/repro.py
python cases/zju_cas/reproduce.py
python cases/cdut_cas_login/repro.py
python cases/facebook_login/repro.py
node cases/jnu_login/repro.js
```

## 列表 / 搜索 / 资讯

| 站点 | 算法 | 验证 | 文档 |
|------|------|------|------|
| 查策网 | 响应 AES-CBC | 解密得到分页条目 | [chacewang_pagination](cases/chacewang_pagination/README.md) |
| 采招网 | 搜索分页解密 | 解密顶层字段成功 | [bidcenter_search_pagination](cases/bidcenter_search_pagination/README.md) |
| 甘肃公资 | SM2 请求体 | `code=0` 且返回列表 | [gansu_ggzyjy_list_search](cases/gansu_ggzyjy_list_search/README.md) |
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

| 站点 | 算法 | 验证 | 文档 |
|------|------|------|------|
| 书旗网 | 章节 `contentfree` | 拉到正文 | [aliwx_reader](cases/aliwx_reader/README.md) |
| 番茄小说 | Web 字体映射 | 3/3 样本精确还原 | [fanqie_novel_font](cases/fanqie_novel_font/README.md) |

```bash
python cases/aliwx_reader/repro.py
python cases/fanqie_novel_font/repro.py
```

## 机票

| 站点 | 算法 | 验证 | 文档 |
|------|------|------|------|
| 天巡 | `web-unified-search` 会话 | 返回可报价航班 | [skyscanner_flight](cases/skyscanner_flight/README.md) |

```bash
python cases/skyscanner_flight/repro.py
```

## 签名

| 站点 | 算法 | 验证 | 文档 |
|------|------|------|------|
| 抖音 webmssdk | X-Bogus 离线 | `OFFLINE_XBOGUS_OK` | [douyin_webmssdk_xbogus](cases/douyin_webmssdk_xbogus/README.md) |

```bash
node cases/douyin_webmssdk_xbogus/repro_offline_xbogus.js
```

## 说明

- 登录案例使用随机或占位账号，不收集、不提交真实凭据。
- 案例写法见 [cases/case_template.md](cases/case_template.md)。

## 免责声明

仅供学术交流与安全研究。禁止用于未授权访问或违法抓取。遵守目标站规则与当地法律，后果自负。
