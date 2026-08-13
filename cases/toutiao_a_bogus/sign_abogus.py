#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
今日头条 a_bogus 离线签名 Python 封装（调 Node replay_bdms_offline.js）

示例：
    from sign_abogus import sign_abogus, sign_feed_url
    signed = sign_abogus("https://www.toutiao.com/api/pc/list/feed?...")
    print(signed["a_bogus"], signed["signed_url"])
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
NODE_SCRIPT = HERE / "replay_bdms_offline.js"
OUT_JSON = HERE / "replay_bdms_offline_out.json"


def _run_node(args: list[str], *, timeout: int = 180, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """运行 node 子命令"""
    try:
        return subprocess.run(
            ["node", *args],
            cwd=str(cwd or HERE),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 node，请先安装 Node.js") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("node 命令超时") from exc


def refresh_env_snapshot(*, timeout: int = 60) -> None:
    """签名前刷新 browser_env_snapshot.json（同步 msToken / me[24]）"""
    script = HERE / "refresh_env_snapshot.js"
    if not script.is_file():
        raise FileNotFoundError(f"缺少 {script}")
    proc = _run_node([str(script)], timeout=timeout)
    if proc.stdout:
        logger.info(proc.stdout.strip())
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"刷新快照失败 exit={proc.returncode}: {err[:500]}")


def _run_node_sign(input_url: str, timeout: int = 180, *, refresh_snapshot: bool = False) -> dict[str, Any]:
    """调用 Node 离线脚本签名"""
    if refresh_snapshot:
        refresh_env_snapshot(timeout=min(timeout, 60))

    if not NODE_SCRIPT.is_file():
        raise FileNotFoundError(f"缺少 {NODE_SCRIPT}")

    proc = _run_node([str(NODE_SCRIPT), input_url], timeout=timeout)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"node 签名失败 exit={proc.returncode}: {err[:500]}")

    if not OUT_JSON.is_file():
        raise RuntimeError("node 未写出 replay_bdms_offline_out.json")

    try:
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"解析签名结果失败: {exc}") from exc


def build_feed_url(
    *,
    max_behot_time: int | None = None,
    offset: int = 0,
    category: str = "pc_profile_recommend",
    channel_id: int = 0,
    aid: int = 24,
    app_name: str = "toutiao_web",
) -> str:
    """构造 feed 待签 URL（不含 msToken / a_bogus）"""
    import time

    ts = max_behot_time if max_behot_time is not None else int(time.time())
    qs = urlencode({
        "channel_id": channel_id,
        "max_behot_time": ts,
        "offset": offset,
        "category": category,
        "aid": aid,
        "app_name": app_name,
    })
    return f"https://www.toutiao.com/api/pc/list/feed?{qs}"


def sign_abogus(input_url: str, *, timeout: int = 180, refresh_snapshot: bool = False) -> dict[str, Any]:
    """
    对给定 URL 离线签名。

    Returns:
        {
          "input_url": str,
          "a_bogus": str,
          "signed_url": str,
          "abogus_len": int,
          "elapsed_ms": int,
          "init_env_patched": int,
        }
    """
    try:
        result = _run_node_sign(input_url, timeout=timeout, refresh_snapshot=refresh_snapshot)
    except (RuntimeError, FileNotFoundError) as exc:
        logger.error("签名失败: %s", exc)
        raise

    if not result.get("a_bogus"):
        raise RuntimeError(f"签名结果无效: {result}")
    return result


def sign_feed_url(*, refresh_snapshot: bool = False, **kwargs: Any) -> dict[str, Any]:
    """构造 feed URL 并签名（kwargs 传给 build_feed_url）"""
    url = build_feed_url(**kwargs)
    out = sign_abogus(url, refresh_snapshot=refresh_snapshot)
    out["feed_url_template"] = url
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    refresh = "--refresh-snapshot" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--refresh-snapshot"]
    url = args[0] if args else build_feed_url()
    try:
        result = sign_abogus(url, refresh_snapshot=refresh)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
