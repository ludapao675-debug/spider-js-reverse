# -*- coding: utf-8 -*-
"""
微博单条微博评论接口复现
========================
目标页面: https://weibo.com/7911647609/Rd3GvlX2Q  （单条微博正文）

逆向结论
--------
1. 评论接口: GET https://weibo.com/ajax/statuses/buildComments
   参数全明文，无签名/加密:
     id           微博 mid 的十进制 id（由 URL mid 短码转换，页面 SSR 内联）
     uid          博主 uid
     count        每页条数
     is_reload    1 首屏 / 0 翻页
     fetch_level  0 全部 / 1 只看楼中楼
     flow         0 按热度 / 1 按时间（filter_group 由响应返回）
     is_mix / is_show_bulletin / locale  固定值

2. 校验机制 = SUB cookie + XSRF-TOKEN 双保险（非加密）:
   - X-XSRF-TOKEN header 必填，值 = cookie XSRF-TOKEN（访客流程自动下发）
   - 缺失任一 → {"ok": -100, "msg": "..."} 被拒
   - SUB/SUBP/PC_TOKEN 为访客 cookie，由 passport.weibo.com 访客流程 Set-Cookie

3. mid 短码 → 十进制 id:
   URL /weibo.com/<uid>/<mid> 中 mid 是 Base62 短码(Rd3GvlX2Q)，
   页面 SSR 的 __INITIAL_STATE__ 或 /ajax/statuses/show?id=<mid> 响应返回十进制 id。

用法
----
    python repro.py --mid Rd3GvlX2Q --uid 7911647609 --id 5331124315231860
    python repro.py --mid Rd3GvlX2Q --uid 7911647609 --id 5331124315231860 --flow 1 --count 50
"""
import argparse
import json
import re
import sys

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"),
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}

# 访客 cookie（可由 requests.Session 访问首页自动获取）
VISITOR_COOKIES = {
    "SUB": None,
    "SUBP": None,
    "PC_TOKEN": None,
    "XSRF-TOKEN": None,
}


def parse_cookies(cookie_str: str) -> dict:
    """解析 'SUB=xxx; XSRF-TOKEN=yyy' 格式 cookie 串为 dict。"""
    out = {}
    for pair in cookie_str.split(";"):
        if "=" in pair:
            k, v = pair.strip().split("=", 1)
            out[k] = v
    return out


def fetch_visitor() -> dict:
    """尝试自动获取访客 cookie。
    注意: 纯 requests 访问微博会被防爬重定向到 visitor/visitor(JS渲染),
    通常拿不到 SUB/XSRF-TOKEN Set-Cookie。推荐用浏览器打开一次微博后
    从 DevTools / ch_page_get_cookies 提取 cookie 手动传入 --cookie。
    """
    s = requests.Session()
    h = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://weibo.com/"}
    s.get("https://weibo.com/a/hot/realtime", headers=h, timeout=20, allow_redirects=True)
    c = s.cookies.get_dict()
    return {
        "SUB": c.get("SUB", ""),
        "SUBP": c.get("SUBP", ""),
        "PC_TOKEN": c.get("PC_TOKEN", ""),
        "XSRF-TOKEN": c.get("XSRF-TOKEN", ""),
    }


# 微博 mid 短码 <-> 十进制 id 转换（Base62，每 7 位一组）
# 已验证金标准: mid=5331124315231860 <-> mblogid=Rd3GvlX2Q（statuses/show 真实响应确认）
_B62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_B62_BASE = 62
_MID_GROUP = 7


def _b62_encode(num: int) -> str:
    if num == 0:
        return "0"
    out = ""
    while num > 0:
        out = _B62_CHARS[num % _B62_BASE] + out
        num //= _B62_BASE
    return out


def _b62_decode(s: str) -> int:
    n = 0
    for ch in s:
        n = n * _B62_BASE + _B62_CHARS.index(ch)
    return n


def mid_to_id(uid: str, mid: str, cookies: dict = None, referer: str = "") -> str:
    """URL mid 短码 -> 微博十进制 id（纯本地 Base62 解码，无需网络）。
    算法: 短码从右往左每 4 字符一组(Base62 表示 7 位十进制最多 4 字符),
    各组解码后按组序拼接成十进制字符串。
    """
    s = mid
    parts = []
    while len(s) > 4:
        parts.append(s[-4:])
        s = s[:-4]
    parts.append(s)
    nums = [_b62_decode(p) for p in reversed(parts)]
    return str(int("".join(str(n) for n in nums)))


def id_to_mid(id_str: str) -> str:
    """微博十进制 id -> URL mid 短码（纯本地 Base62 编码，供校验/调试）。"""
    s = str(id_str)
    parts = []
    while len(s) > _MID_GROUP:
        parts.append(s[-_MID_GROUP:])
        s = s[:-_MID_GROUP]
    parts.append(s)
    return "".join(_b62_encode(int(p)) for p in reversed(parts))


def fetch_comments(uid: str, cid: str, cookies: dict, referer: str,
                   count: int = 10, flow: int = 0, reload: bool = True) -> dict:
    """请求评论接口并返回完整响应。"""
    headers = {**HEADERS, "Referer": referer}
    xsrf = cookies.get("XSRF-TOKEN")
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
    params = {
        "is_reload": 1 if reload else 0,
        "id": cid,
        "is_show_bulletin": 2,
        "is_mix": 0,
        "count": count,
        "uid": uid,
        "fetch_level": 0,
        "locale": "zh-CN",
    }
    if flow:
        params["flow"] = flow
    r = requests.get("https://weibo.com/ajax/statuses/buildComments",
                     params=params, headers=headers, cookies=cookies, timeout=15)
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="微博评论接口复现")
    parser.add_argument("--mid", default="Rd3GvlX2Q", help="微博 URL mid 短码")
    parser.add_argument("--uid", default="7911647609", help="博主 uid")
    parser.add_argument("--id", default="", help="十进制微博 id（自动获取）")
    parser.add_argument("--count", type=int, default=10, help="每页条数")
    parser.add_argument("--flow", type=int, default=0, help="0热度 1时间")
    parser.add_argument("--page", type=int, default=1, help="页码(对应 max_id 分页)")
    parser.add_argument("--cookie", default="",
                        help="微博 cookie 串(如 'SUB=xx; XSRF-TOKEN=yy')，"
                             "从浏览器 ch_page_get_cookies / DevTools 提取")
    args = parser.parse_args()

    # 1) 获取访客 cookie（SUB/XSRF-TOKEN）
    cookies = parse_cookies(args.cookie) if args.cookie else fetch_visitor()
    if not cookies["SUB"] or not cookies["XSRF-TOKEN"]:
        print("[-] 访客 cookie 获取失败（可能需要人工访问一次微博）", file=sys.stderr)
        sys.exit(1)
    print(f"[+] cookie: SUB={cookies['SUB'][:20]}... XSRF={cookies['XSRF-TOKEN'][:12]}...")

    referer = f"https://weibo.com/{args.uid}/{args.mid}"
    # 2) 拿十进制 id（纯本地 Base62 解码）
    if args.id:
        cid = str(args.id)
    else:
        cid = mid_to_id(args.uid, args.mid)
    if not cid:
        print("[-] 无法解析微博 id", file=sys.stderr)
        sys.exit(1)
    back = id_to_mid(cid)
    print(f"[+] mid={args.mid} -> id={cid} (反向编码校验={back}, {'OK' if back == args.mid else 'MISMATCH'})")

    # 3) 拉评论
    d = fetch_comments(args.uid, cid, cookies, referer, args.count, args.flow)
    if d.get("ok") != 1:
        print(f"[-] 接口失败: ok={d.get('ok')} msg={d.get('msg', d.get('error', ''))}")
        sys.exit(1)
    print(f"[+] total_number={d.get('total_number')} 本页={len(d.get('data', []))}")
    for c in d.get("data", []):
        user = c.get("user", {})
        print(f"  [{c.get('floor_number')}] {c.get('text', '')[:50]} "
              f"@ {user.get('screen_name', '?')} +{c.get('like_count', 0)}")
        for sub in c.get("comments", [])[:2]:
            su = sub.get("user", {})
            print(f"    └─ {sub.get('text', '')[:40]} @ {su.get('screen_name', '?')}")


if __name__ == "__main__":
    main()
