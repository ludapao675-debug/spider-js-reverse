# -*- coding: utf-8 -*-
"""
协议栈定界实验（风控预算 1 次）：
- 变量：impersonate='chrome110'（可能降级 HTTP/1.1 或不同 H2 指纹）
- 其余与 verify_token_replay.py 相同（sdenv 离线 token + 基础头）
用于区分"HTTP/2 帧指纹"还是"一切非真 Chrome 协议栈"被拦。
"""
import json
import os
import re
import sys
import urllib.request

from curl_cffi import requests as crl

BACKEND = "http://127.0.0.1:27183"
TAB_ID = "8D44B9776336055378BCC173BEA94A23"
GOODS_ID = "976241093684"
PDDUID = "6772515013646"
HERE = os.path.dirname(os.path.abspath(__file__))


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
    src = open(os.path.join(HERE, "local_repro_experiment.py"), encoding="utf-8").read()
    bundle_js = re.search(r'BUNDLE_JS = r"""(.*?)"""', src, re.S).group(1)
    rb = api_post("/api/browser/page/run-js", {
        "tab_id": TAB_ID, "code": bundle_js,
        "return_mode": "json", "await_promise": True, "timeout_sec": 60}, timeout=90)
    res = rb.get("result")
    if not isinstance(res, dict) and rb.get("result_stashed"):
        # 大结果落盘回退（run_js_dumps）
        fn = os.path.basename(str(rb.get("result_file") or ""))
        rr = json.loads(urllib.request.urlopen(
            f"{BACKEND}/api/browser/page/run-js/result?file={fn}", timeout=30).read())
        res = rr.get("data") or {}
    bundle = ((res or {}).get("bundle") or "")
    if not bundle:
        print(f"bundle 构建失败: {str(res)[:200]}")
        sys.exit(1)
    rc = api_post("/api/browser/page/cookies", {"tab_id": TAB_ID}, timeout=20)
    cookie = "; ".join(f"{c['name']}={c['value']}" for c in (rc.get("cookies") or []))
    d = api_post("/api/sdenv/run-code", {
        "js_code": bundle,
        "url": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
        "cookies": cookie, "super_env": True, "timeout": 60}, timeout=180)
    ck = str(d.get("cookies") or "")
    token = ""
    for part in ck.split(";"):
        kv = part.strip()
        if kv.startswith("__sdenv_ac="):
            token = kv[len("__sdenv_ac="):]
            break
    print(f"sdenv token: {token[:24]}... len={len(token)}")
    if not token.startswith("0as"):
        print("生成失败")
        sys.exit(2)

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://mobile.pinduoduo.com",
        "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
        "cookie": cookie,
        "anti-content": token,
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"),
    }
    # impersonate=chrome110：不同的 TLS/H2 指纹档位，用于协议栈敏感性定界
    resp = crl.post(
        f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
        f"?label_id=0&page=22&size=10&enable_video=1&enable_group_review=1&pdduid={PDDUID}",
        headers=headers, json={"name": "goodsCommentListAxios", "anti_content": token},
        impersonate="chrome110", timeout=15)
    print(f"http_version: {getattr(resp, 'http_version', '?')}")
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:200]}
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        print(f"★ chrome110 指纹通过 n={len(body['data'])} → 指纹档位敏感，可遍历 impersonate 找可用档")
    else:
        print(f"chrome110 仍拒: {str(body)[:120]}")
        print("→ 非特定 H2 档位问题，一切非真 Chrome 协议栈均被拦（或存在带外信号）")


if __name__ == "__main__":
    main()
