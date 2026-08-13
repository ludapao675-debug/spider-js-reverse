# -*- coding: utf-8 -*-
"""查策网产业政策项目分页 API 本地复现。

目标接口:
  GET https://web.chace-ai.com/api/ccw/project/evaluation/getList/

请求侧无签名；响应 data 为自定义包装后的 AES-CBC 密文。
解密函数对应前端 jsapp 模块 `myDecrypt`。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import sys
from typing import Any

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("chacewang_pagination")

API_URL = "https://web.chace-ai.com/api/ccw/project/evaluation/getList/"
DEFAULT_AREA = "RegisterArea_HNDQ_Guangdong_SZ"
MARK = "ccwfp___"


def md5_hex(text: str) -> str:
    """与前端 createHash('md5').digest('hex') 一致。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def derive_key_iv(prefix10: str, decoded: str, length: int = 48) -> str:
    """链式 MD5 派生 48 字符：前 32 为 AES key，后 16 为 IV。"""
    mid32 = decoded[18:50]
    seed = prefix10 + mid32
    digest = md5_hex(seed)
    acc = digest
    while len(acc) < length:
        digest = md5_hex(digest + seed)
        acc += digest
    return acc[:length]


def my_decrypt(cipher_b64: str) -> str:
    """还原前端 myDecrypt：Base64 -> 头部分片 -> AES-CBC 解密。"""
    # js-base64 decode 得到 latin1 字符串
    pad_len = (4 - len(cipher_b64) % 4) % 4
    decoded = base64.b64decode(cipher_b64 + ("=" * pad_len)).decode("latin1")

    if MARK not in decoded[:50]:
        logger.warning("未检测到标记 %s，仍按固定切片规则尝试解密", MARK)

    prefix10 = decoded[:10]
    derived = derive_key_iv(prefix10, decoded, 48)
    key = derived[:32].encode("utf-8")
    iv = derived[32:].encode("utf-8")
    hex_cipher = decoded[50:]
    ciphertext = bytes.fromhex(hex_cipher)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
    return plaintext.decode("utf-8")


def fetch_list(
    page: int = 1,
    size: int = 20,
    area: str = DEFAULT_AREA,
    timeout: int = 30,
) -> Any:
    """请求分页列表并解密 data 字段。"""
    params = {
        "page": page,
        "size": size,
        "industry": "",
        "area": area,
        "dept": "",
        "partition": "",
        "pe_name": "",
        "currentArea": area,
        "query_date": 0,
        "full_search": 0,
        "sort_type": 0,
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.chacewang.com",
        "Referer": "https://www.chacewang.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"
        ),
    }

    logger.info("请求 page=%s size=%s area=%s", page, size, area)
    try:
        resp = requests.get(API_URL, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.exception("请求失败: %s", exc)
        raise

    if payload.get("code") != 200:
        raise RuntimeError(f"接口返回异常: {payload}")

    encrypted = payload.get("data")
    if not isinstance(encrypted, str) or not encrypted:
        raise RuntimeError("响应缺少加密 data 字段")

    plain = my_decrypt(encrypted)
    try:
        return json.loads(plain)
    except json.JSONDecodeError:
        logger.warning("明文不是 JSON，原样返回字符串")
        return plain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="查策网产业项目分页复现")
    parser.add_argument("--page", type=int, default=1, help="页码，从 1 开始")
    parser.add_argument("--size", type=int, default=20, help="每页条数")
    parser.add_argument("--area", default=DEFAULT_AREA, help="地区字典码")
    parser.add_argument(
        "--preview",
        type=int,
        default=2,
        help="打印前 N 条标题预览",
    )
    args = parser.parse_args(argv)

    try:
        data = fetch_list(page=args.page, size=args.size, area=args.area)
    except Exception:
        return 1

    if isinstance(data, list):
        logger.info("解密成功，条目数=%s", len(data))
        for item in data[: max(0, args.preview)]:
            if isinstance(item, dict):
                print(
                    f"- {item.get('pe_name', '')} | mid={item.get('mid', '')}"
                )
            else:
                print("-", item)
    else:
        logger.info("解密成功，类型=%s", type(data).__name__)
        print(str(data)[:500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
