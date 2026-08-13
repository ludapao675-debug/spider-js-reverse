# 书旗网 aliwx.com.cn 阅读页正文协议

**样本**: `https://www.aliwx.com.cn/reader?bid=6813923&cid=674174`（《偃师传说》第1章）
**状态**: 免费章节协议已还原并本地复现；付费章节参数加密待续

## 逆向链路

1. 页面为 **SSR + 数据埋点**，正文与目录随 HTML 下发，无正文动态接口
2. 埋点 JSON 存于 `<i class="page-data js-*">` 标签（HTML 实体转义，需 `html.unescape`）
   - `js-dataBookInfo`：书籍信息（authorId/bookId/payMode/price…）
   - `js-dataChapters`：章节全集 183 章 + 接口前缀/后缀
   - `js-dataUserInfo`：用户信息
3. 章节数据关键字段（`reader.js` 使用）：
   - `freeContUrlPrefix` / `chargeContUrlPrefix` / `shortContUrlPrefix`：内容接口前缀
   - 每章 `contUrlSuffix`：免费章节 = 明文参数 + 服务端生成的 `sign`
   - 每章 `shortContUrlSuffix`：试读接口

## 正文接口

```
GET https://c13.shuqireader.com/pcapi/chapter/contentfree/?bookId=6813923&chapterId=674175&ut=1754876996&num=1&ver=1&aut=1754876998&sign=6b6df1b9908f043ef160f389c2f2d896
```

- `sign` 由服务端生成并随 `contUrlSuffix` 下发，**前端不参与计算**，直接拼用即可
- 响应: `{"state":"200","message":"success","ChapterContent":"<ROT13(Base64(UTF8(正文)))>"}`
- 付费章节走 `contentcharge`，参数切换为 `reqEncryptType=1`（bookId/chapterId/user_id 自研 base64 变体加密）

## 解密算法（reader.js `_decodeCont`）

三层逆序解码，本地 Python 已验证（`repro.py`）：

1. **ROT13**：`i = (ch.toLowerCase().charCodeAt(0) - 83) % 26 || 26`，大写 base 64 / 小写 base 96
2. **Base64**：标准字母表解码
3. **UTF-8**：字节解码 → 正文 HTML（`<br/>` 分段）

```python
def rot13(s):  # 等价凯撒位移 13，自反
    out = []
    for ch in s:
        if ch.isalpha():
            e = ord(ch) // 97
            i = (ord(ch.lower()) - 83) % 26 or 26
            out.append(chr(i + (64 if e == 0 else 96)))
        else:
            out.append(ch)
    return "".join(out)
```

## 复现脚本

```
python repro.py                    # 默认抓当前章
python repro.py --bid 6813923 --cid 674175
python repro.py --bid 6813923 --all   # 抓全书免费章节（每章一个 txt）
```

## 验证样本

- 接口 HTTP 200，`state=200`，ChapterContent 7043 字节密文
- 解密输出第1章正文 1913 字（首句：月圆之夜，风暮原。）

## 付费章节结论（无需逆向加密算法）

- 付费章节 `contUrlSuffix` 中 `bookId/chapterId/user_id` 的加密串（`bTkwAQ4B...=` 形式）
  由**服务端随章节数据下发**，前端零参与生成，直接拼 `chargeContUrlPrefix + contUrlSuffix` 即可
- 加密串**每次 SSR 动态生成**（同书两次抓取结果不同），本地复现时实时抓页面拿最新 suffix
- 未购买/未登录请求返回 `403 verify chapter read error`，`failReason=[1,3,4,5,6]`（鉴权层拦截，
  非加密层问题）；正文获取需带已购账号 Cookie

## 未完成项

- 登录/打赏/月票等接口的 `_token/_ts` 签名（`/api/issueRecTicket` 等，`appConfig.apiToken`）
