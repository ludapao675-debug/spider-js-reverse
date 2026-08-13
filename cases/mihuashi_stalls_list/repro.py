# -*- coding: utf-8 -*-
"""米画师橱窗列表分页协议复现：WASM SignTool 生成 M-S/M-T 后 GET /api/v1/stalls。"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

BASE = "https://www.mihuashi.com"
API_PATH = "/api/v1/stalls"
CASE_DIR = Path(__file__).resolve().parent
SIGN_JS = CASE_DIR / "sign_tool.mjs"


def make_sign_headers(url_for_sign: str, timestamp: Optional[int] = None) -> Dict[str, str]:
    """调用 Node SignTool，生成与前端一致的 M-S / M-T / Web-Version。"""
    cmd = ["node", str(SIGN_JS.name), url_for_sign]
    if timestamp is not None:
        cmd.append(str(int(timestamp)))
    last_err = ""
    # Windows 子进程偶发 wasm unreachable，有限重试
    for attempt in range(1, 6):
        try:
            out = subprocess.check_output(
                cmd,
                cwd=str(CASE_DIR),
                stderr=subprocess.PIPE,
                timeout=60,
                encoding="utf-8",
                errors="replace",
            )
            payload = json.loads(out)
            if not payload.get("ok"):
                raise RuntimeError(f"SignTool 返回异常: {payload}")
            return {
                "M-S": str(payload["M-S"]),
                "M-T": str(payload["M-T"]),
                "Web-Version": "frontend",
            }
        except FileNotFoundError as exc:
            raise RuntimeError("未找到 node，请先安装 Node.js") from exc
        except subprocess.CalledProcessError as exc:
            last_err = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(
                "utf-8", "replace"
            )
            logger.warning("SignTool 第 %s 次失败: %s", attempt, last_err.splitlines()[-1] if last_err else exc)
        except json.JSONDecodeError as exc:
            last_err = str(exc)
            logger.warning("SignTool JSON 解析失败(第 %s 次): %s", attempt, exc)
    raise RuntimeError(f"SignTool 签名失败: {last_err}")


def fetch_stalls(
    page: int = 1,
    per: int = 20,
    category: int = 3,
    order: int = 2,
    state: str = "forsale",
    only_fast: bool = False,
    timeout: int = 30,
    max_retries: int = 25,
) -> Dict[str, Any]:
    """
    分页拉取橱窗列表。

    注意：签名输入是 axios config.url = '/api/v1/stalls'（不含 query），
    与真实请求 URL（带 query）不同。

    签名有效性根因（已验证）：
      M-S 由 WASM 内部对含 HashMap 的载荷序列化生成，key 迭代顺序受
      getrandom 影响，约 38% 落入服务端认可的规范顺序（“有效族”），
      其余 62% 为确定性无效签名（同串重发 0 通过）；有效签名偶发被服务端集群随机 403。

    【关键】getrandom 种子在 WASM 实例初始化时定一次（进程级偏置）：
      同一 node 进程内多次签名高度同命运（实测进程可 8/8 全无效）。
      因此必须【每次重试都 spawn 全新 node 进程】才能得到独立种子，
      切勿单进程批量签名（会把独立试验退化为批数试验，大幅降低成功率）。
      每次新进程约 38% 命中，重试 25 次失败概率 ≈ 0.62**25 ≈ 4e-6。
    """
    query = {
        "category": category,
        "only_fast": str(only_fast).lower(),
        "order": order,
        "page": page,
        "per": per,
        "state": state,
    }
    url = f"{BASE}{API_PATH}?{urlencode(query)}"
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
    referer = f"{BASE}/stalls/list?state={state}&category={category}&order={order}&onlyFast={str(only_fast).lower()}&page={page}"
    last_status = None
    last_data: Any = None
    for attempt in range(1, max_retries + 1):
        # 关键：每次重试都 spawn 全新 node 进程（make_sign_headers 内部调 node），
        # 获得一个独立的 WASM 初始化种子 → 独立的 38% 命中机会
        sign_headers = make_sign_headers(API_PATH)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": "Bearer null",
            "Referer": referer,
            "User-Agent": ua,
            **sign_headers,
        }
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            logger.warning("第 %s 次请求网络异常: %s", attempt, exc)
            continue
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:2000]}
        last_status, last_data = resp.status_code, data
        if resp.status_code == 200:
            if attempt > 1:
                logger.info("第 %s 次重试命中有效签名", attempt)
            return data
        # 403 多为签名落入无效族或服务端随机拒，重新 spawn 进程重签再试
        logger.info("第 %s 次 HTTP %s，重新 spawn 进程重签重试", attempt, resp.status_code)
    raise RuntimeError(f"重试 {max_retries} 次仍失败，末次 HTTP {last_status}: {last_data}")


def main(argv: Optional[list] = None) -> int:
    # Windows 控制台默认 GBK，橱窗名含 emoji 会导致 print 崩溃，强制标准输出走 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="米画师 stalls 分页本地复现")
    parser.add_argument("--page", type=int, default=2, help="页码，默认 2")
    parser.add_argument("--per", type=int, default=20, help="每页条数")
    parser.add_argument("--category", type=int, default=3, help="品类，立绘=3")
    parser.add_argument("--order", type=int, default=2, help="排序")
    parser.add_argument("--state", default="forsale", help="状态 forsale 等")
    parser.add_argument("--only-fast", action="store_true", help="仅快速橱窗")
    args = parser.parse_args(argv)

    if not (CASE_DIR / "mhs_fe_sign_bg.wasm").exists():
        print("缺少 mhs_fe_sign_bg.wasm，请放在本目录", file=sys.stderr)
        return 2
    if not SIGN_JS.exists():
        print("缺少 sign_tool.mjs", file=sys.stderr)
        return 2

    data = fetch_stalls(
        page=args.page,
        per=args.per,
        category=args.category,
        order=args.order,
        state=args.state,
        only_fast=args.only_fast,
    )
    stalls = data.get("stalls") or []
    summary = {
        "ok": True,
        "page": args.page,
        "total_pages": data.get("total_pages"),
        "stalls_count": len(stalls),
        "first_ids": [s.get("id") for s in stalls[:5]],
        "first_names": [s.get("name") for s in stalls[:5]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
