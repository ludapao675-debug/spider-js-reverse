# -*- coding: utf-8 -*-
"""
判据实验：验证 54001 的真正根因是否为缺失 verifyauthtoken 头 + is_back=1 参数

背景：
- 页面真实请求（request_id=19764.593）携带 verifyauthtoken 头，
  值来自 localStorage.VerifyAuthToken（人工过 psnl_verification 后写入）
- 页面请求 URL 带 is_back=1；此前所有本地重放均缺这两项
- 若本实验本地通过 → 纯本地复现成立（sdenv token + VerifyAuthToken）

风控预算：本地 1 次请求；失败不做浏览器对照（离线 token 已被 C2 证实可用，
若仍 54001 则定界为协议栈层）。
"""
import json
import os
import sys
import urllib.request

from curl_cffi import requests as crl

BACKEND = "http://127.0.0.1:27183"
TAB_ID = "8D44B9776336055378BCC173BEA94A23"
GOODS_ID = "976241093684"
PDDUID = "6772515013646"


def api_post(path, payload, timeout=180):
    req = urllib.request.Request(
        BACKEND + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))

    # 1) 读取 VerifyAuthToken（localStorage，非 HttpOnly，可读）
    r = api_post("/api/browser/page/run-js", {
        "tab_id": TAB_ID,
        "code": "(() => ({vat: localStorage.getItem('VerifyAuthToken') || ''}))()",
        "return_mode": "json"}, timeout=20)
    vat = ((r.get("result") or {}).get("vat") or "").strip()
    print(f"[1] VerifyAuthToken: {vat[:20]}... len={len(vat)}")
    if not vat:
        print("    缺失，无法实验")
        sys.exit(1)

    # 2) 复用 local_repro_experiment 的 bundle 构建逻辑生成离线 token
    import re
    src = open(os.path.join(here, "local_repro_experiment.py"), encoding="utf-8").read()
    bundle_js = re.search(r'BUNDLE_JS = r"""(.*?)"""', src, re.S).group(1)
    rb = api_post("/api/browser/page/run-js", {
        "tab_id": TAB_ID, "code": bundle_js,
        "return_mode": "json", "await_promise": True, "timeout_sec": 60}, timeout=90)
    res = rb.get("result")
    if not isinstance(res, dict) and rb.get("result_stashed"):
        fn = os.path.basename(str(rb.get("result_file") or ""))
        rr = json.loads(urllib.request.urlopen(
            f"{BACKEND}/api/browser/page/run-js/result?file={fn}", timeout=30).read())
        res = rr.get("data") or {}
    bundle = (res or {}).get("bundle", "")
    if not bundle:
        print(f"[2] bundle 构建失败: {str(res)[:200]}")
        sys.exit(1)
    print(f"[2] bundle 构建完成 {len(bundle)//1024}KB")

    rc = api_post("/api/browser/page/cookies",
                  {"tab_id": TAB_ID}, timeout=20)
    cookie = "; ".join(f"{c['name']}={c['value']}" for c in (rc.get("cookies") or []))
    d = api_post("/api/sdenv/run-code", {
        "js_code": bundle,
        "url": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
        "cookies": cookie, "super_env": True, "timeout": 60,
    }, timeout=180)
    ck = str(d.get("cookies") or "")
    token = ""
    for part in ck.split(";"):
        kv = part.strip()
        if kv.startswith("__sdenv_ac="):
            token = kv[len("__sdenv_ac="):]
            break
    print(f"[3] sdenv token: {token[:30]}... len={len(token)}")
    if not token.startswith("0as"):
        print(f"    生成失败: {str(d.get('output'))[-300:]}")
        sys.exit(2)

    # 3) 本地重放：带 verifyauthtoken 头 + is_back=1 参数（限 1 次）
    url = (f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
           f"?label_id=0&page=8&size=10&enable_video=1"
           f"&enable_group_review=1&pdduid={PDDUID}&is_back=1")
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://mobile.pinduoduo.com",
        "referer": (f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}"
                    "&is_back=1"),
        "cookie": cookie,
        "anti-content": token,
        "verifyauthtoken": vat,   # ★ 关键变量：人工验证凭证
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
        "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "accept-language": "zh-CN,zh;q=0.9",
    }
    resp = crl.post(url, headers=headers,
                    json={"name": "goodsCommentListAxios", "anti_content": token},
                    impersonate="chrome", timeout=15)
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:200]}
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        print(f"[4] ★★★ 本地通过！status=200 n={len(body['data'])} "
              f"first={body['data'][0].get('name') if body['data'] else ''}")
        print("    结论：54001 根因 = 缺失 verifyauthtoken 头/is_back 参数，"
              "纯本地复现成立")
    else:
        print(f"[4] 本地仍被拒 status={resp.status_code} resp={str(body)[:150]}")
        print("    结论：排除头/参数变量，阻碍定界到 HTTP/2/TLS 协议栈层")


if __name__ == "__main__":
    main()
