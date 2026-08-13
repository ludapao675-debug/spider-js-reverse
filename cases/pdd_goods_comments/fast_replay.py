# -*- coding: utf-8 -*-
"""
秒级重放验证：从 __pdd_cap 暂存读取浏览器刚发出的 reviews 请求，
立刻用相同 anti_content 重放不同页，测定 anti_content 的真实约束（TTL/请求绑定）。
用法: python fast_replay.py <captured_json_file>
"""
import json
import sys
from curl_cffi import requests as crl

COOKIE = ("api_uid=Ck0sQWpy7ftD0wCATLoUAg==; "
          "_nano_fp=XpmJnpUan5Uxn0Tano_~3Y94UM5nFvdl7Ned~u4A; webp=1; "
          "jrpl=h1U5paAiTKeWWvrTqbjRIkyg64MU98Hv; "
          "njrpl=h1U5paAiTKeWWvrTqbjRIkyg64MU98Hv; "
          "dilx=EyTdULuNd3eV84ph3tTFA; "
          "PDDAccessToken=KAUXXQ4M5SAGCLYRBHLEBSZ5VPOEORJLE6MN56ANOKFGGQZXPQSQ1200e08; "
          "pdd_user_id=6772515013646; "
          "pdd_user_uin=6SBCSWT3HUMGRNK6AAKTKPWKWE_GEXDA; "
          "pdd_vds=gaHWpYTYBTuCvpBqhqDHBWTeYWHrZHuevBHBpcvrZqThDcThfWBDTHuZDHpf")


def replay(url, anti_content, body_name="goodsCommentListAxios"):
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://mobile.pinduoduo.com",
        "referer": "https://mobile.pinduoduo.com/goods_comments.html?goods_id=976241093684",
        "cookie": COOKIE,
        "anti-content": anti_content,
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
    }
    body = {"name": body_name, "anti_content": anti_content}
    resp = crl.post(url, headers=headers, json=body, impersonate="chrome", timeout=15)
    try:
        d = resp.json()
    except Exception:
        return resp.status_code, resp.text[:150]
    if isinstance(d, dict) and "data" in d and isinstance(d["data"], list):
        return resp.status_code, f"OK n={len(d['data'])}"
    return resp.status_code, str(d)[:150]


def main():
    cap = json.load(open(sys.argv[1], encoding="utf-8"))
    ac = cap["headers"].get("anti-content", "")
    print(f"captured url: {cap['url'][:120]}")
    print(f"anti_content prefix: {ac[:30]}... len={len(ac)}")
    # 实验 1：原样重放同一 URL（含相同 page）→ 判断是否一次性 token
    s1, r1 = replay(cap["url"], ac)
    print(f"[同URL重放] status={s1} {r1}")
    # 实验 2：换 page 参数重放 → 判断是否绑定 URL
    import re
    alt_url = re.sub(r"page=\d+", "page=7", cap["url"])
    s2, r2 = replay(alt_url, ac)
    print(f"[换page重放] status={s2} {r2}")


if __name__ == "__main__":
    main()
