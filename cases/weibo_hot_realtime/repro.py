# -*- coding: utf-8 -*-
"""
微博实时热搜（weibo.com/a/hot/realtime）接口复现
=================================================
目标页面: https://weibo.com/a/hot/realtime  （微博实时热点）

逆向结论
--------
1. 页面为老版 SSR：热榜数据直接内联 HTML，无独立正文接口。
2. 动态数据接口零加密（无签名/token/加密参数），仅要求合法 Referer：
   - GET https://weibo.com/ajax/side/hotSearch        实时热搜 50 条
   - GET https://weibo.com/ajax/statuses/hot_band      热搜榜 50 条（含热搜进榜/趋势）
   - GET https://weibo.com/ajax/statuses/topiclist?category=N  分类热搜（s.weibo 版）
3. 校验机制 = Referer 反爬（非加密）：
   - 无 Referer → 403 Forbidden
   - 带 Referer: https://weibo.com/a/hot/realtime → 200 完整 JSON
   - 无需 cookie / 无需访客 token（裸请求带 Referer 即可）
4. 访客 cookie（SUB/SUBP）由 passport.weibo.com 访客流程生成（genvisitor→visitor），
   对热榜接口非必需；仅在登录态接口（关注/点赞/评论）才需要。

用法
----
    python repro.py hotsearch      # 实时热搜
    python repro.py hotband        # 热搜榜
    python repro.py --top 5        # 只看前 N 条
"""
import argparse
import json
import sys

import requests

HOTSEARCH_URL = "https://weibo.com/ajax/side/hotSearch"
HOTBAND_URL = "https://weibo.com/ajax/statuses/hot_band"
REFERER = "https://weibo.com/a/hot/realtime"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"),
    "Referer": REFERER,
}


def fetch_hotsearch(top: int) -> list:
    r = requests.get(HOTSEARCH_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    d = r.json()
    rt = d["data"]["realtime"]
    rows = []
    for item in rt:
        rank = item.get("realpos")
        rows.append({
            "rank": rank if rank is not None else 0,
            "note": item.get("note"),
            "num": item.get("num"),
            "word": item.get("word"),
            "word_scheme": item.get("word_scheme", ""),
            "flag": item.get("flag"),
            "label": item.get("label_name", ""),
        })
    return rows[:top] if top else rows


def fetch_hotband(top: int) -> list:
    r = requests.get(HOTBAND_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    d = r.json()
    bl = d["data"]["band_list"]
    rows = []
    for item in bl:
        rank = item.get("realpos") or item.get("position")
        rows.append({
            "rank": rank if rank is not None else 0,
            "note": item.get("note"),
            "num": item.get("num"),
            "trend": item.get("trend", ""),   # up/down/flat
            "icon": item.get("small_icon_desc", ""),
        })
    return rows[:top] if top else rows


def main() -> None:
    parser = argparse.ArgumentParser(description="微博实时热搜复现")
    parser.add_argument("cmd", choices=["hotsearch", "hotband"], default="hotsearch", nargs="?")
    parser.add_argument("--top", type=int, default=0, help="只看前 N 条")
    args = parser.parse_args()

    if args.cmd == "hotsearch":
        rows = fetch_hotsearch(args.top)
        for r in rows:
            print(f"#{r['rank']:<3} {r['note']}  (热度 {r['num']})")
    else:
        rows = fetch_hotband(args.top)
        for r in rows:
            trend = {"up": "↑", "down": "↓", "flat": "—"}.get(r["trend"], r["trend"])
            print(f"#{r['rank']:<3} {r['note']}  (热度 {r['num']}) {trend}")


if __name__ == "__main__":
    main()
