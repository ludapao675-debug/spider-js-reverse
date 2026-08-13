# 微博单条微博评论接口逆向

**样本**: `https://weibo.com/7911647609/Rd3GvlX2Q`（博主「喜欢短毛小狗_EK」微博正文）
**状态**: 评论接口协议已还原并本地复现

## 逆向结论

### 1. 评论接口 —— 零加密

```
GET https://weibo.com/ajax/statuses/buildComments
```

| 参数 | 值 | 说明 |
|------|-----|------|
| `is_reload` | 1/0 | 1=首屏 0=翻页 |
| `id` | 十进制微博 id | 由 URL mid 短码转换 |
| `is_show_bulletin` | 2 | 公告展示 |
| `is_mix` | 0 | 不混合 |
| `count` | 10 | 每页条数 |
| `uid` | 博主 uid | |
| `fetch_level` | 0 | 0=全部 1=仅楼中楼 |
| `flow` | 0/1 | 0=热度 1=时间（`filter_group` 由响应返回） |
| `locale` | zh-CN | |

**参数全明文，无签名、无加密、无时间戳**。

### 2. 校验机制 = SUB cookie + XSRF-TOKEN（非加密，防爬核心）

- `X-XSRF-TOKEN` header 必填，值 = cookie `XSRF-TOKEN`
- `SUB`/`SUBP`/`PC_TOKEN` 访客 cookie
- **缺任一 → `{"ok": -100}` 被拒**

### 3. cookie 获取（关键坑）

- **纯 requests 访问微博 → 302 重定向到 `passport.weibo.com/visitor/visitor`**（JS 渲染页），
  拿不到 SUB/XSRF-TOKEN 的 Set-Cookie
- `genvisitor` 接口返回 `tid`（`01AfV9z9ahmUwSs2jHggOR2wg...`），但 **SUB cookie 仅由浏览器 JS 流程下发**
- 正确路径：浏览器打开微博 → `ch_page_get_cookies` / DevTools 提取 → 手动传入 `--cookie`

### 4. mid 短码 ↔ 十进制 id 转换（纯本地，无需网络）

微博 URL `weibo.com/<uid>/<bid>` 的 `bid` 是 mid 的 Base62 短码，转换算法已还原：

```
编码: 十进制 mid 从右往左每 7 位一组 → 每组 Base62 → 组序拼接
解码: 短码从右往左每 4 字符一组（Base62 表示 7 位十进制最多 4 字符）
      → 各组解码 → 拼接回十进制字符串
字符集: 0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
```

**金标准验证**（`statuses/show` 真实接口响应确认）：
```
mid=5331124315231860  ↔  mblogid=Rd3GvlX2Q   双向完全匹配 ✅
```

复现脚本 `repro.py` 内置 `mid_to_id()`/`id_to_mid()`，无需 `--id` 参数，
`--mid` 直接本地解码（自动反向编码校验一致性）。

### 5. 响应结构

```json
{
  "ok": 1,
  "total_number": 29,
  "filter_group": [{"param":"flow=0","title":"按热度"},{"param":"flow=1","title":"按时间"}],
  "data": [
    {"id": 5331124483788564, "floor_number": 1, "text": "这瓜保熟吗？...",
     "user": {"id":7911647609, "screen_name":"喜欢短毛小狗_EK", ...},
     "like_count": 0, "comments": [{"text":"假的", ...}]}   // 嵌套回复
  ],
  "max_id": "0_0_...",  // 翻页游标
  "since_id": "..."     // 下拉加载游标
}
```

- 评论树：`data[].text` 顶层评论，`data[].comments[]` 楼中楼嵌套
- 翻页：传 `max_id`（热度流）或 `since_id`（时间流）继续拉取

## 复现脚本

```
# 方法1: 浏览器提取 cookie 后传入，mid 本地自动解码（推荐）
python repro.py --mid Rd3GvlX2Q --uid 7911647609 \
    --cookie "SUB=xxx; SUBP=yyy; PC_TOKEN=zzz; XSRF-TOKEN=ccc"

# 方法2: 显式传十进制 id（跳过解码）
python repro.py --mid Rd3GvlX2Q --uid 7911647609 --id 5331124315231860 \
    --cookie "..."
```

验证结果：`--mid` 纯本地解码 `Rd3GvlX2Q -> 5331124315231860`（反向校验 OK），
29 条评论 + 嵌套回复完整返回，作者回复（"假的"/"是真的"/"确实"）均正确解析。

## 未完成项
- 登录态接口（发评论/点赞）需 `SUB` 登录态 cookie + 更严 XSRF 校验
