# -*- coding: utf-8 -*-
"""
本地遥测重放（t.gif）：验证纯本地构造的遥测载荷是否被服务端接受

载荷结构（已离线解析 9 条活体样本）：
- 明文 URL-encoded k=v，无加密无签名
- log_id = 13位毫秒时间戳 + 16位 base36 随机（源码 r+(0,h.A)(16)）
- dcf    = pdd_vds + "." + 递增计数 + "." + 随机数
- cookie_fp/storage_fp = _nano_fp cookie 值
- op=impr 为曝光埋点

风控预算：本次仅发 1 条。
"""
import json
import os
import random
import string
import sys
import time
import urllib.request

from curl_cffi import requests as crl

BACKEND = "http://127.0.0.1:27183"
TAB_ID = "8D44B9776336055378BCC173BEA94A23"
HERE = os.path.dirname(os.path.abspath(__file__))
B36 = string.digits + string.ascii_lowercase


def api_post(path, payload, timeout=60):
    req = urllib.request.Request(
        BACKEND + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def b36(n):
    return "".join(random.choice(B36) for _ in range(n))


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    # 1) 活体会话数据：cookie + 页面上下文 + VerifyAuthToken
    rc = api_post("/api/browser/page/cookies", {"tab_id": TAB_ID}, timeout=20)
    cookies = {c["name"]: c["value"] for c in (rc.get("cookies") or [])}
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    jrpl_cookie = "; ".join(f"{k}={v}" for k, v in cookies.items()
                            if k in ("api_uid", "jrpl"))  # t.gif 实际只带 ~139B cookie

    r = api_post("/api/browser/page/run-js", {
        "tab_id": TAB_ID,
        "code": ("(() => ({page_id: new URLSearchParams(location.search).get('page_id') || '',"
                 "refer_page_name: new URLSearchParams(location.search).get('refer_page_name') || '',"
                 "refer_page_id: new URLSearchParams(location.search).get('refer_page_id') || '',"
                 "is_back: new URLSearchParams(location.search).get('is_back') || '',"
                 "vat: localStorage.getItem('VerifyAuthToken') || '',"
                 "sw: screen.width, sh: screen.height, dpr: window.devicePixelRatio}))()"),
        "return_mode": "json"}, timeout=20)
    ctx = r.get("result") or {}
    print(f"ctx: page_id={ctx.get('page_id', '')[:30]}... vat={bool(ctx.get('vat'))}")

    # 2) 本地构造 op=impr 载荷（对照活体 555 字节小样本结构）
    now = int(time.time() * 1000)
    nano_fp = cookies.get("_nano_fp", "")
    pdd_vds = cookies.get("pdd_vds", "")
    dcf = f"{pdd_vds}.{random.randint(20, 30)}.{random.randint(100000000, 3999999999)}"
    from urllib.parse import urlencode
    payload = urlencode({
        "goods_id": "976241093684",
        "page_sn": "10058",
        "page_id": ctx.get("page_id", ""),
        "refer_page_name": ctx.get("refer_page_name", ""),
        "refer_page_id": ctx.get("refer_page_id", ""),
        "refer_page_sn": "10390",
        "is_back": ctx.get("is_back", "1"),
        "op": "impr",
        "time": str(now),
        "log_id": f"{now}{b36(16)}",
        "user_id": cookies.get("pdd_user_id", ""),
        "uin": cookies.get("pdd_user_uin", ""),
        "app_id": "",
        "screen_width": str(ctx.get("sw", 2560)),
        "screen_height": str(ctx.get("sh", 1600)),
        "dpr": str(ctx.get("dpr", 1)),
        "app_version": "",
        "platform": "unknown",
        "cookie_fp": nano_fp,
        "storage_fp": nano_fp,
        "dcf": dcf,
    })
    print(f"本地载荷 {len(payload)}B（活体对照 555B）")

    # 3) 本地发送（限 1 条）
    headers = {
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://mobile.pinduoduo.com",
        "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id=976241093684",
        "cookie": jrpl_cookie,
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
    }
    if ctx.get("vat"):
        headers["verifyauthtoken"] = ctx["vat"]
    resp = crl.post("https://th.pinduoduo.com/t.gif", headers=headers,
                    data=payload, impersonate="chrome", timeout=15)
    print(f"服务端响应: status={resp.status_code} "
          f"body={resp.text[:100]!r} http={getattr(resp, 'http_version', '?')}")
    if resp.status_code == 200:
        print("★ 本地遥测载荷被接受 → t.gif 流可纯本地伪造")
    else:
        print("被拒 → 遥测端点另有校验")


if __name__ == "__main__":
    main()
