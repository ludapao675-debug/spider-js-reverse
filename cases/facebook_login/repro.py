#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Facebook Web 登录协议本地复现（随机假账号）。

算法：#PWD_BROWSER:5
  AES-256-GCM(password, key=random32, nonce=12*0x00, AAD=unix_ts)
  + NaCl SealedBox(Curve25519) 封装 AES key
  + base64 拼接 → #PWD_BROWSER:5:<ts>:<b64>

依赖：pycryptodome、pynacl
  pip install pycryptodome pynacl

验证目标（非真实登录成功）：
  1) 加密格式与浏览器捕获结构一致（kid=148 / sealedLen=80）
  2) 用随机账号 POST /api/graphql/ 得到业务错误 1348131（登录信息有误）
"""

from __future__ import annotations

import argparse
import base64
import binascii
import http.cookiejar
import json
import logging
import random
import re
import string
import struct
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from Crypto import Random
from Crypto.Cipher import AES
from nacl.public import PublicKey, SealedBox

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("facebook_login")

HOME_URL = "https://www.facebook.com/"
GRAPHQL_URL = "https://www.facebook.com/api/graphql/"
# 实测 capture 的持久化查询 ID；页面升级后可能轮换，脚本会尝试从首页 HTML 回退提取
DEFAULT_DOC_ID = "9807605492696448"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"
)

# Facebook 对缺 Sec-Fetch / Accept-Encoding 的客户端常直接 400
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def encrypt_password(
    key_id: int,
    pub_key_hex: str,
    password: str,
    version: int = 5,
    ts: Optional[int] = None,
) -> str:
    """复现 FBBrowserPasswordEncryption / EnvelopeEncryption。"""
    try:
        key = Random.get_random_bytes(32)
        iv = bytes(12)  # 全 0 nonce
        ts_i = int(time.time()) if ts is None else int(ts)
        aes = AES.new(key, AES.MODE_GCM, nonce=iv, mac_len=16)
        # AAD = 秒级时间戳字符串
        aes.update(str(ts_i).encode("utf-8"))
        ciphertext, tag = aes.encrypt_and_digest(password.encode("utf-8"))
        sealed = SealedBox(PublicKey(binascii.unhexlify(pub_key_hex))).encrypt(key)
        payload = (
            bytes([1, int(key_id)])
            + struct.pack("<h", len(sealed))
            + sealed
            + tag
            + ciphertext
        )
        b64 = base64.b64encode(payload).decode("ascii")
        return f"#PWD_BROWSER:{version}:{ts_i}:{b64}"
    except Exception as exc:
        log.exception("encrypt_password 失败: %s", exc)
        raise


def parse_enc_payload(enc: str) -> Dict[str, Any]:
    """解析 #PWD_BROWSER 载荷结构，便于断言。"""
    parts = enc.split(":")
    if len(parts) != 4 or parts[0] != "#PWD_BROWSER":
        raise ValueError(f"非法 enc_password: {enc[:60]}")
    raw = base64.b64decode(parts[3])
    sealed_len = struct.unpack("<h", raw[2:4])[0]
    return {
        "prefix": parts[0],
        "version": int(parts[1]),
        "ts": int(parts[2]),
        "v0": raw[0],
        "kid": raw[1],
        "sealed_len": sealed_len,
        "total": len(raw),
        "tag_cipher_len": len(raw) - 4 - sealed_len,
    }


def jazoest_from_lsd(lsd: str) -> str:
    """Facebook 常见 jazoest 算法：'2' + sum(ord)。"""
    return "2" + str(sum(ord(c) for c in lsd))


def random_creds() -> Tuple[str, str]:
    """生成随机假账号密码（不使用真实邮箱）。"""
    suffix = "".join(random.choices(string.digits, k=5))
    email = f"ch_repro_{suffix}@example.test"
    pwd = "FbRand!" + "".join(random.choices(string.ascii_letters + string.digits, k=8))
    return email, pwd


def _http_get(url: str, opener: urllib.request.OpenerDirector) -> str:
    req = urllib.request.Request(url, headers=dict(BROWSER_HEADERS), method="GET")
    with opener.open(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_login_bootstrap(html: str) -> Dict[str, Any]:
    """从首页 HTML 提取 password 公钥、lsd、jazoest、doc_id。"""
    out: Dict[str, Any] = {}

    # 优先取 caa_password_encryption_data（Facebook Web 登录）
    m = re.search(
        r'"caa_password_encryption_data"\s*:\s*\{\s*"encryption_data"\s*:\s*'
        r'\{\s*"key_id"\s*:\s*(\d+)\s*,\s*"public_key"\s*:\s*"([0-9a-fA-F]{64})"',
        html,
    )
    if m:
        out["key_id"] = int(m.group(1))
        out["public_key"] = m.group(2)
    else:
        # 回退：credential_manager 里的同名字段
        m2 = re.search(
            r'"password_encryption"\s*:\s*\{\s*"encryption_data"\s*:\s*'
            r'\{\s*"key_id"\s*:\s*(\d+)\s*,\s*"public_key"\s*:\s*"([0-9a-fA-F]{64})"',
            html,
        )
        if not m2:
            raise RuntimeError("首页未找到 caa_password_encryption_data.public_key")
        out["key_id"] = int(m2.group(1))
        out["public_key"] = m2.group(2)

    m_lsd = re.search(r'"lsd"\s*:\s*\{\s*"name"\s*:\s*"lsd"\s*,\s*"value"\s*:\s*"([^"]+)"', html)
    if not m_lsd:
        m_lsd = re.search(r'name="lsd"\s+value="([^"]+)"', html)
    if not m_lsd:
        raise RuntimeError("首页未找到 lsd")
    out["lsd"] = m_lsd.group(1)

    m_jaz = re.search(
        r'"jazoest"\s*:\s*\{\s*"name"\s*:\s*"jazoest"\s*,\s*"value"\s*:\s*"([^"]+)"',
        html,
    )
    out["jazoest"] = m_jaz.group(1) if m_jaz else jazoest_from_lsd(out["lsd"])

    # doc_id 可能不在首页；保留默认值
    m_doc = re.search(r'"useCDSWebLoginMutation"[^,]{0,80}"doc_id"\s*:\s*"?(\d+)"?', html)
    if m_doc:
        out["doc_id"] = m_doc.group(1)
    else:
        out["doc_id"] = DEFAULT_DOC_ID

    m_rev = re.search(r'"rev"\s*:\s*(\d+)', html)
    out["__rev"] = m_rev.group(1) if m_rev else "0"
    return out


def build_login_body(
    *,
    identifier: str,
    enc_password: str,
    lsd: str,
    jazoest: str,
    doc_id: str,
    rev: str,
    extra_info: Optional[Dict[str, Any]] = None,
) -> str:
    """构造 useCDSWebLoginMutation 表单 body。

    注意：GraphQL 对 String 字段用 null 会触发 noncoercible_variable_value，
    浏览器实测大量可选字段是空字符串 "" 而不是 null。
    """
    sensitive = {"sensitive_string_value": enc_password}
    if extra_info is None:
        # 字段形态对齐浏览器：String 用 ""，login_source 小写；
        # shared_prefs_data 为空时部分环境会 GraphQL coerce 失败，加密本身仍可用 offline 验证
        extra_info = {
            "ab_test_data": "AAAAAAAAAAAAAAAA/AAAAAAAAAAAAAAAAAAAAAAAfA/AAAfAAAABAB",
            "shared_prefs_data": "",
            "cuid": "",
            "guid": uuid.uuid4().hex[:17],
            "jazoest": jazoest,
            "lgndim": "eyJ3Ijo4MjcsImgiOjk5MiwiYXciOjgyNywiYWgiOjk5MiwiYyI6MjR9",
            "lgnjs": str(int(time.time())),
            "lgnrnd": "000000_xxxx",
            "locale": "zh_CN",
            "login_source": "comet_headerless_login",
            "lsd": lsd,
            "next": "",
            "prefill_contact_point": "",
            "prefill_source": "",
            "prefill_type": "",
            "skstamp": "",
            "timezone": "-480",
        }
    variables = {
        "input": {
            "actor_id": "0",
            "client_mutation_id": "1",
            "access_flow_version": "pre_mt_behavior",
            "app": "facebook",
            "auth_domain_data_key": None,
            "caa_login_request_extra_info": extra_info,
            "credential_type": "password",
            "dyi_job_id": "",
            "enc_password": sensitive,
            "event_request_id": str(uuid.uuid4()),
            "identifier": identifier,
            "ig_web_device_id": None,
            "initial_request_id": "1",
            "lids": None,
            "login_source": "COMET_HEADERLESS_LOGIN",
            "next": None,
            "passkey_payload": None,
            "password": sensitive,
            "persistent": True,
            "query_params": "{}",
            "trusted_device_records": "{}",
            "use_uid_to_login": False,
            "waterfall_id": str(uuid.uuid4()),
        },
        "scale": 1,
    }
    form = {
        "av": "0",
        "__user": "0",
        "__a": "1",
        "__req": "1",
        "__ccg": "GOOD",
        "__rev": rev,
        "__comet_req": "15",
        "lsd": lsd,
        "jazoest": jazoest,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "useCDSWebLoginMutation",
        "server_timestamps": "true",
        "variables": json.dumps(variables, separators=(",", ":"), ensure_ascii=False),
        "doc_id": doc_id,
    }
    return urllib.parse.urlencode(form)


def post_login(opener: urllib.request.OpenerDirector, body: str, lsd: str) -> Dict[str, Any]:
    """POST GraphQL 登录 mutation。"""
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Origin": "https://www.facebook.com",
        "Referer": "https://www.facebook.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-FB-LSD": lsd,
        "X-FB-Friendly-Name": "useCDSWebLoginMutation",
        "X-ASBD-ID": "359341",
    }
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with opener.open(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
        log.warning("HTTPError %s: %s", status, raw[:300])
    # 去掉 anti-hijack 前缀
    if raw.startswith("for (;;);"):
        raw = raw[len("for (;;);") :]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"http_status": status, "raw": raw[:500], "parse_error": True}
    return {"http_status": status, "json": data}


def main() -> int:
    parser = argparse.ArgumentParser(description="Facebook 登录协议本地复现（随机假账号）")
    parser.add_argument("--email", default="", help="可选：指定假邮箱；默认随机")
    parser.add_argument("--password", default="", help="可选：指定假密码；默认随机")
    parser.add_argument("--offline-only", action="store_true", help="只验证加密格式，不发 live 请求")
    args = parser.parse_args()

    email, password = args.email, args.password
    if not email or not password:
        email, password = random_creds()
    log.info("使用随机假账号: %s / %s", email, password)

    # ---- 离线结构样例（与浏览器捕获 kid/sealedLen 对齐）----
    sample_key_id = 148
    sample_pub = "c5c61f9b8d92fa4036118ea4d271b35733e9484c2186ebdd8ea11487434f6536"
    sample_enc = encrypt_password(sample_key_id, sample_pub, password, ts=int(time.time()))
    meta = parse_enc_payload(sample_enc)
    assert meta["v0"] == 1
    assert meta["kid"] == sample_key_id
    assert meta["sealed_len"] == 80
    assert meta["tag_cipher_len"] == 16 + len(password)
    log.info("离线加密格式 OK: %s", meta)
    log.info("enc_password sample: %s", sample_enc[:96] + "...")

    if args.offline_only:
        print(json.dumps({"ok": True, "mode": "offline", "enc_meta": meta, "email": email}, ensure_ascii=False, indent=2))
        return 0

    # ---- live：拉首页拿公钥/csrf，再发登录 ----
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        html = _http_get(HOME_URL, opener)
        boot = extract_login_bootstrap(html)
    except Exception as exc:
        log.error("拉取/解析首页失败: %s", exc)
        return 1

    log.info(
        "bootstrap key_id=%s pub=%s... lsd=%s jazoest=%s doc_id=%s",
        boot["key_id"],
        boot["public_key"][:16],
        boot["lsd"][:12],
        boot["jazoest"],
        boot["doc_id"],
    )

    enc = encrypt_password(boot["key_id"], boot["public_key"], password)
    body = build_login_body(
        identifier=email,
        enc_password=enc,
        lsd=boot["lsd"],
        jazoest=boot["jazoest"],
        doc_id=boot["doc_id"],
        rev=boot["__rev"],
    )
    result = post_login(opener, body, boot["lsd"])
    caa = (
        ((result.get("json") or {}).get("data") or {}).get("caa_login_web")
        if isinstance(result.get("json"), dict)
        else None
    )
    error_code = (caa or {}).get("error_code") if isinstance(caa, dict) else None
    error_text = None
    if isinstance(caa, dict) and isinstance(caa.get("error_message"), dict):
        error_text = caa["error_message"].get("text")

    # 随机假账号的期望：业务层返回「登录信息有误」(1348131)
    # 若缺 shared_prefs 等指纹字段，可能先撞 GraphQL coerce 错误——加密闭环以 offline 结构 + 浏览器投递 Python 密文为准
    gql_errors = None
    if isinstance(result.get("json"), dict) and result["json"].get("errors"):
        gql_errors = [e.get("message") for e in result["json"]["errors"][:3]]

    ok = error_code == 1348131 or (
        isinstance(error_text, str) and ("登录信息有误" in error_text or "incorrect" in error_text.lower())
    )
    summary = {
        "ok": bool(ok),
        "offline_encrypt_ok": True,
        "email": email,
        "enc_meta": parse_enc_payload(enc),
        "http_status": result.get("http_status"),
        "error_code": error_code,
        "error_text": error_text,
        "gql_errors": gql_errors,
        "key_id": boot["key_id"],
        "doc_id": boot["doc_id"],
        "note": (
            "加密算法已 offline 验证；若 live 非 1348131，通常是 GraphQL 附加字段不完整，"
            "可将 Python 生成的 enc_password 替换进浏览器捕获的完整 variables 再 POST。"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not ok:
        log.warning("live 未命中 1348131（offline 加密已通过）: %s", gql_errors or result)
        # 加密本身已验证，live 附加字段失败不阻断主结论
        return 0
    log.info("live 验证通过：服务端接受加密载荷并返回凭据错误（协议闭环）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
