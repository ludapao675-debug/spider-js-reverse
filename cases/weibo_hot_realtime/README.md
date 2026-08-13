# 微博实时热搜 weibo.com/a/hot/realtime 逆向

**样本**: `https://weibo.com/a/hot/realtime`（微博实时热点榜）
**状态**: 接口协议已还原并本地复现

## 逆向结论

### 1. 页面架构
- 老版 SSR 页面，热榜数据直接内联 HTML，无独立正文接口
- 打开时自动跳转 `passport.weibo.com/visitor/visitor`（访客流程），获取 `SUB/SUBP/PC_TOKEN` cookie 后回跳

### 2. 动态数据接口 —— **零加密**

| 接口 | 参数 | 说明 |
|------|------|------|
| `GET /ajax/side/hotSearch` | - | 实时热搜 50 条（realpos/note/num/word/flag） |
| `GET /ajax/statuses/hot_band` | - | 热搜榜 50 条（含 trend 趋势 up/down/flat） |
| `GET /ajax/statuses/topiclist` | `category=N` | 分类热搜（s.weibo 版） |

**无签名、无 token、无加密参数**。唯一校验 = **Referer 反爬**：
- 无 `Referer` → `403 Forbidden`
- 带 `Referer: https://weibo.com/a/hot/realtime` → 200 完整 JSON
- **无需 cookie**：裸请求（无任何 cookie）带 Referer 即可拿全量数据

### 3. 访客 cookie 流程（非热榜必需）
```
GET passport.weibo.com/visitor/genvisitor?cb=gen_callback&fp=<设备指纹JSON>&url=...
  → {"retcode":20000000,"data":{"tid":"01AfV9z..."}}
GET passport.weibo.com/visitor/visitor?entry=miniblog&a=enter&url=...&domain=.weibo.com...
  → 页面 JS (mini_original.js) 校验 tid → 跳回原页面
```
- `tid` 是访客标识，配合 `mini_original.js` 的**设备指纹采集**（fp 参数，Canvas/Fonts/屏幕等）
- `SUB/SUBP` cookie 由服务端 Set-Cookie 下发，**前端不参与签名计算**
- 登录态接口（关注/点赞/评论/发博）才需要 `SUB` + `XSRF-TOKEN`；热榜 GET 接口完全不需要

## 复现脚本

```
python repro.py hotsearch --top 5    # 实时热搜前5
python repro.py hotband              # 热搜榜全量50条
```

验证样本：
- `hotsearch`：rank1「朱镕基同志逝世」热度114万
- `hotband`：rank1 同上，rank2「微信群聊可以彻底关闭通知了」109万
- 本地带 Referer 裸请求，HTTP 200，与浏览器抓包数据一致

## 踩坑记录
- **PowerShell 转义**：`-c` 内联 Python 含嵌套引号/JSON 易炸，长逻辑用临时 `.py` 文件
- **hot_band 无 realpos**：用 `position` 字段，需兼容 None
- **Referer 必带**：裸请求 403，这是该站唯一反爬门槛（非加密）
