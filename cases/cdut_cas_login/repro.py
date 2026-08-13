#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成都理工大学 CAS (cas.paas.cdut.edu.cn) — 登录密码加密与请求本地复现
====================================================================
加密算法：RSA-2048 + PKCS#1 v1.5（JSEncrypt），结果 Base64，再加前缀 __RSA__

  password_field = "__RSA__" + base64( RSA_encrypt(明文密码, 公钥) )

公钥：GET https://cas.paas.cdut.edu.cn/cas/jwt/publicKey  （PEM）
提交：POST /cas/login?service=...  （application/x-www-form-urlencoded）

依赖：仅 Python 标准库（无 pycryptodome / cryptography）。

用法：
  python repro.py                     # 自检：拉公钥 + 加密长度校验
  python repro.py <账号> <密码>       # 组装登录表单字段（不自动提交成功登录）
  python repro.py <账号> <密码> --post  # 真正 POST（需有效账号；失败会回登录页）
"""

from __future__ import annotations

import argparse
import base64
import logging
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("cdut_cas_login")

CAS_ORIGIN = "https://cas.paas.cdut.edu.cn"
PUBLIC_KEY_URL = f"{CAS_ORIGIN}/cas/jwt/publicKey"
DEFAULT_SERVICE = (
    "http://jw.cdut.edu.cn/sso/login.jsp?"
    "targetUrl=base64aHR0cDovL2p3LmNkdXQuZWR1LmNuL0xvZ29uLmRvP21ldGhvZD1sb2dvblNTT2NkbGdkeA=="
)
LOGIN_URL = f"{CAS_ORIGIN}/cas/login?service={urllib.parse.quote(DEFAULT_SERVICE, safe='')}"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 页面实测静态公钥缓存（与 /cas/jwt/publicKey 一致；运行时仍优先在线拉取）
FALLBACK_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApelX/roOn1yUNOiDr/obm/9ez6qmEoq5AoU/GqLUvZdvd4XrBI6cFvKVihT3JjlyqR7ayxsRNAnZDXP1AQ2KWevQrtjBlZ9pAJUONpWRqkODYvVioh67+BoE/SkpOKjxdF9TJydn8OwhSP+ycCTCPTfXXYHJyoKHNBP8KwH99smVN/owCvsUnflMSXdWMPBWnrgaQyHgZWJgzybKLMwKcSeZMuHwMdMC6N0nhkV5RrSUi1XoONRtSwuP34zMU/NFY9v9QOOwTPGW79q9UELqw9mciTZ8GOcJ/DU8Pd/OE8BizgEhOHxBrpRPVhZQVcFp5MjWOQibL5zKwUof6qr7FQIDAQAB
-----END PUBLIC KEY-----"""


# ---------------------------------------------------------------------------
# 标准库 RSA（SubjectPublicKeyInfo PEM → n/e → PKCS#1 v1.5 encrypt）
# ---------------------------------------------------------------------------

def _read_asn1_len(data: bytes, i: int) -> tuple[int, int]:
    first = data[i]
    i += 1
    if first & 0x80 == 0:
        return first, i
    n = first & 0x7F
    return int.from_bytes(data[i : i + n], "big"), i + n


def _parse_asn1_int(data: bytes, i: int) -> tuple[int, int]:
    if data[i] != 0x02:
        raise ValueError("期望 INTEGER")
    i += 1
    ln, i = _read_asn1_len(data, i)
    return int.from_bytes(data[i : i + ln], "big"), i + ln


def parse_spki_pem(pem: str) -> tuple[int, int]:
    """解析 SubjectPublicKeyInfo PEM，返回 (n, e)。"""
    try:
        body = "".join(
            line.strip()
            for line in pem.strip().splitlines()
            if line and not line.startswith("-----")
        )
        der = base64.b64decode(body)
        i = 0
        if der[i] != 0x30:
            raise ValueError("顶层非 SEQUENCE")
        i += 1
        _, i = _read_asn1_len(der, i)
        # AlgorithmIdentifier
        if der[i] != 0x30:
            raise ValueError("缺少 AlgorithmIdentifier")
        i += 1
        aln, i = _read_asn1_len(der, i)
        i += aln
        # BIT STRING wrapping RSAPublicKey
        if der[i] != 0x03:
            raise ValueError("缺少 BIT STRING")
        i += 1
        _, i = _read_asn1_len(der, i)
        if der[i] != 0x00:
            raise ValueError("BIT STRING unused bits 非 0")
        i += 1
        if der[i] != 0x30:
            raise ValueError("RSAPublicKey 非 SEQUENCE")
        i += 1
        _, i = _read_asn1_len(der, i)
        n, i = _parse_asn1_int(der, i)
        e, i = _parse_asn1_int(der, i)
        return n, e
    except Exception as exc:
        logger.exception("解析公钥失败")
        raise ValueError(f"解析公钥失败: {exc}") from exc


def pkcs1_v15_encrypt(plaintext: bytes, n: int, e: int) -> bytes:
    """RSAES-PKCS1-v1_5 加密（与 JSEncrypt 默认一致）。"""
    try:
        k = (n.bit_length() + 7) // 8
        if len(plaintext) > k - 11:
            raise ValueError(f"明文过长: {len(plaintext)} > {k - 11}")
        # PS 必须全非零随机字节
        ps = bytearray()
        while len(ps) < k - len(plaintext) - 3:
            chunk = secrets.token_bytes(k - len(plaintext) - 3 - len(ps))
            ps.extend(b for b in chunk if b != 0)
        em = b"\x00\x02" + bytes(ps) + b"\x00" + plaintext
        m = int.from_bytes(em, "big")
        c = pow(m, e, n)
        return c.to_bytes(k, "big")
    except Exception as exc:
        logger.exception("RSA 加密失败")
        raise RuntimeError(f"RSA 加密失败: {exc}") from exc


def encrypt_password(password: str, public_key_pem: str | None = None) -> str:
    """返回登录表单 password 字段：__RSA__ + base64(密文)。"""
    pem = public_key_pem or FALLBACK_PUBLIC_KEY
    n, e = parse_spki_pem(pem)
    ct = pkcs1_v15_encrypt(password.encode("utf-8"), n, e)
    return "__RSA__" + base64.b64encode(ct).decode("ascii")


def fetch_public_key(timeout: float = 15.0) -> str:
    """在线拉取最新公钥 PEM。"""
    try:
        req = urllib.request.Request(PUBLIC_KEY_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
        if "BEGIN PUBLIC KEY" not in text:
            raise ValueError("响应不是 PEM 公钥")
        return text.strip() + "\n"
    except Exception as exc:
        logger.warning("在线拉取公钥失败，使用内置缓存: %s", exc)
        return FALLBACK_PUBLIC_KEY


# ---------------------------------------------------------------------------
# 登录页表单解析（取 execution 等一次性字段）
# ---------------------------------------------------------------------------

class _FormParser(HTMLParser):
    """只关心 id=fm1 的密码登录表单。"""

    def __init__(self) -> None:
        super().__init__()
        self.in_fm1 = False
        self.depth = 0
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        if tag == "form" and ad.get("id") == "fm1":
            self.in_fm1 = True
            self.depth = 1
            return
        if not self.in_fm1:
            return
        if tag == "form":
            self.depth += 1
        if tag == "input":
            name = ad.get("name") or ""
            if name and name not in self.fields:
                self.fields[name] = ad.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if not self.in_fm1:
            return
        if tag == "form":
            self.depth -= 1
            if self.depth <= 0:
                self.in_fm1 = False


def fetch_login_page(service: str | None = None, timeout: float = 20.0) -> dict[str, Any]:
    """GET 登录页，解析 #fm1 隐藏域与 Set-Cookie。"""
    try:
        login_url = (
            f"{CAS_ORIGIN}/cas/login?service={urllib.parse.quote(service or DEFAULT_SERVICE, safe='')}"
        )
        req = urllib.request.Request(login_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "replace")
            cookies = resp.headers.get_all("Set-Cookie") or []
        parser = _FormParser()
        parser.feed(html)
        cookie_header = "; ".join(
            c.split(";", 1)[0] for c in cookies if c
        )
        return {
            "ok": True,
            "login_url": login_url,
            "fields": parser.fields,
            "cookie": cookie_header,
            "html_len": len(html),
        }
    except Exception as exc:
        logger.exception("拉取登录页失败")
        return {"ok": False, "error": str(exc)}


def build_login_form(
    username: str,
    password: str,
    *,
    public_key_pem: str | None = None,
    page: dict[str, Any] | None = None,
    captcha: str = "",
    remember_me: bool = False,
) -> dict[str, str]:
    """组装与浏览器 #fm1 一致的 POST 表单字段。"""
    page = page or fetch_login_page()
    if not page.get("ok"):
        raise RuntimeError(f"无法获取登录页: {page.get('error')}")
    fields = dict(page.get("fields") or {})
    pem = public_key_pem or fetch_public_key()
    enc = encrypt_password(password, pem)
    data = {
        "username": username,
        "password": enc,
        "captcha": captcha,
        "currentMenu": fields.get("currentMenu") or "1",
        "failN": fields.get("failN") or "0",
        "mfaState": fields.get("mfaState") or "",
        "execution": fields.get("execution") or "",
        "_eventId": fields.get("_eventId") or "submit",
        "geolocation": fields.get("geolocation") or "",
        "fpVisitorId": fields.get("fpVisitorId") or "",
        "trustAgent": fields.get("trustAgent") or "",
    }
    if remember_me:
        data["rememberMe"] = "true"
    return data


def post_login(
    username: str,
    password: str,
    *,
    captcha: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """完整协议：拉公钥 → 拉登录页 → RSA 加密 → POST #fm1。"""
    try:
        pem = fetch_public_key(timeout=timeout)
        page = fetch_login_page(timeout=timeout)
        if not page.get("ok"):
            return page
        form = build_login_form(
            username,
            password,
            public_key_pem=pem,
            page=page,
            captcha=captcha,
        )
        body = urllib.parse.urlencode(form).encode("utf-8")
        headers = {
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": CAS_ORIGIN,
            "Referer": page["login_url"],
            "Cookie": page.get("cookie") or "",
        }
        req = urllib.request.Request(
            page["login_url"],
            data=body,
            headers=headers,
            method="POST",
        )
        # 不自动跟随到教务，便于观察 CAS 响应
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
        try:
            with opener.open(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
                return {
                    "ok": True,
                    "status": getattr(resp, "status", None),
                    "url": resp.geturl(),
                    "password_field_len": len(form["password"]),
                    "password_prefix": form["password"][:7],
                    "execution_len": len(form.get("execution") or ""),
                    "body_preview": text[:500],
                    "looks_like_login_page": ("登录" in text and "password" in text.lower()),
                }
        except urllib.error.HTTPError as http_exc:
            # 302/其它也可能以 HTTPError 抛出
            return {
                "ok": True,
                "status": http_exc.code,
                "url": http_exc.geturl() if hasattr(http_exc, "geturl") else "",
                "password_field_len": len(form["password"]),
                "password_prefix": form["password"][:7],
                "headers": dict(http_exc.headers.items()) if http_exc.headers else {},
                "note": "HTTPError（可能是重定向/鉴权失败）",
            }
    except Exception as exc:
        logger.exception("POST 登录失败")
        return {"ok": False, "error": str(exc)}


def self_test() -> bool:
    """本地闭环：公钥可解析 + 密文长度符合 RSA-2048/JSEncrypt。"""
    pem = fetch_public_key()
    n, e = parse_spki_pem(pem)
    bits = n.bit_length()
    sample = encrypt_password("CdutTest@2026", pem)
    b64 = sample[len("__RSA__") :]
    ct = base64.b64decode(b64)
    ok = (
        bits == 2048
        and e == 65537
        and sample.startswith("__RSA__")
        and len(ct) == 256
        and len(b64) == 344
        and len(sample) == 351
    )
    print(f"[*] 公钥 bits={bits} e={e}")
    print(f"[*] password 字段 len={len(sample)} prefix={sample[:7]!r}")
    print(f"[*] cipher_bytes={len(ct)} b64_len={len(b64)}")
    print(f"[*] sample={sample[:48]}...")
    print(f"[*] self_test={'PASS' if ok else 'FAIL'}")
    # 再确认登录页能解析到 execution
    page = fetch_login_page()
    exec_ok = bool(page.get("ok") and (page.get("fields") or {}).get("execution"))
    print(f"[*] login_page execution={'OK' if exec_ok else 'MISSING'} html_len={page.get('html_len')}")
    return ok and exec_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="成都理工 CAS 登录请求本地复现")
    parser.add_argument("username", nargs="?", default="")
    parser.add_argument("password", nargs="?", default="")
    parser.add_argument("--captcha", default="", help="图形验证码（failN>=3 时需要）")
    parser.add_argument("--post", action="store_true", help="真正发起 POST（默认只组装字段）")
    parser.add_argument("--self-test", action="store_true", help="仅跑自检")
    args = parser.parse_args(argv)

    if args.self_test or (not args.username and not args.password):
        return 0 if self_test() else 1

    pem = fetch_public_key()
    page = fetch_login_page()
    form = build_login_form(
        args.username,
        args.password,
        public_key_pem=pem,
        page=page,
        captcha=args.captcha,
    )
    print("[*] POST 字段已组装：")
    for k, v in form.items():
        if k == "password":
            print(f"    {k} = {v[:24]}...(len={len(v)})")
        elif k == "execution":
            print(f"    {k} = {v[:48]}...(len={len(v)})")
        else:
            print(f"    {k} = {v!r}")

    if args.post:
        result = post_login(args.username, args.password, captcha=args.captcha)
        print("[*] POST 结果：", result)
        return 0 if result.get("ok") else 1

    print("[*] 未传 --post，仅完成加密参数与表单组装（协议复现核心）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
