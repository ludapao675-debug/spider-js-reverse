# -*- coding: utf-8 -*-
"""P1 缺失格：sdenv token × 浏览器真栈 fetch（不发本地 reviews）。

历史结论（2026-08-05 local_repro_experiment C2）：同枚 sdenv 0as
浏览器内 fetch → 200+10 → 缺失格已填 = TICKET_CLEAN_CHANNEL_GAP。
本脚本仅在换账号/换 goods/换会话、需复验时再跑（仍消耗浏览器侧 1 次 reviews）。

2×2 判读：
  =200 → 票证干净，差纯在通道
  =54001 → sdenv 票证本身带标
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = "http://127.0.0.1:27183"
TAB_ID = "3AC01DA691EDCC73060A21A21F94ADDD"
GOODS_ID = "881388350961"
PDDUID = "9505538327527"
PAGE = 4


def api_post(path, body, timeout=120):
    req = urllib.request.Request(
        BACKEND + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_js(code, tab_id=TAB_ID, timeout=60):
    d = api_post(
        "/api/browser/page/run-js",
        {
            "tab_id": tab_id,
            "code": code,
            "return_mode": "json",
            "await_promise": True,
            "timeout_sec": timeout,
        },
        timeout=timeout + 30,
    )
    if not d.get("ok"):
        raise RuntimeError(d)
    r = d.get("result")
    if isinstance(r, dict) and r.get("__json_parse_error__"):
        raise RuntimeError(r)
    return r, d


def get_cookie_str():
    d = api_post("/api/browser/page/cookies", {"tab_id": TAB_ID}, timeout=20)
    items = d.get("cookies") or []
    return "; ".join(f"{c['name']}={c['value']}" for c in items if c.get("name"))


def gen_sdenv_token(cookie_str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "lre", os.path.join(HERE, "local_repro_experiment.py")
    )
    lre = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lre)

    # force current tab for bundle build
    r, meta = run_js(lre.BUNDLE_JS, timeout=90)
    res = r
    if not isinstance(res, dict) or "bundle" not in res:
        if meta.get("result_stashed") and meta.get("result_file"):
            fname = os.path.basename(str(meta["result_file"]))
            with urllib.request.urlopen(
                f"{BACKEND}/api/browser/page/run-js/result?file={fname}", timeout=30
            ) as resp:
                res = (json.loads(resp.read().decode("utf-8"))).get("data") or {}
        else:
            raise RuntimeError(f"bundle fail: {str(res)[:200]}")

    d = api_post(
        "/api/sdenv/run-code",
        {
            "js_code": res["bundle"],
            "url": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
            "cookies": cookie_str,
            "super_env": True,
            "timeout": 60,
            "eval_expression": "globalThis.__sdenv_token",
        },
        timeout=180,
    )
    token = ""
    for part in str(d.get("cookies") or "").split(";"):
        kv = part.strip()
        if kv.startswith("__sdenv_ac="):
            token = kv[len("__sdenv_ac=") :]
            break
    if not token:
        ev = d.get("eval_result")
        if isinstance(ev, str) and ev.startswith("0as"):
            token = ev.strip()
    if not token.startswith("0as"):
        raise RuntimeError(f"sdenv fail: {str(d.get('error'))[:240]}")
    return token, {
        "modules": res.get("modules"),
        "bundle_kb": len(res.get("bundle") or "") // 1024,
        "sdenv_ok": d.get("ok"),
        "error_type": d.get("error_type"),
    }


def main():
    evidence = {"ts": int(time.time() * 1000), "goods_id": GOODS_ID, "page": PAGE, "cell": "sdenv_token x browser_stack"}

    print("[0] cookie ...")
    cookie = get_cookie_str()
    evidence["cookie_n"] = len([p for p in cookie.split("; ") if p])
    print(f"    cookies={evidence['cookie_n']}")

    print("[1] sdenv token ...")
    ac, meta = gen_sdenv_token(cookie)
    evidence["token"] = {"prefix": ac[:8], "len": len(ac), **meta}
    print(f"    {ac[:28]}... len={len(ac)} modules={meta.get('modules')}")

    url = (
        f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
        f"?label_id=0&page={PAGE}&size=10&enable_video=1&enable_group_review=1"
        f"&pdduid={PDDUID}&is_back=1"
    )
    # 浏览器原生 fetch 发 sdenv token（真栈；只消耗浏览器侧 1 次）
    code = (
        "(()=>{const $args="
        + json.dumps({"url": url, "ac": ac}, ensure_ascii=False)
        + ";return (async()=>{"
        "const resp=await fetch($args.url,{method:'POST',"
        "headers:{'accept':'application/json, text/plain, */*',"
        "'content-type':'application/json;charset=UTF-8','anti-content':$args.ac},"
        "body:JSON.stringify({name:'goodsCommentListAxios',anti_content:$args.ac})});"
        "const d=await resp.json();"
        "return {status:resp.status,n:Array.isArray(d.data)?d.data.length:0,"
        "error_code:d.error_code||null,verify:!!d.verify_auth_token,"
        "msg:(d.error_msg||'').slice(0,40)};"
        "})();})()"
    )
    print("[2] browser fetch with sdenv token ...")
    t0 = time.time()
    result, _ = run_js(code, timeout=30)
    evidence["browser_result"] = {"elapsed": round(time.time() - t0, 3), **(result if isinstance(result, dict) else {"raw": result})}
    print(f"    {evidence['browser_result']}")

    n = evidence["browser_result"].get("n") or 0
    err = evidence["browser_result"].get("error_code")
    if n > 0:
        evidence["verdict"] = "TICKET_CLEAN_CHANNEL_GAP: sdenv token accepted on real browser stack => budget goes to ④a/④b TLS/H2 stack clone"
    elif err == 54001 or evidence["browser_result"].get("verify"):
        evidence["verdict"] = "TICKET_TAINTED: sdenv token rejected even on real browser stack => fix sdenv env first, channel weight down"
    else:
        evidence["verdict"] = "INCONCLUSIVE"
    print(f"[VERDICT] {evidence['verdict']}")

    out = os.path.join(HERE, "p1_missing_cell_evidence.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] {out}")


if __name__ == "__main__":
    main()
