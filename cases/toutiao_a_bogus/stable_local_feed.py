#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
头条 feed 稳定本地复现：Node 现签 → 立刻纯 HTTP 取 JSON。

验收标准：
  status=200 且 message=success 且 data 非空

用法：
  # 纯本地（推荐）：依赖 mstoken_cache.json / xmst，无需浏览器
  python stable_local_feed.py --no-refresh

  # 首次或 cache 失效：刷新浏览器快照后再签
  python stable_local_feed.py

说明：
  - msToken = localStorage.xmst = bdms me[24].inner（来自 mssdk x-ms-token）
  - 必须「现签现用」a_bogus；未签名 URL 纯 HTTP 会 200 空 body
  - Cookie 非必须
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from sign_abogus import build_feed_url, sign_abogus

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("stable_local_feed")

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "stable_local_feed_out.json"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)


def fetch_signed(url: str, cookie: str | None = None, timeout: int = 30) -> dict:
    """对现签 URL 发起 GET，返回精简结果 + 可选原始 JSON。"""
    headers = {
        "accept": "application/json, text/plain, */*",
        "referer": "https://www.toutiao.com/",
        "user-agent": UA,
    }
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", "replace")
            try:
                data = json.loads(text) if text else {}
            except json.JSONDecodeError:
                data = {}
            items = data.get("data") if isinstance(data.get("data"), list) else []
            return {
                "status": resp.status,
                "body_len": len(raw),
                "message": data.get("message"),
                "data_count": len(items),
                "has_more": data.get("has_more"),
                "ok": resp.status == 200 and data.get("message") == "success" and len(items) > 0,
                "sample_titles": [
                    (it.get("title") or it.get("Abstract") or "")[:60]
                    for it in items[:3]
                    if isinstance(it, dict)
                ],
            }
    except urllib.error.HTTPError as exc:
        logger.error("HTTP 错误: %s", exc)
        return {"status": exc.code, "ok": False, "err": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("请求失败")
        return {"ok": False, "err": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="头条 feed：Node 现签 + 纯 HTTP 取数")
    parser.add_argument("--no-refresh", action="store_true", help="不刷新 browser_env_snapshot")
    parser.add_argument("--cookie", default="", help="可选 Cookie 字符串（如 ttwid=...）")
    parser.add_argument("--url", default="", help="自定义待签 feed URL；默认自动构造")
    args = parser.parse_args()

    base = args.url.strip() or build_feed_url()
    logger.info("待签 URL: %s...", base[:100])

    try:
        signed = sign_abogus(base, refresh_snapshot=not args.no_refresh)
    except RuntimeError as exc:
        logger.error("签名失败: %s", exc)
        logger.error("请确认后端 27183 + 浏览器在 toutiao.com，或先 node refresh_env_snapshot.js")
        return 2

    signed_url = signed.get("signed_url") or ""
    ab_len = signed.get("abogus_len") or len(signed.get("a_bogus") or "")
    logger.info("已签名 a_bogus_len=%s，立刻 HTTP GET ...", ab_len)

    result = fetch_signed(signed_url, cookie=args.cookie.strip() or None)
    report = {
        "input_url": signed.get("input_url") or base,
        "a_bogus_len": ab_len,
        "signed_url_head": signed_url[:160],
        "http": result,
        "ok": bool(result.get("ok")),
        "path": "node_sign_then_http",
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    logger.info("已写入 %s ok=%s data_count=%s", OUT_JSON.name, report["ok"], result.get("data_count"))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
