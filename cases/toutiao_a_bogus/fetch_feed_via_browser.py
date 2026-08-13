#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过浏览器内 fetch 未签名 feed URL 获取 JSON（绕过 signed_url 不可重放限制）。

需 crypto-hunter 后端 + 今日头条 tab 已打开。

用法：
  python fetch_feed_via_browser.py
  python fetch_feed_via_browser.py --save feed_sample.json
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
BACKEND = "http://127.0.0.1:27183"


def build_feed_url(**kwargs: Any) -> str:
    """构造未签名 feed URL"""
    ts = kwargs.pop("max_behot_time", None) or int(time.time())
    params = {
        "channel_id": kwargs.pop("channel_id", 0),
        "max_behot_time": ts,
        "offset": kwargs.pop("offset", 0),
        "category": kwargs.pop("category", "pc_profile_recommend"),
        "aid": kwargs.pop("aid", 24),
        "app_name": kwargs.pop("app_name", "toutiao_web"),
        **kwargs,
    }
    return f"https://www.toutiao.com/api/pc/list/feed?{urlencode(params)}"


def fetch_unsigned_via_browser(unsigned_url: str, *, timeout: int = 90) -> dict[str, Any]:
    """浏览器内 fetch 未签名 URL（调 Node 脚本，与 validate 链路一致）"""
    script = HERE / "validate_browser_unsigned_fetch.js"
    if not script.is_file():
        raise FileNotFoundError(f"缺少 {script}")

    try:
        proc = subprocess.run(
            ["node", str(script), unsigned_url],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("浏览器 fetch 超时") from exc

    if proc.stdout:
        logger.info(proc.stdout.strip()[-800:])

    result_path = HERE / "validate_unsigned_fetch_result.json"
    if not result_path.is_file():
        raise RuntimeError(f"node 未写出 {result_path.name}: {proc.stderr[:300]}")

    report = json.loads(result_path.read_text(encoding="utf-8"))
    if not report.get("ok"):
        raise RuntimeError(f"feed 未返回 success: {report.get('result')}")

    inner = report.get("result") or {}
    return {
        "status": inner.get("status"),
        "final_url": inner.get("final_url"),
        "message": inner.get("message"),
        "data_count": inner.get("data_count"),
        "body_text_len": inner.get("body_len"),
        "body": None,
    }


def refresh_env() -> None:
    """刷新 msToken 快照 + 浏览器指纹"""
    for script in ("refresh_env_snapshot.js", "refresh_browser_fingerprint.js"):
        p = HERE / script
        if not p.is_file():
            continue
        proc = subprocess.run(
            ["node", str(p)],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.stdout:
            logger.info(proc.stdout.strip())
        if proc.returncode != 0:
            logger.warning("%s 退出码 %s", script, proc.returncode)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="浏览器内 fetch 未签名 feed")
    parser.add_argument("--url", help="未签名 feed URL（默认自动构造）")
    parser.add_argument("--save", help="保存完整 JSON 到文件")
    parser.add_argument("--refresh-env", action="store_true", help="fetch 前刷新快照与指纹")
    args = parser.parse_args()

    if args.refresh_env:
        refresh_env()

    url = args.url or build_feed_url()
    logger.info("fetch 未签名 URL: %s...", url[:100])

    try:
        result = fetch_unsigned_via_browser(url)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    logger.info(
        "成功 message=%s data_count=%s body_len=%s",
        result.get("message"),
        result.get("data_count"),
        result.get("body_text_len"),
    )

    if args.save:
        out_path = Path(args.save)
        payload = result.get("body") or result
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("已保存 %s", out_path)

    #  stdout 摘要（避免撑爆终端）
    summary = {
        "ok": True,
        "final_url_head": (result.get("final_url") or "")[:200],
        "data_count": result.get("data_count"),
        "first_title": None,
    }
    body = result.get("body") or {}
    items = body.get("data") or []
    if items and isinstance(items[0], dict):
        summary["first_title"] = items[0].get("title") or items[0].get("Abstract")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
