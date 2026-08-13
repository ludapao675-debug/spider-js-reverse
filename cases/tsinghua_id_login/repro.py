#!/usr/bin/env python3
"""清华统一身份认证 id.tsinghua.edu.cn — SM2 密码本地复现。

依赖: pip install gmssl
用法:
  python repro.py --self-test
  python repro.py <username> <password> [captcha]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any

# 页面 #sm2publicKey 文本（未压缩 04||X||Y，130 hex）
# 实测 2026-07-19 登录页内嵌；若站点轮换公钥，请从页面重新读取。
DEFAULT_SM2_PUBLIC_KEY = (
    "04d0c9e1ae89279fe05b435d63e3eba437bf510e09da5f71558974a19dc59672"
    "4227f08dc2fc6e74bbb9d8b468d4dd5205e9b6793a3bbc48df3fdf219b3ea140e3"
)

LOGIN_URL = "https://id.tsinghua.edu.cn/f/login"
SECURITY_CHECK = "https://id.tsinghua.edu.cn/security_check"


def encrypt_password_sm2(password: str, public_key_hex: str = DEFAULT_SM2_PUBLIC_KEY) -> str:
    """等价 sm2Util.doEncryptStr(pass, publicKey)。

    JS: return "04" + sm2.doEncrypt(pass, publicKey, cipherMode=1)  # C1C3C2
    """
    try:
        from gmssl import sm2
    except ImportError as exc:
        raise SystemExit("缺少 gmssl，请先: pip install gmssl") from exc

    pub = public_key_hex.strip().lower()
    if pub.startswith("04") and len(pub) == 130:
        pub_xy = pub[2:]
    else:
        pub_xy = pub
    cryptor = sm2.CryptSM2(public_key=pub_xy, private_key=None)
    raw = cryptor.encrypt(password.encode("utf-8"))
    if isinstance(raw, str):
        hex_body = raw.lower()
    else:
        hex_body = bytes(raw).hex()
    # 与前端一致：外层补 04 前缀
    if hex_body.startswith("04"):
        return hex_body
    return "04" + hex_body


def fetch_public_key_from_login_html(timeout: float = 15.0) -> str:
    """从登录页 HTML 解析 #sm2publicKey（兜底；优先用页面运行时文本）。"""
    req = urllib.request.Request(LOGIN_URL, headers={"User-Agent": "crypto-hunter-lite/repro"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    marker = 'id="sm2publicKey"'
    idx = html.find(marker)
    if idx < 0:
        raise RuntimeError("登录页未找到 sm2publicKey")
    # <span id="sm2publicKey">HEX</span> 或同类
    gt = html.find(">", idx)
    lt = html.find("<", gt)
    key = html[gt + 1 : lt].strip()
    if not key.startswith("04") or len(key) < 130:
        raise RuntimeError(f"解析到的公钥异常: len={len(key)}")
    return key


def build_login_form(
    username: str,
    password: str,
    *,
    captcha: str = "",
    public_key: str = DEFAULT_SM2_PUBLIC_KEY,
    finger_print: str = "",
    device_name: str = "windows,Chrome/120",
) -> dict[str, str]:
    """组装 POST /security_check 表单字段（password 为 SM2 密文）。"""
    return {
        "username": username,
        "password": encrypt_password_sm2(password, public_key),
        "fingerPrint": finger_print,
        "fingerGenPrint": "",
        "fingerGenPrint3": "",
        "deviceName": device_name,
        "i_captcha": captcha,
    }


def self_test() -> dict[str, Any]:
    """长度/前缀自检（SM2 含随机数，无法逐字节比对浏览器密文）。"""
    pw = "RandPass@Ts2026"
    cipher = encrypt_password_sm2(pw)
    expected_len = 2 + 128 + 64 + len(pw.encode("utf-8")) * 2
    ok = cipher.startswith("04") and len(cipher) == expected_len
    form = build_login_form("thu_rand_20260719", pw, captcha="0000")
    return {
        "ok": ok,
        "cipher_prefix": cipher[:4],
        "cipher_len": len(cipher),
        "expected_len": expected_len,
        "password_field_is_sm2": form["password"].startswith("04"),
        "form_keys": list(form.keys()),
        "sample_cipher_head": cipher[:48],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="清华 id.tsinghua SM2 登录复现")
    parser.add_argument("username", nargs="?", default="")
    parser.add_argument("password", nargs="?", default="")
    parser.add_argument("captcha", nargs="?", default="")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--fetch-key", action="store_true", help="从登录页 HTML 拉公钥")
    parser.add_argument("--print-body", action="store_true", help="打印 urlencoded body")
    args = parser.parse_args(argv)

    if args.self_test:
        result = self_test()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    pubkey = DEFAULT_SM2_PUBLIC_KEY
    if args.fetch_key:
        try:
            pubkey = fetch_public_key_from_login_html()
            print(f"[pubkey] fetched len={len(pubkey)}", file=sys.stderr)
        except Exception as exc:
            print(f"[pubkey] fetch failed: {exc}; use default", file=sys.stderr)

    if not args.username or not args.password:
        parser.print_help()
        return 2

    form = build_login_form(args.username, args.password, captcha=args.captcha, public_key=pubkey)
    payload = {
        "ok": True,
        "endpoint": SECURITY_CHECK,
        "method": "POST",
        "content_type": "application/x-www-form-urlencoded",
        "form": form,
        "note": "password 为 SM2(C1C3C2) 密文；完整登录还需有效 i_captcha 与会话 Cookie",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.print_body:
        print(urllib.parse.urlencode(form))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
