# -*- coding: utf-8 -*-
"""54001 通道定界：同公网 IP + 同浏览器新鲜 token，浏览器内 vs curl_cffi。

预算：浏览器 reviews ×1（对照）+ 本地 reviews ×1（判据）。
用法：先确保 MCP/后端已 attach 目标 tab，再：
  python dissect_channel_54001.py --tab_id <TAB> --goods_id <ID> --pdduid <UID>
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

from curl_cffi import requests as creq

BACKEND = "http://127.0.0.1:27183"


def run_js(code: str, tab_id: str, timeout: int = 30):
    payload = json.dumps(
        {
            "tab_id": tab_id,
            "code": code,
            "return_mode": "json",
            "await_promise": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        BACKEND + "/api/browser/page/run-js",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or data)
    r = data.get("result")
    if isinstance(r, dict) and r.get("__json_parse_error__"):
        raise RuntimeError(r)
    return r


def get_cookies(tab_id: str) -> str:
    payload = json.dumps({"tab_id": tab_id}).encode("utf-8")
    req = urllib.request.Request(
        BACKEND + "/api/browser/page/cookies",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data)
    return data.get("cookie_str") or ""


def public_ip_local(impersonate: str) -> str:
    r = creq.get("https://api.ipify.org?format=json", impersonate=impersonate, timeout=15)
    return r.json().get("ip", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab_id", required=True)
    ap.add_argument("--goods_id", required=True)
    ap.add_argument("--pdduid", required=True)
    ap.add_argument("--page", type=int, default=3)
    ap.add_argument("--impersonate", default="chrome")
    args = ap.parse_args()

    evidence = {"ts": int(time.time() * 1000), "goods_id": args.goods_id, "page": args.page}

    # 0) IP
    evidence["ip_local"] = public_ip_local(args.impersonate)
    ip_browser = run_js(
        "(async()=>{const r=await fetch('https://api.ipify.org?format=json');return await r.json()})()",
        args.tab_id,
    )
    evidence["ip_browser"] = (ip_browser or {}).get("ip") if isinstance(ip_browser, dict) else ip_browser
    evidence["ip_same"] = evidence["ip_local"] == evidence["ip_browser"]
    print(f"[IP] browser={evidence['ip_browser']} local={evidence['ip_local']} same={evidence['ip_same']}")

    # 1) 浏览器生成 token（不发业务）
    tok = run_js(
        "(async()=>{const ac=await window.__pdd_ac_mod.g();return{ac,len:String(ac).length,prefix:String(ac).slice(0,8)}})()",
        args.tab_id,
    )
    ac = tok["ac"]
    evidence["ac_prefix"] = tok.get("prefix")
    evidence["ac_len"] = tok.get("len")
    print(f"[TOK] {evidence['ac_prefix']}... len={evidence['ac_len']}")

    cookie_str = get_cookies(args.tab_id)
    evidence["cookie_names"] = [p.split("=", 1)[0] for p in cookie_str.split("; ") if p]
    print(f"[CK] n={len(evidence['cookie_names'])} {evidence['cookie_names']}")

    url = (
        f"https://mobile.pinduoduo.com/proxy/api/reviews/{args.goods_id}/list"
        f"?label_id=0&page={args.page}&size=10&enable_video=1&enable_group_review=1"
        f"&pdduid={args.pdduid}&is_back=1"
    )

    # 2) 对照：同 token 浏览器内 fetch（真 Chrome/Edge 栈）
    ctrl_js = (
        "(()=>{const $args="
        + json.dumps({"url": url, "ac": ac}, ensure_ascii=False)
        + "; return (async()=>{"
        "const resp=await fetch($args.url,{method:'POST',"
        "headers:{'accept':'application/json, text/plain, */*',"
        "'content-type':'application/json;charset=UTF-8','anti-content':$args.ac},"
        "body:JSON.stringify({name:'goodsCommentListAxios',anti_content:$args.ac})});"
        "const d=await resp.json();"
        "return {status:resp.status,n:Array.isArray(d.data)?d.data.length:0,"
        "error_code:d.error_code||null,verify:!!d.verify_auth_token};"
        "})();})()"
    )
    t0 = time.time()
    ctrl = run_js(ctrl_js, args.tab_id, timeout=30)
    evidence["browser_ctrl"] = {"elapsed": round(time.time() - t0, 3), **(ctrl if isinstance(ctrl, dict) else {"raw": ctrl})}
    print(f"[CTRL browser] {evidence['browser_ctrl']}")

    if not (isinstance(ctrl, dict) and ctrl.get("n", 0) > 0):
        print("[STOP] 浏览器对照未通过，不消耗本地预算")
        Path = __import__("pathlib").Path
        Path("dissect_channel_evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    time.sleep(2)

    # 3) 判据：同 token + 同 Cookie + 同 IP，curl_cffi 发
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
    )
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://mobile.pinduoduo.com",
        "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={args.goods_id}",
        "cookie": cookie_str,
        "anti-content": ac,
        "user-agent": ua,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }
    t1 = time.time()
    resp = creq.post(
        url,
        headers=headers,
        json={"name": "goodsCommentListAxios", "anti_content": ac},
        impersonate=args.impersonate,
        timeout=20,
    )
    try:
        d = resp.json()
    except Exception:
        d = {"_text": resp.text[:200]}
    evidence["local_probe"] = {
        "elapsed": round(time.time() - t1, 3),
        "impersonate": args.impersonate,
        "http_status": resp.status_code,
        "error_code": d.get("error_code") if isinstance(d, dict) else None,
        "verify": bool(isinstance(d, dict) and d.get("verify_auth_token")),
        "n": len(d["data"]) if isinstance(d, dict) and isinstance(d.get("data"), list) else 0,
        "head": str(d)[:180],
    }
    print(f"[PROBE local] {evidence['local_probe']}")

    # 定界结论
    if evidence["ip_same"] and evidence["browser_ctrl"].get("n", 0) > 0 and evidence["local_probe"].get("error_code") == 54001:
        evidence["verdict"] = (
            "IP_EXCLUDED_CHANNEL_BINDING: same public IP + same browser token; "
            "browser stack OK, curl_cffi stack 54001 => TLS/HTTP2 connection fingerprint "
            "(or non-IP channel signal), not anti_content algorithm / not IP reputation"
        )
    else:
        evidence["verdict"] = "INCONCLUSIVE_SEE_FIELDS"
    print(f"[VERDICT] {evidence['verdict']}")

    out = __import__("pathlib").Path("dissect_channel_evidence.json")
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SAVE] {out.resolve()}")


if __name__ == "__main__":
    main()
