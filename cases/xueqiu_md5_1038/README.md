# 雪球搜索 `md5__1038`

## 状态

| 项 | 状态 |
|---|---|
| 算法 | ✅ 已封死 |
| 离线生成 | ✅ `scratch/.../offline_md5_1038.py` |
| HTTP 新闻 list | ✅ |
| L2 纯本地翻页 | ✅ `local_fetch_news.py` |
| **L3 无浏览器冷启动** | ✅ `l3_cold_fetch_news.py` |

## 算法摘要

完整文档：[`../../scratch/xueqiu_md5_1038_20260718/README.md`](../../scratch/xueqiu_md5_1038_20260718/README.md)  
本地复现：[`../../scratch/xueqiu_md5_1038_20260718/LOCAL_REPRO.md`](../../scratch/xueqiu_md5_1038_20260718/LOCAL_REPRO.md)  
协议细节：[`../../scratch/xueqiu_md5_1038_20260718/PROTOCOL.md`](../../scratch/xueqiu_md5_1038_20260718/PROTOCOL.md)

```
enc_in → encodeURIComponent → SHA-256 → [14:30]
  → B(ww=8)=h1, B(ww=3)=h2
kt = h1|h2|dy|ts|waf|ts0|deviceId
token = prefix + "-" + lz6bit(kt)
```

## L3 冷启动（推荐）

```text
python scratch/xueqiu_md5_1038_20260718/l3_cold_fetch_news.py --q 纳斯达克 --pages 3
```

1. `GET /` → `acw_tc` + 挑战页 `renderData._waf_bd8ce2ce37`（**不必跑挑战 JS**）
2. `GET /k?q=...` → 访客 `xq_a_token` 等
3. 离线 `md5__1038` + `GET status.json` → `list`

## 产物路径

`scratch/xueqiu_md5_1038_20260718/`

## 工具问题与加固

[`../../scratch/xueqiu_md5_1038_20260718/TOOLING_REVIEW.md`](../../scratch/xueqiu_md5_1038_20260718/TOOLING_REVIEW.md)

## 可选未做

- `J()` 环境位逐位复刻（常量 `dy=336070664` 已够用）
- 阿里云外部 gzip 挑战脚本本体（拉搜索新闻不需要）
