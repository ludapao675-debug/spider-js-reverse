# -*- coding: utf-8 -*-
"""Phase 1 live：V0 curl_cffi ×1 → V1 tls-client chrome_150 ≤2。

前提：phase0_tls_diff.json stock_aligned=true。
纪律：必须 --confirm-sacrifice；reviews 预算硬封顶；首 200 / 首 54001 按协议停。

链（单 Session 连接复用）：
  GET goods 页 → GET a3 → POST ae4 → POST a4(干净) → POST t.gif → dwell → POST reviews
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import string
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import a4_live_test as alt  # noqa: E402

BACKEND = "http://127.0.0.1:27183"
TAB_ID = "3AC01DA691EDCC73060A21A21F94ADDD"
GOODS_ID = "881388350961"
PDDUID = "9505538327527"
UA = alt.FP_UA
B36 = string.digits + string.ascii_lowercase

# HAR-ish Chrome header order（应用层；伪头由 profile 管）
HEADER_ORDER = [
    "accept",
    "accept-language",
    "content-type",
    "origin",
    "referer",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
    "anti-content",
    "verifyauthtoken",
    "cookie",
]


def api_post(path: str, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        BACKEND + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_js(code: str, timeout: int = 60) -> Any:
    d = api_post(
        "/api/browser/page/run-js",
        {
            "tab_id": TAB_ID,
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
    return r


def get_cookie_str() -> str:
    d = api_post(
        "/api/browser/page/cookies",
        {"tab_id": TAB_ID, "all_domains": True, "all_info": True},
        timeout=20,
    )
    items = d.get("cookies") or []
    keep = []
    for c in items:
        name = c.get("name") or ""
        val = c.get("value") or ""
        domain = (c.get("domain") or "").lstrip(".")
        if not name:
            continue
        if not (
            domain.endswith("pinduoduo.com")
            or domain.endswith("yangkeduo.com")
            or "pinduoduo" in domain
            or "yangkeduo" in domain
        ):
            continue
        # curl/tls headers must be latin-1
        try:
            f"{name}={val}".encode("latin-1")
        except UnicodeEncodeError:
            continue
        keep.append(f"{name}={val}")
    # de-dupe by name (first wins)
    seen = set()
    out = []
    for kv in keep:
        n = kv.split("=", 1)[0]
        if n in seen:
            continue
        seen.add(n)
        out.append(kv)
    return "; ".join(out)


def get_vat() -> str:
    r = run_js("(()=>({vat: localStorage.getItem('VerifyAuthToken')||''}))()")
    if isinstance(r, dict):
        return r.get("vat") or ""
    return r if isinstance(r, str) else ""


def gen_browser_token() -> str:
    r = run_js(
        "(async()=>{const ac=await window.__pdd_ac_mod.g();"
        "return{ac,len:String(ac).length,prefix:String(ac).slice(0,8)}})()"
    )
    ac = (r or {}).get("ac") if isinstance(r, dict) else None
    if not (isinstance(ac, str) and ac.startswith("0as")):
        raise RuntimeError(f"token fail: {r}")
    return ac


def shift(s: str, n: int) -> str:
    return "".join(chr(ord(ch) + n) for ch in s)


def build_clean_a4_body() -> dict:
    src = open(os.path.join(HERE, "verify_a4_sign.py"), encoding="utf-8").read()
    data0 = re.search(r'DATA = "([^"]+)"', src).group(1)
    pairs = alt.decode_data(data0)
    kv = dict(zip(pairs[0::2], pairs[1::2]))
    now_ms = int(time.time() * 1000)
    delta = now_ms - int(kv["reportTimestamp"])
    kv["botD"] = '{"bot":false,"botKind":""}'
    kv["botKinds"] = ""
    kv["botSignals"] = (
        '{"detectPluginsArray":"unknown","detectWebDriverDescriptor":"unknown"}'
    )
    kv["cdpProxy"] = "false"
    kv["hookFuncs"] = "[]"
    kv["reportTimestamp"] = str(now_ms)
    kv["uid"] = PDDUID
    try:
        mv = json.loads(kv["moveData"])
        for e in mv:
            if "timestamp" in e:
                e["timestamp"] += delta
        kv["moveData"] = json.dumps(mv, separators=(",", ":"))
    except Exception:
        pass
    m = re.match(r"^(.*~JtK)(\d+)$", kv.get("pageId", ""))
    if m:
        kv["pageId"] = m.group(1) + str(int(m.group(2)) + delta)
    new_pairs = []
    for i in range(0, len(pairs), 2):
        new_pairs.append(pairs[i])
        new_pairs.append(kv[pairs[i]])
    data_new = alt.encode_pairs(new_pairs)
    ts_str = str(now_ms)
    sign = hashlib.sha1((alt.SALT + ts_str + data_new).encode()).hexdigest()
    return {"data": data_new, "timestamp": ts_str, "appKey": "fe", "sign": sign}


def base_headers(cookie: str, extra: dict | None = None) -> dict:
    h = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "origin": "https://mobile.pinduoduo.com",
        "referer": f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}",
        "sec-ch-ua": '"Not=A?Brand";v="99", "Microsoft Edge";v="151", "Chromium";v="151"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": UA,
        "cookie": cookie,
    }
    if extra:
        h.update(extra)
    return h


def ordered_headers(h: dict) -> dict:
    """Preserve HEADER_ORDER then leftovers (tls-client respects insertion / header_order)."""
    out = {}
    for k in HEADER_ORDER:
        if k in h and h[k] is not None and h[k] != "":
            out[k] = h[k]
    for k, v in h.items():
        if k not in out and v is not None and v != "":
            out[k] = v
    return out


def b36(n: int) -> str:
    return "".join(random.choice(B36) for _ in range(n))


def build_tgif_body(cookies: dict) -> str:
    now = int(time.time() * 1000)
    nano = cookies.get("_nano_fp", "")
    vds = cookies.get("pdd_vds", "")
    dcf = f"{vds}.{random.randint(20, 30)}.{random.randint(100000000, 3999999999)}"
    return urllib.parse.urlencode(
        {
            "goods_id": GOODS_ID,
            "page_sn": "10058",
            "page_id": "",
            "refer_page_name": "",
            "refer_page_id": "",
            "refer_page_sn": "10390",
            "is_back": "1",
            "op": "impr",
            "log_id": f"{now}{b36(16)}",
            "dcf": dcf,
            "cookie_fp": nano,
            "storage_fp": nano,
            "time": str(now),
        }
    )


def cookie_dict(cookie_str: str) -> dict:
    out = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def merge_set_cookie(cookie_str: str, resp) -> str:
    """Best-effort merge Set-Cookie into cookie_str."""
    jar = cookie_dict(cookie_str)
    try:
        # curl_cffi / requests
        if hasattr(resp, "cookies"):
            for k, v in resp.cookies.items():
                jar[k] = v
    except Exception:
        pass
    # tls-client may expose headers
    try:
        sc = resp.headers.get("Set-Cookie") or resp.headers.get("set-cookie")
        if sc:
            # may be multiple joined
            for piece in re.split(r",(?=[^;]+?=)", sc):
                nv = piece.split(";", 1)[0]
                if "=" in nv:
                    k, v = nv.split("=", 1)
                    jar[k.strip()] = v.strip()
    except Exception:
        pass
    return "; ".join(f"{k}={v}" for k, v in jar.items())


class CurlSession:
    name = "V0_curl_cffi"

    def __init__(self):
        from curl_cffi import requests as crl

        self._crl = crl
        self.sess = crl.Session(impersonate="chrome")

    def get(self, url, headers, **kw):
        return self.sess.get(url, headers=ordered_headers(headers), timeout=30, **kw)

    def post(self, url, headers, data=None, **kw):
        return self.sess.post(
            url, headers=ordered_headers(headers), data=data, timeout=30, **kw
        )

    def close(self):
        try:
            self.sess.close()
        except Exception:
            pass


class TlsClientSession:
    name = "V1_tls_chrome_150"

    def __init__(self, identifier: str = "chrome_150", timeout_seconds: int = 60):
        import tls_client

        self.timeout_seconds = timeout_seconds
        self.sess = tls_client.Session(
            client_identifier=identifier,
            random_tls_extension_order=False,
        )
        try:
            self.sess.pseudo_header_order = [":method", ":authority", ":scheme", ":path"]
        except Exception:
            pass

    def get(self, url, headers, **kw):
        to = kw.pop("timeout_seconds", None) or self.timeout_seconds
        return self.sess.get(
            url,
            headers=ordered_headers(headers),
            header_order=HEADER_ORDER,
            timeout_seconds=to,
        )

    def post(self, url, headers, data=None, **kw):
        to = kw.pop("timeout_seconds", None) or self.timeout_seconds
        return self.sess.post(
            url,
            headers=ordered_headers(headers),
            header_order=HEADER_ORDER,
            data=data,
            timeout_seconds=to,
        )

    def close(self):
        try:
            self.sess.close()
        except Exception:
            pass


def summarize_reviews(resp) -> dict:
    try:
        j = resp.json()
    except Exception:
        text = getattr(resp, "text", "") or ""
        j = {"raw": text[:300]}
    n = len(j.get("data")) if isinstance(j.get("data"), list) else 0
    return {
        "http": getattr(resp, "status_code", None),
        "error_code": j.get("error_code"),
        "n": n,
        "verify": bool(j.get("verify_auth_token")),
        "msg": (j.get("error_msg") or "")[:80],
        "ok": n > 0 and not j.get("verify_auth_token") and j.get("error_code") in (None, 0),
    }


def run_full_chain(factory: Callable, cookie0: str, vat: str, ac: str, page: int) -> dict:
    s = factory()
    ev: dict[str, Any] = {"variant": s.name, "page": page, "steps": {}}
    cookie = cookie0
    referer = f"https://mobile.pinduoduo.com/goods_comments.html?goods_id={GOODS_ID}"
    try:
        # 0) GET goods page (warm TLS/H2)
        print(f"  [{s.name}] GET goods ...")
        r0 = s.get(
            referer,
            headers=base_headers(
                cookie,
                {
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                },
            ),
        )
        cookie = merge_set_cookie(cookie, r0)
        ev["steps"]["get_goods"] = getattr(r0, "status_code", None)

        # 1) a3
        print(f"  [{s.name}] GET a3 ...")
        r1 = s.get(
            "https://mobile.pinduoduo.com/proxy/api/xg/pfb/a3",
            headers=base_headers(cookie),
        )
        cookie = merge_set_cookie(cookie, r1)
        ev["steps"]["a3"] = {
            "http": getattr(r1, "status_code", None),
            "body": (getattr(r1, "text", "") or "")[:120],
        }

        # 2) ae4
        print(f"  [{s.name}] POST ae4 ...")
        payload = json.dumps(
            {"u": PDDUID, "f": "", "keys": "t,acc"}, separators=(",", ":")
        )
        body2 = json.dumps({"data": shift(payload, 30)}, separators=(",", ":"))
        r2 = s.post(
            "https://xg.pinduoduo.com/xg/pfb/ae4",
            headers=base_headers(
                cookie,
                {
                    "content-type": "application/json;charset=UTF-8",
                    "sec-fetch-site": "same-site",
                },
            ),
            data=body2,
        )
        cookie = merge_set_cookie(cookie, r2)
        ev["steps"]["ae4"] = {"http": getattr(r2, "status_code", None)}

        # 3) a4
        print(f"  [{s.name}] POST a4 ...")
        a4body = json.dumps(build_clean_a4_body(), separators=(",", ":"))
        r3 = s.post(
            "https://mobile.pinduoduo.com/proxy/api/xg/pfb/a4",
            headers=base_headers(
                cookie, {"content-type": "application/json;charset=UTF-8"}
            ),
            data=a4body,
        )
        cookie = merge_set_cookie(cookie, r3)
        try:
            j3 = r3.json()
        except Exception:
            j3 = {}
        result_a = ((j3.get("result") or {}).get("a")) if isinstance(j3, dict) else None
        if result_a:
            jar = cookie_dict(cookie)
            jar["njrpl"] = result_a
            cookie = "; ".join(f"{k}={v}" for k, v in jar.items())
        ev["steps"]["a4"] = {
            "http": getattr(r3, "status_code", None),
            "success": j3.get("success") if isinstance(j3, dict) else None,
            "has_a": bool(result_a),
        }

        # 4) t.gif
        print(f"  [{s.name}] POST t.gif ...")
        tbody = build_tgif_body(cookie_dict(cookie))
        r4 = s.post(
            "https://th.pinduoduo.com/t.gif",
            headers=base_headers(
                cookie,
                {
                    "content-type": "application/x-www-form-urlencoded",
                    "sec-fetch-site": "same-site",
                },
            ),
            data=tbody,
        )
        cookie = merge_set_cookie(cookie, r4)
        ev["steps"]["tgif"] = {"http": getattr(r4, "status_code", None)}

        dwell = random.uniform(3.0, 8.0)
        print(f"  [{s.name}] dwell {dwell:.1f}s ...")
        time.sleep(dwell)
        ev["dwell"] = round(dwell, 2)

        # 5) reviews — THE budget unit
        print(f"  [{s.name}] POST reviews (BUDGET) ...")
        url = (
            f"https://mobile.pinduoduo.com/proxy/api/reviews/{GOODS_ID}/list"
            f"?label_id=0&page={page}&size=10&enable_video=1&enable_group_review=1"
            f"&pdduid={PDDUID}&is_back=1"
        )
        extra = {
            "content-type": "application/json;charset=UTF-8",
            "anti-content": ac,
        }
        if vat:
            extra["verifyauthtoken"] = vat
        body5 = json.dumps(
            {"name": "goodsCommentListAxios", "anti_content": ac},
            separators=(",", ":"),
        )
        r5 = s.post(url, headers=base_headers(cookie, extra), data=body5)
        rev = summarize_reviews(r5)
        ev["reviews"] = rev
        ev["ac_prefix"] = ac[:8]
        ev["ac_len"] = len(ac)
        print(f"  [{s.name}] reviews => {rev}")
        return ev
    finally:
        s.close()


def main() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-sacrifice", action="store_true", required=True)
    ap.add_argument("--page-v0", type=int, default=41)
    ap.add_argument("--page-v1", type=int, default=42)
    args = ap.parse_args()

    phase0 = json.load(open(os.path.join(HERE, "phase0_tls_diff.json"), encoding="utf-8"))
    if not phase0.get("verdict", {}).get("stock_aligned"):
        print("ABORT: Phase0 not aligned")
        sys.exit(2)

    evidence: dict[str, Any] = {
        "ts": int(time.time() * 1000),
        "goods_id": GOODS_ID,
        "pdduid": PDDUID,
        "tab_id": TAB_ID,
        "phase0": phase0.get("verdict"),
        "budget": {"reviews_max": 5, "used": 0},
        "variants": {},
    }

    print("[prep] cookies + vat + fresh 0as ...")
    cookie = get_cookie_str()
    vat = get_vat()
    print(f"  cookies≈{len(cookie)}B vat={bool(vat)} ({len(vat)}B)")

    # ── V0 ──
    print("\n=== V0 curl_cffi (expect 54001; drift stop if 200) ===")
    ac0 = gen_browser_token()
    print(f"  token {ac0[:12]}... len={len(ac0)}")
    v0 = run_full_chain(CurlSession, cookie, vat, ac0, args.page_v0)
    evidence["variants"]["V0"] = v0
    evidence["budget"]["used"] += 1
    if v0.get("reviews", {}).get("ok"):
        evidence["verdict"] = "DRIFT: V0 unexpected 200 — stop all, reassess environment"
        _save(evidence)
        print(evidence["verdict"])
        sys.exit(3)
    print("  V0 rejected as expected (or non-200) — continue V1")

    time.sleep(2)

    # ── V1 ──
    print("\n=== V1 tls-client chrome_150 (≤2; stop on first 200 or 54001) ===")
    ac1 = gen_browser_token()
    print(f"  token {ac1[:12]}... len={len(ac1)}")
    v1 = run_full_chain(TlsClientSession, cookie, vat, ac1, args.page_v1)
    evidence["variants"]["V1"] = v1
    evidence["budget"]["used"] += 1

    rev = v1.get("reviews") or {}
    if rev.get("ok"):
        evidence["verdict"] = (
            "PASS_4a: chrome_150 reviews 200 — TLS ClientHello stack is sufficient; "
            "pure-local via tls-client成立"
        )
    elif rev.get("error_code") == 54001 or rev.get("verify"):
        evidence["verdict"] = (
            "FAIL_CHANNEL_BEYOND_JA4: chrome_150 JA4-aligned still 54001 — "
            "binding beyond TLS+H2 SETTINGS (④d/④f); pure-local判死；本地预算永久关闭；全转 Extension"
        )
    else:
        evidence["verdict"] = f"INCONCLUSIVE: {rev}"

    _save(evidence)
    print(f"\n[VERDICT] {evidence['verdict']}")
    print(f"[BUDGET] reviews used={evidence['budget']['used']}")


def _save(evidence: dict) -> None:
    path = os.path.join(HERE, "phase1_live_evidence.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] {path}")


if __name__ == "__main__":
    main()
