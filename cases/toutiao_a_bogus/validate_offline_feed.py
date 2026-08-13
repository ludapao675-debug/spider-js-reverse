#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纯离线 a_bogus 验收：
  1) 可选：调用 node replay_bdms_offline.js 重新签名
  2) 读取 replay_bdms_offline_out.json
  3) 格式校验 + 可选浏览器 oracle 对比（推荐）
  4) 可选 Python requests 直连（今日头条 feed 常返回空体，仅作探测）

用法：
  python validate_offline_feed.py
  python validate_offline_feed.py --resign
  python validate_offline_feed.py --browser-oracle
  python validate_offline_feed.py --http-probe --cookies-from-browser
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "replay_bdms_offline_out.json"
BACKEND = "http://127.0.0.1:27183"

# Windows 常见 Python 路径（py launcher 可能未安装）
PYTHON_CANDIDATES = [
    Path(r"E:\aicode\.venv\Scripts\python.exe"),
    Path(sys.executable),
]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.toutiao.com/",
}

ABOGUS_RE = re.compile(r"^[A-Za-z0-9_\-/=]+$")


def format_ok(abogus: str) -> bool:
    """a_bogus 格式是否合法（168/172 + base64url）"""
    if not abogus:
        return False
    return len(abogus) in (168, 172) and bool(ABOGUS_RE.match(abogus))


def run_node_resign() -> None:
    """调用 Node 离线脚本重新生成 a_bogus"""
    script = HERE / "replay_bdms_offline.js"
    logger.info("运行 node %s ...", script.name)
    try:
        proc = subprocess.run(
            ["node", str(script)],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 node，请先安装 Node.js") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("node replay_bdms_offline.js 超时") from exc

    if proc.stdout:
        logger.info(proc.stdout.strip())
    if proc.returncode != 0:
        logger.error(proc.stderr.strip() if proc.stderr else "node 退出码 %s", proc.returncode)
        raise RuntimeError(f"node 签名失败，exit={proc.returncode}")


def run_browser_unsigned_fetch() -> dict:
    """浏览器内对未签名 URL fetch（服务端可用性 oracle）"""
    script = HERE / "validate_browser_unsigned_fetch.js"
    try:
        proc = subprocess.run(
            ["node", str(script)],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 node") from exc

    if proc.stdout:
        logger.info(proc.stdout.strip())
    if proc.returncode != 0:
        logger.error(proc.stderr.strip() if proc.stderr else "unsigned fetch 未通过")
        raise RuntimeError("浏览器 unsigned fetch 验收失败")

    result_path = HERE / "validate_unsigned_fetch_result.json"
    if not result_path.is_file():
        raise RuntimeError("缺少 validate_unsigned_fetch_result.json")
    return json.loads(result_path.read_text(encoding="utf-8"))


def run_browser_oracle() -> dict:
    """Node 脚本：浏览器内 XHR oracle 对比"""
    script = HERE / "validate_offline_browser.js"
    try:
        proc = subprocess.run(
            ["node", str(script)],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 node") from exc

    if proc.stdout:
        logger.info(proc.stdout.strip())
    if proc.returncode != 0:
        logger.error(proc.stderr.strip() if proc.stderr else "oracle 对比未通过")
        raise RuntimeError("浏览器 oracle 对比失败")

    result_path = HERE / "validate_oracle_result.json"
    if not result_path.is_file():
        raise RuntimeError("缺少 validate_oracle_result.json")
    return json.loads(result_path.read_text(encoding="utf-8"))


def load_sign_result() -> dict:
    """读取离线签名结果"""
    if not OUT_JSON.is_file():
        raise FileNotFoundError(f"缺少 {OUT_JSON}，请先运行 node replay_bdms_offline.js")
    try:
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"解析 {OUT_JSON.name} 失败: {exc}") from exc


def fetch_browser_cookies() -> dict[str, str]:
    """从 crypto-hunter 后端读取当前 tab Cookie"""
    try:
        resp = requests.post(
            f"{BACKEND}/api/browser/page/cookies",
            json={"all_domains": False, "all_info": False},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as exc:
        logger.warning("读取浏览器 Cookie 失败（将无 Cookie 请求）: %s", exc)
        return {}

    items = body.get("cookies") or body.get("data", {}).get("cookies") or []
    out: dict[str, str] = {}
    for c in items:
        if isinstance(c, dict) and c.get("name"):
            out[str(c["name"])] = str(c.get("value", ""))
    logger.info("已从浏览器读取 %d 个 Cookie", len(out))
    return out


def fetch_feed(signed_url: str, cookies: dict[str, str] | None) -> dict:
    """HTTP GET 已签名 feed URL（探测用，常为空体）"""
    try:
        resp = requests.get(
            signed_url,
            headers=DEFAULT_HEADERS,
            cookies=cookies or {},
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.error("HTTP 请求失败: %s", exc)
        raise

    logger.info("HTTP %s, body_len=%d", resp.status_code, len(resp.text or ""))
    preview = (resp.text or "")[:240]
    if not resp.text or not resp.text.strip().startswith("{"):
        logger.warning("响应非 JSON（预签名 URL 重放常见），预览: %s", preview)
        return {
            "ok": False,
            "http_status": resp.status_code,
            "preview": preview,
            "hint": "toutiao feed 需在浏览器内对未签名 URL 发起 fetch/XHR",
        }

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        logger.error("JSON 解析失败: %s", exc)
        return {"ok": False, "http_status": resp.status_code, "preview": preview}

    message = data.get("message")
    ok = resp.status_code == 200 and message == "success"
    return {
        "ok": ok,
        "http_status": resp.status_code,
        "message": message,
        "data_count": len(data.get("data") or []),
        "preview": json.dumps(data, ensure_ascii=False)[:300],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="离线 a_bogus 验收")
    parser.add_argument("--resign", action="store_true", help="先运行 node replay_bdms_offline.js")
    parser.add_argument(
        "--browser-unsigned-fetch",
        action="store_true",
        help="浏览器内 fetch 未签名 URL（服务端可用性 oracle，推荐）",
    )
    parser.add_argument(
        "--refresh-snapshot",
        action="store_true",
        help="--resign 前先刷新 browser_env_snapshot.json",
    )
    parser.add_argument(
        "--browser-oracle",
        action="store_true",
        help="浏览器内 XHR oracle 对比（需后端+浏览器 tab）",
    )
    parser.add_argument(
        "--http-probe",
        action="store_true",
        help="Python requests 探测（常为空体，非主验收项）",
    )
    parser.add_argument(
        "--cookies-from-browser",
        action="store_true",
        help="HTTP 探测时从 crypto-hunter 浏览器 tab 读取 Cookie",
    )
    args = parser.parse_args()

    if args.resign:
        if args.refresh_snapshot:
            subprocess.run(["node", str(HERE / "refresh_env_snapshot.js")], cwd=str(HERE), check=False)
        run_node_resign()

    sign = load_sign_result()
    signed_url = sign.get("signed_url") or ""
    abogus = sign.get("a_bogus") or ""
    if not signed_url or not abogus:
        logger.error("签名结果不完整: %s", sign)
        return 1

    logger.info("a_bogus len=%d prefix=%s...", len(abogus), abogus[:40])

    format_result = {
        "ok": len(abogus) in (168, 172) and bool(ABOGUS_RE.match(abogus)),
        "len": len(abogus),
    }
    if not format_result["ok"]:
        logger.error("格式校验失败: len=%s", len(abogus))
        return 1
    logger.info("格式校验通过 (len=%d)", len(abogus))

    unsigned_fetch_result = None
    if args.browser_unsigned_fetch:
        unsigned_fetch_result = run_browser_unsigned_fetch()
        if not unsigned_fetch_result.get("ok"):
            logger.error("浏览器 unsigned fetch 未返回 success: %s", unsigned_fetch_result.get("result"))
            return 2
        logger.info(
            "浏览器 unsigned fetch 通过: data_count=%s body_len=%s",
            unsigned_fetch_result.get("result", {}).get("data_count"),
            unsigned_fetch_result.get("result", {}).get("body_len"),
        )

    oracle_result = None
    if args.browser_oracle:
        oracle_result = run_browser_oracle()
        if oracle_result.get("compare", {}).get("lcs_len", 0) < 24:
            logger.warning(
                "与浏览器 oracle 公共段较短 (lcs=%s)，指纹未完全对齐",
                oracle_result.get("compare", {}).get("lcs_len"),
            )
        logger.info(
            "浏览器 oracle 对比: lcs=%s exact=%s offline_len=%s oracle_len=%s",
            oracle_result.get("compare", {}).get("lcs_len"),
            oracle_result.get("compare", {}).get("exact_match"),
            oracle_result.get("offline", {}).get("a_bogus_len"),
            oracle_result.get("browser_oracle", {}).get("a_bogus_len"),
        )

    http_result = None
    if args.http_probe:
        cookies = fetch_browser_cookies() if args.cookies_from_browser else {}
        http_result = fetch_feed(signed_url, cookies)

    report = {
        "input_url": sign.get("input_url"),
        "a_bogus_len": len(abogus),
        "signed_url_head": signed_url[:160],
        "format": format_result,
        "browser_unsigned_fetch": unsigned_fetch_result,
        "browser_oracle": oracle_result,
        "http_probe": http_result,
        "used_browser_cookies": bool(args.cookies_from_browser),
    }
    report_path = HERE / "validate_offline_result.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("验收报告已写入 %s", report_path.name)

    if args.http_probe and http_result and http_result.get("ok"):
        logger.info("HTTP 探测通过: message=success")
    elif args.http_probe:
        logger.warning("HTTP 探测未返回 JSON（预期行为，不代表签名失败）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
