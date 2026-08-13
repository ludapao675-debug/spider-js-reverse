#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成示例：在真实项目里如何使用 toutiao a_bogus 签名。

复制本文件到你的业务项目，或 import cases/toutiao_a_bogus/sign_abogus.py。

前置：
  1. crypto-hunter 后端 + 浏览器 tab 已打开 toutiao 文章页
  2. 首次运行前：cd cases/toutiao_a_bogus && node refresh_env_snapshot.js

注意：
  - sign_abogus 产出 a_bogus/msToken；必须「现签现用」
  - 新鲜 signed_url 可用 urllib/requests 立刻 GET（见 stable_local_feed.py）
  - 未签名 URL / 过期签 会 200 空 body；浏览器 unsigned fetch 仍可作备用
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 按实际项目调整路径
CASE_DIR = Path(__file__).resolve().parent
if str(CASE_DIR) not in sys.path:
    sys.path.insert(0, str(CASE_DIR))

from sign_abogus import build_feed_url, sign_abogus  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_signed_feed_params(
    *,
    refresh_snapshot: bool = True,
    category: str = "pc_profile_recommend",
) -> dict:
    """
    获取带 a_bogus 的 feed 请求参数（供业务 HTTP 客户端拼装）。

    Returns:
        {
          "input_url": 未签名 base URL,
          "signed_url": 含 msToken + a_bogus（勿直接 requests 重放）,
          "a_bogus": str,
          "abogus_len": int,
        }
    """
    base_url = build_feed_url(category=category)
    result = sign_abogus(base_url, refresh_snapshot=refresh_snapshot)
    return {
        "input_url": result["input_url"],
        "signed_url": result["signed_url"],
        "a_bogus": result["a_bogus"],
        "abogus_len": result.get("abogus_len") or len(result["a_bogus"]),
    }


def main() -> int:
    try:
        params = get_signed_feed_params(refresh_snapshot=True)
    except RuntimeError as exc:
        logger.error("签名失败: %s", exc)
        logger.error("请确认：1) 后端 27183 运行中 2) 浏览器 tab 在 toutiao 3) 已 node refresh_env_snapshot.js")
        return 1

    logger.info("a_bogus len=%d", params["abogus_len"])
    logger.info("signed_url head: %s...", params["signed_url"][:120])
    logger.info("集成提示: 用 a_bogus/msToken 拼参；取 JSON 数据请走 fetch_feed_via_browser.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
