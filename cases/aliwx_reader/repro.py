# -*- coding: utf-8 -*-
"""
书旗网（www.aliwx.com.cn）小说阅读页正文协议复现
================================================
目标页面: https://www.aliwx.com.cn/reader?bid=<bookId>&cid=<chapterId>

逆向结论
--------
1. 阅读页为 SSR + 数据埋点:
   - <i class="page-data js-dataBookInfo">  书籍信息 JSON
   - <i class="page-data js-dataChapters">  章节数据 JSON（含全部 183 章 contUrlSuffix）
   - <i class="page-data js-dataUserInfo">  用户信息 JSON

2. 正文接口（免费章节）:
   GET https://c13.shuqireader.com/pcapi/chapter/contentfree/<suffix>
   suffix 形如: ?bookId=6813923&chapterId=674175&ut=1754876996&num=1&ver=1&aut=1754876998&sign=...
   - 前缀 freeContUrlPrefix（在 js-dataChapters JSON 中）
   - 后缀 contUrlSuffix（每章独立，sign 由服务端生成，直接拼用即可，无需前端计算）
   - 付费章节走 contentcharge（参数 reqEncryptType=1 加密，暂未逆）

3. 响应解密算法（reader.js 的 _decodeCont，三层）:
   - 第1层 ROT13: 字母 charCode 位移 13 位（等价凯撒 -13，自反）
   - 第2层 Base64: 标准 base64 解码
   - 第3层 UTF-8: 字节解码得到正文 HTML
   - 即: 明文 = UTF8( b64decode( ROT13( 密文 ) ) )

用法
----
    python repro.py                    # 按页面 URL 里的 bid/cid 抓当前章
    python repro.py --bid 6813923 --cid 674175   # 指定章节
    python repro.py --bid 6813923 --all          # 抓全书免费章节
    python repro.py --bid 6813923 --cid 681365 --paid  # 请求付费章节(验证鉴权)
"""
import argparse
import base64
import html
import json
import re
import sys
import time

import requests

ALIWX_READER = "https://www.aliwx.com.cn/reader"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"),
    "Referer": "https://www.aliwx.com.cn/",
}


def rot13(s: str) -> str:
    """ROT13 变换（reader.js 原版逻辑，自反）。"""
    out = []
    for ch in s:
        if ch.isalpha():
            e = ord(ch) // 97          # 大写->0 小写->1
            i = (ord(ch.lower()) - 83) % 26 or 26
            out.append(chr(i + (64 if e == 0 else 96)))
        else:
            out.append(ch)
    return "".join(out)


def decode_cont(t: str) -> str:
    """密文 -> 明文（ROT13 + Base64 + UTF-8）。"""
    t2 = re.sub(r"[^A-Za-z0-9\+\/\=]", "", rot13(t))
    return base64.b64decode(t2).decode("utf-8", errors="ignore")


def get_reader_page(bid: str, cid: str) -> dict:
    """抓取阅读页，提取 js-dataChapters 章节数据。"""
    resp = requests.get(ALIWX_READER, params={"bid": bid, "cid": cid},
                        headers=HEADERS, timeout=15)
    resp.raise_for_status()
    m = re.search(r'class="page-data js-dataChapters"[^>]*>([^<]+)</i>', resp.text)
    if not m:
        raise RuntimeError("未找到 js-dataChapters 数据埋点")
    return json.loads(html.unescape(m.group(1)))


def build_chapter_list(data: dict) -> list:
    """从章节数据 JSON 摊平全部章节。"""
    chapters = []
    for vol in data.get("chapterList", []):
        for c in vol.get("volumeList", []):
            chapters.append({
                "chapterId": c["chapterId"],
                "chapterName": c["chapterName"],
                "isFreeRead": c.get("isFreeRead"),
                "isBuy": c.get("isBuy"),
                "contUrlSuffix": c.get("contUrlSuffix", ""),
            })
    return chapters


def fetch_chapter(pref: str, suffix: str) -> dict:
    """请求正文接口。pref=chargeContUrlPrefix 或 freeContUrlPrefix, suffix=contUrlSuffix。
    返回原始响应 dict；调用方负责解密与鉴权判断。"""
    url = pref + suffix
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def decode_resp(d: dict) -> str:
    """从响应中解出明文正文。"""
    if d.get("state") != "200":
        raise RuntimeError(f"接口异常: {d.get('state')} {d.get('message')}")
    return decode_cont(d["ChapterContent"])


def main() -> None:
    parser = argparse.ArgumentParser(description="书旗网阅读正文复现")
    parser.add_argument("--bid", default="6813923")
    parser.add_argument("--cid", default="674174")
    parser.add_argument("--all", action="store_true", help="抓全书免费章节")
    parser.add_argument("--paid", action="store_true",
                        help="请求付费章节(加密参数由服务端下发,无需本地加密;未购买会返回403)")
    args = parser.parse_args()

    data = get_reader_page(args.bid, args.cid)
    chapters = build_chapter_list(data)
    print(f"书名: {data['bookName']}  作者: {data['authorName']}  章节数: {len(chapters)}")

    if args.all:
        pref = data["freeContUrlPrefix"]
        for i, c in enumerate(chapters, 1):
            if not c["isFreeRead"]:
                continue
            d = fetch_chapter(pref, c["contUrlSuffix"])
            text = decode_resp(d)
            with open(f"{args.bid}_{c['chapterId']}.txt", "w", encoding="utf-8") as f:
                f.write(text)
            print(f"[{i}/{len(chapters)}] {c['chapterName']} {len(text)}字")
            time.sleep(0.4)
        return

    target = next((c for c in chapters if str(c["chapterId"]) == str(args.cid)), None)
    if not target:
        print(f"未找到章节 cid={args.cid}", file=sys.stderr)
        sys.exit(1)

    if args.paid or not target["isFreeRead"]:
        # 付费章节:加密参数(bookId/chapterId/user_id)全部由服务端随 contUrlSuffix 下发,
        # 前端不参与生成,直接拼 chargeContUrlPrefix 请求即可。
        # 未购买/未登录时返回 403 + failReason,正文需带已购账号 Cookie。
        pref = data["chargeContUrlPrefix"]
        print(f"== {target['chapterName']} (付费章节, charge 接口) ==")
        d = fetch_chapter(pref, target["contUrlSuffix"])
        print(f"state={d.get('state')} message={d.get('message')} failReason={d.get('failReason')}")
        if d.get("state") == "200":
            print(decode_resp(d)[:500])
        return

    pref = data["freeContUrlPrefix"]
    d = fetch_chapter(pref, target["contUrlSuffix"])
    text = decode_resp(d)
    print(f"== {target['chapterName']} ==")
    print(text[:500])


if __name__ == "__main__":
    main()
