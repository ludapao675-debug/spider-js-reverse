#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阅文通行证登录协议本地复现（假账号）。

加密：RSA-1024 / PKCS#1 v1.5，JSBN 输出 hex（不是 JSEncrypt/base64）。
  密文 = hex(RSA_encrypt(utf8(password), n=modulus, e=0x10001))
  长度 = 256 hex

提交：JSONP GET https://ptlogin.yuewen.com/login/login
成功标准：本地 JSONP 的 code/message 与网页 LoginV1.loginCallback 一致。
PKCS#1 随机填充，密文字节不可比对。不做真实账号登录。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

PAGE_URL = "https://passport.yuewen.com/yuewen.html"
LOGIN_URL = "https://ptlogin.yuewen.com/login/login"
JSONP_CB = "ywLoginCb"

# LoginV1.init 内联公钥（活体以 HTML 解析为准）
FALLBACK_MODULUS = (
    "CC11740869A1B1BB93F18A872196C5F5AA0FDB48D4D60C70938E99C95AE83F02"
    "A67EF4D2E2ADAE09BAB169ED1E1AE50A31170163B36B9C742843A72BC30CD3D4"
    "2D51033CFA2A3BD6CF1A9C331A0D6054AB3DEF984B6C4B5B28F26E57A300FE6A"
    "49BDFF1111299F9784177F8DFFE25B2AED2EC68B0467E98319CD94B54E8F895F"
)
EXPONENT = 0x10001

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 2026-08-13 网页 LoginV1.loginCallback 对假账号的返回（RSA hex 路径）
PAGE_FAKE_ACCOUNT = {
    "code": 72141,
    "message": "账号或密码错误，请重新输入",
}
# 明文密码走另一条错误码，用来证明必须 RSA hex
PLAINTEXT_CODE = -11016

INIT_RE = re.compile(r"LoginV1\.init\((\{.*?\})\)\s*;", re.S)
JSONP_RE = re.compile(r"^[^(]+\((.*)\)\s*;?\s*$", re.S)


def encrypt_password(password: str, modulus_hex: str = FALLBACK_MODULUS) -> str:
    key = RSA.construct((int(modulus_hex, 16), EXPONENT))
    return PKCS1_v1_5.new(key).encrypt(password.encode("utf-8")).hex()


def parse_init(html: str) -> dict[str, Any]:
    m = INIT_RE.search(html)
    if not m:
        raise RuntimeError("LoginV1.init 未出现在登录页 HTML")
    return json.loads(m.group(1))


def parse_jsonp(text: str) -> dict[str, Any]:
    m = JSONP_RE.search(text.strip())
    if not m:
        raise RuntimeError("不是 JSONP: " + text[:200])
    payload = json.loads(m.group(1))
    if not isinstance(payload, dict):
        raise RuntimeError("JSONP 不是对象")
    return payload


def fetch_page(session: requests.Session) -> dict[str, Any]:
    r = session.get(
        PAGE_URL,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        timeout=20,
    )
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    cfg = parse_init(r.text)
    if not cfg.get("ywtoken") or not cfg.get("modulus"):
        raise RuntimeError("LoginV1.init 缺 ywtoken/modulus")
    return cfg


def login_jsonp(
    session: requests.Session,
    cfg: dict[str, Any],
    username: str,
    password: str,
    *,
    encrypt: bool = True,
    auto: int = 0,
    code: str = "",
    sessionkey: str = "",
) -> tuple[str, dict[str, Any]]:
    modulus = str(cfg.get("modulus") or FALLBACK_MODULUS)
    password_field = encrypt_password(password, modulus) if encrypt else password
    params = {
        "appId": cfg.get("appId", 37),
        "areaId": cfg.get("areaId", 1),
        "source": cfg.get("source") or "",
        "returnurl": cfg.get("returnUrl") or "",
        "version": cfg.get("version") or "",
        "imei": cfg.get("imei") or "",
        "qimei": cfg.get("qimei") or "",
        "target": cfg.get("target") or "top",
        "ticket": cfg.get("ticket", 0),
        "autotime": cfg.get("autoTime", 14),
        "jumpdm": cfg.get("jumpdm") or "yuewen",
        "ajaxdm": cfg.get("ajaxdm") or "yuewen",
        "auto": auto,
        "sdkversion": cfg.get("sdkversion") or "",
        "ywtoken": cfg["ywtoken"],
        "username": username + str(cfg.get("loginPostfix") or ""),
        "password": password_field,
        "code": code,
        "sessionkey": sessionkey,
        "method": JSONP_CB,
        "format": "jsonp",
        "callback": JSONP_CB,
    }
    r = session.get(
        LOGIN_URL,
        params=params,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": PAGE_URL,
        },
        timeout=20,
    )
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text, parse_jsonp(r.text)


def self_check(modulus_hex: str = FALLBACK_MODULUS) -> None:
    a = encrypt_password("user123Pass5678", modulus_hex)
    b = encrypt_password("user123Pass5678", modulus_hex)
    n_bits = int(modulus_hex, 16).bit_length()
    assert n_bits == 1024, n_bits
    assert len(a) == 256 and len(b) == 256, (len(a), len(b))
    assert a != b
    assert all(c in "0123456789abcdef" for c in a)
    print("[ok] RSA-1024 PKCS#1 v1.5 hex len=256, two calls differ")


def fingerprint(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "code": payload.get("code"),
        "message": payload.get("message") or "",
        "nextAction": payload.get("nextAction", data.get("nextAction")),
    }


def assert_same_as_page(local: dict[str, Any], page: dict[str, Any], label: str) -> None:
    lf, pf = fingerprint(local), fingerprint(page)
    print(f"[{label} page]", json.dumps(pf, ensure_ascii=False))
    print(f"[{label} local]", json.dumps(lf, ensure_ascii=False))
    if lf["code"] != pf["code"] or lf["message"] != pf["message"]:
        raise SystemExit(
            f"[fail] 与网页不一致: local={lf} page={pf}"
        )
    print(f"[ok] {label} code/message 与网页一致")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default="ch_probe_user")
    ap.add_argument("--password", default="user123Pass5678")
    ap.add_argument(
        "--page-json",
        default="",
        help="网页 LoginV1.loginCallback 的 JSON 字符串",
    )
    ap.add_argument(
        "--page-json-file",
        default="",
        help="网页 LoginV1.loginCallback 的 JSON 文件",
    )
    ap.add_argument("--self-check-only", action="store_true")
    args = ap.parse_args()

    self_check()
    if args.self_check_only:
        return

    session = requests.Session()
    cfg = fetch_page(session)
    print("[*] ywtoken =" + str(cfg["ywtoken"])[:24] + "...")
    print("[*] modulus bits =", int(str(cfg["modulus"]), 16).bit_length())

    raw, payload = login_jsonp(session, cfg, args.username, args.password, encrypt=True)
    print("[*] rsa jsonp =", json.dumps(payload, ensure_ascii=False)[:400])
    if payload.get("code") in (0, "0"):
        raise SystemExit("[fail] 假账号不应登录成功")

    if args.page_json_file:
        page = json.loads(Path(args.page_json_file).read_text(encoding="utf-8"))
    elif args.page_json:
        page = json.loads(args.page_json)
    else:
        page = dict(PAGE_FAKE_ACCOUNT)
    assert_same_as_page(payload, page, "rsa")

    cfg2 = fetch_page(session)
    _, plain = login_jsonp(
        session, cfg2, args.username, args.password, encrypt=False
    )
    print("[*] plain jsonp =", json.dumps(plain, ensure_ascii=False)[:300])
    if fingerprint(plain) == fingerprint(payload):
        raise SystemExit("[fail] 明文密码与 RSA 路径返回相同，协议未区分")
    if plain.get("code") != PLAINTEXT_CODE:
        print("[warn] 明文路径 code 不是 -11016，实际", plain.get("code"))
    else:
        print("[ok] 负向：明文密码走 -11016，与网页 RSA 路径不同")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print("[fail]", type(exc).__name__, exc)
        sys.exit(1)
