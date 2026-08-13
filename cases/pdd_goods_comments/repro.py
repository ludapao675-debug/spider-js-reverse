# -*- coding: utf-8 -*-
"""
拼多多移动端商品评论接口本地复现
接口: POST https://mobile.pinduoduo.com/proxy/api/reviews/{goods_id}/list
加密参数: anti_content（header anti-content + body anti_content 双带）
生成位置: react_goods_comments_*.js 内 webpack 模块 q.g() -> RCF 风控 SDK
         (assets-rcf/*.js, 760KB 混淆, 预签名池 localStorage['anti_pre_sig'])

验证策略: 拼多多 anti_content 为自包含 token（请求不带 Cookie），
先验证"单个 anti_content 是否可跨页重放"，再决定复现深度。
"""
import json
import sys
from curl_cffi import requests as crl

GOODS_ID = "976241093684"
# 从浏览器监听捕获的活体 anti_content（request_id=19764.127, 2026-08-05 17:15）
ANTI_CONTENT = sys.argv[1] if len(sys.argv) > 1 else ""
PDDUID = "6772515013646"
# 浏览器活体 Cookie（与 anti_content 同会话捕获，登录态 PDDAccessToken）
COOKIE = ("api_uid=Ck0sQWpy7ftD0wCATLoUAg==; "
          "_nano_fp=XpmJnpUan5Uxn0Tano_~3Y94UM5nFvdl7Ned~u4A; webp=1; "
          "jrpl=h1U5paAiTKeWWvrTqbjRIkyg64MU98Hv; "
          "njrpl=h1U5paAiTKeWWvrTqbjRIkyg64MU98Hv; "
          "dilx=EyTdULuNd3eV84ph3tTFA; "
          "PDDAccessToken=KAUXXQ4M5SAGCLYRBHLEBSZ5VPOEORJLE6MN56ANOKFGGQZXPQSQ1200e08; "
          "pdd_user_id=6772515013646; "
          "pdd_user_uin=6SBCSWT3HUMGRNK6AAKTKPWKWE_GEXDA; "
          "pdd_vds=gaHWpYTYBTuCvpBqhqDHBWTeYWHrZHuevBHBpcvrZqThDcThfWBDTHuZDHpf")

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://mobile.pinduoduo.com",
    "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
    "cookie": COOKIE,
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
}


def fetch_comments(page: int, anti_content: str):
    """请求评论分页，返回 (status, 数据或错误文本)"""
    url = (f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
           f"?label_id=0&page={page}&size=10&enable_video=1"
           f"&enable_group_review=1&pdduid={PDDUID}")
    headers = dict(HEADERS, **{"anti-content": anti_content})
    body = {"name": "goodsCommentListAxios", "anti_content": anti_content}
    resp = crl.post(url, headers=headers, json=body, impersonate="chrome", timeout=15)
    try:
        data = resp.json()
    except Exception:
        return resp.status_code, resp.text[:200]
    return resp.status_code, data


def main():
    if not ANTI_CONTENT:
        print("用法: python repro.py <anti_content>")
        return
    # 多样本验证：同一 anti_content 请求不同页
    for page in (4, 5, 6):
        status, data = fetch_comments(page, ANTI_CONTENT)
        if isinstance(data, dict) and "data" in data:
            names = [d.get("name", "") for d in data["data"][:3]]
            print(f"page={page} status={status} OK comments={len(data['data'])} "
                  f"first3={names}")
        else:
            print(f"page={page} status={status} FAIL resp={str(data)[:200]}")


if __name__ == "__main__":
    main()
