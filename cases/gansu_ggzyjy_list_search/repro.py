# -*- coding: utf-8 -*-
"""甘肃公共资源列表分页协议复现：SM2 加密 POST /ESProjectList/searchByPage。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

BASE = "https://sjfz.ggzyjy.gansu.gov.cn:19002/api/renren-api"
API = "/ESProjectList/searchByPage"
# 前端 sm-crypto 固定公钥（压缩格式 03||X），cipherMode=1 (C1C3C2)
SM2_PUB = "03702057B53C16031D786D9E06D839163F3DD5867E6E161292F61E1340FDF6DE24"
# 前端内嵌私钥，仅用于部分本地解密工具；列表响应实测为明文 JSON
SM2_PRIV = "B8FDD61FD8C115F51C6E23431614A204EE7C59FB2E0C58FFE58F786790793EC4"


def sm2_encrypt_js(plaintext: str) -> str:
    """调用与站点一致的 sm-crypto 生成 04+密文。"""
    repro_dir = Path(__file__).resolve().parent
    script = (
        "const sm2=require('sm-crypto').sm2;"
        f"const pk={SM2_PUB!r};"
        f"const msg={plaintext!r};"
        "process.stdout.write('04'+sm2.doEncrypt(msg,pk,1));"
    )
    try:
        out = subprocess.check_output(
            ["node", "-e", script],
            cwd=str(repro_dir),
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"sm-crypto 加密失败: {exc.stderr.decode('utf-8', 'replace')}"
        ) from exc
    return out.decode("utf-8")


def build_params(
    page: int,
    page_size: int,
    trade_type: str,
    link: str,
    platform_code: str,
    notice_name: str,
) -> dict:
    """与 list-search-6a773d6c.js 中 u.params 对齐。"""
    return {
        "platformCode": platform_code,
        "noticeName": notice_name,
        "tradeType": str(trade_type),
        "queryType": "1",
        "link": link,
        "pageSize": page_size,
        "page": page,
        "important": "",
        "remote": "",
    }


def search_by_page(params: dict, timeout: int = 30) -> dict:
    """发送 encryptedPost 等价请求。"""
    body = sm2_encrypt_js(json.dumps(params, ensure_ascii=False, separators=(",", ":")))
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://sjfz.ggzyjy.gansu.gov.cn:19002",
        "Referer": "https://sjfz.ggzyjy.gansu.gov.cn:19002/",
        "Accept-Language": "zh-CN",
        "tenantCode": "",
    }
    url = BASE + API
    # axios 对 string data 原样发送密文字符串（非再包一层 JSON）
    resp = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=timeout)
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text, "_status": resp.status_code}


def main() -> int:
    parser = argparse.ArgumentParser(description="甘肃交易中心列表分页复现")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--trade-type", default="1")
    parser.add_argument("--link", default="ALL")
    parser.add_argument("--platform-code", default="")
    parser.add_argument("--notice-name", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    params = build_params(
        page=args.page,
        page_size=args.page_size,
        trade_type=args.trade_type,
        link=args.link,
        platform_code=args.platform_code,
        notice_name=args.notice_name,
    )
    print("params:", json.dumps(params, ensure_ascii=False))
    try:
        data = search_by_page(params)
    except Exception as exc:
        print("请求失败:", exc, file=sys.stderr)
        return 1

    print("code:", data.get("code"))
    print("msg:", data.get("msg") or data.get("message"))
    payload = data.get("data") or {}
    if isinstance(payload, dict):
        print("total:", payload.get("total"))
        items = payload.get("list") or []
        print("list_len:", len(items))
        for i, item in enumerate(items[:3]):
            title = (
                item.get("noticeName")
                or item.get("projectName")
                or item.get("title")
                or item.get("tenderProjectName")
            )
            print(f"  [{i}] {title}")
    else:
        print("data preview:", str(data)[:500])

    if args.out:
        Path(args.out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("wrote", args.out)
    return 0 if data.get("code") in (0, "0", 200, "200") else 2


if __name__ == "__main__":
    raise SystemExit(main())
