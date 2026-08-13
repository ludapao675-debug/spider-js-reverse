# -*- coding: utf-8 -*-
"""对比：Node 预签名 URL / 未签名 URL × 有无 Cookie 的纯 HTTP 取数结果。"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("probe_http")

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "replay_bdms_offline_out.json"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)


def build_signed_url(payload: dict) -> str:
    """从离线签名产物拼出带 msToken/a_bogus 的 URL。"""
    signed = payload.get("signed_url") or payload.get("output_url")
    if isinstance(signed, str) and signed.startswith("http"):
        return signed
    base = payload.get("input_url") or payload.get("INPUT")
    ab = payload.get("a_bogus") or payload.get("abogus") or payload.get("output")
    ms = payload.get("msToken") or payload.get("mstoken") or ""
    if not base or not ab or str(ab).startswith("http"):
        raise RuntimeError(f"无法从 {OUT_JSON.name} 拼签名 URL，keys={list(payload.keys())}")
    parsed = urllib.parse.urlparse(base)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    if ms:
        query["msToken"] = ms
    query["a_bogus"] = ab
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", urllib.parse.urlencode(query), "")
    )


def strip_sign(url: str) -> str:
    """去掉 msToken / a_bogus。"""
    parsed = urllib.parse.urlparse(url)
    query = {
        k: v
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if k not in ("a_bogus", "msToken")
    }
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", urllib.parse.urlencode(query), "")
    )


def hit(label: str, url: str, cookie: str | None) -> dict:
    """发起一次 GET，返回精简结果。"""
    headers = {
        "accept": "application/json, text/plain, */*",
        "referer": "https://www.toutiao.com/",
        "user-agent": UA,
    }
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read()
            text = body.decode("utf-8", "replace")
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
            return {
                "label": label,
                "status": resp.status,
                "body_len": len(body),
                "message": data.get("message"),
                "data_count": len(data.get("data") or []) if isinstance(data.get("data"), list) else None,
                "ok": resp.status == 200
                and data.get("message") == "success"
                and len(data.get("data") or []) > 0,
            }
    except urllib.error.HTTPError as exc:
        return {"label": label, "status": exc.code, "err": str(exc), "ok": False}
    except Exception as exc:  # noqa: BLE001 — 探测脚本需吞掉网络异常
        logger.exception("请求失败 label=%s", label)
        return {"label": label, "err": str(exc), "ok": False}


def main() -> int:
    if not OUT_JSON.exists():
        logger.error("缺少 %s，请先 node replay_bdms_offline.js", OUT_JSON.name)
        return 2
    payload = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    signed = build_signed_url(payload)
    unsigned = strip_sign(signed)
    # 与当前浏览器会话一致的最小 Cookie（ttwid/tt_webid 关键）
    cookie = (
        "ttwid=1%7C-Z-8BvaciYNPLXYekIK_sLdM1zfpSHb7bP31BCbrS78%7C1784601131%7C"
        "8d48aa6ed0b4aaac143a3df289704e01d364dcf561f4e279f3fe479d16f0ee85; "
        "tt_webid=7664797676097848841; "
        "s_v_web_id=verify_mru0mx0k_S2LqqQ1a_rNlG_43yw_9yAh_fY1wkrgN0qb4; "
        "tt_scid=cDML5LRrLh.TjZpdJXHPa0s6AWBLI39HoDUS9SYwSUeH9kUep9qbtvoJXpMcHcBjb341; "
        "gfkadpd=24,6457"
    )
    rows = [
        hit("signed_no_cookie", signed, None),
        hit("signed_with_cookie", signed, cookie),
        hit("unsigned_no_cookie", unsigned, None),
        hit("unsigned_with_cookie", unsigned, cookie),
    ]
    report = {
        "signed_head": signed[:160],
        "abogus_len": payload.get("abogus_len"),
        "rows": rows,
        "any_http_ok": any(r.get("ok") for r in rows),
        "note": "纯 HTTP 不稳定；稳定取数请用浏览器 unsigned fetch（sign_and_validate.js）",
    }
    out = HERE / "probe_http_signed_variants_out.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
