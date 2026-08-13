# -*- coding: utf-8 -*-
"""
闲鱼 goofish 密码登录本地协议复现（测试账号）
==========================================
1) RSA-1024 PKCS#1 v1.5 加密 password -> password2（hex 256）
2) POST passport.goofish.com/newlogin/login.do

用法:
  python login_repro.py
  python login_repro.py --login-id test_user_xxx --password RandPwd!234
  python login_repro.py --no-post   # 只生成 password2，不发请求
"""

from __future__ import annotations

import argparse
import json
import secrets
import string
import sys
import urllib.error
import urllib.request
from pathlib import Path

# 同目录加密实现
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rsa_password_encrypt import EXPONENT, MODULUS_HEX, encrypt_password  # noqa: E402

LOGIN_URL = (
    "https://passport.goofish.com/newlogin/login.do"
    "?appName=xianyu&fromSite=77"
)


def random_login_id() -> str:
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    return f"test_xy_{suffix}"


def random_password() -> str:
    # 含大小写+数字+符号，避免过短被前端校验拦
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "Tp" + "".join(secrets.choice(alphabet) for _ in range(10))


def build_login_body(login_id: str, password2: str, umid_token: str = "") -> dict:
    """最小可发请求体。真实浏览器还会带 ua/jsVersion/滑块等风控字段。"""
    body = {
        "loginId": login_id,
        "password2": password2,
        "keepLogin": False,
        "appName": "xianyu",
        "appEntrance": "web",
        "fromSite": "77",
    }
    if umid_token:
        body["umidToken"] = umid_token
    return body


def post_login(body: dict, timeout: float = 20.0) -> tuple[int, str, dict]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        LOGIN_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json",
            "Origin": "https://passport.goofish.com",
            "Referer": "https://passport.goofish.com/mini_login.htm?appName=xianyu&fromSite=77",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"_raw": raw[:2000]}
    return status, raw, parsed if isinstance(parsed, dict) else {"_value": parsed}


def main() -> int:
    parser = argparse.ArgumentParser(description="goofish login local repro (test credentials)")
    parser.add_argument("--login-id", default="", help="测试账号；空则随机生成")
    parser.add_argument("--password", default="", help="测试密码；空则随机生成")
    parser.add_argument("--umid-token", default="", help="可选 umidToken")
    parser.add_argument("--seed", type=int, default=None, help="确定性 PKCS#1 填充 seed")
    parser.add_argument("--no-post", action="store_true", help="只加密不发 POST")
    args = parser.parse_args()

    login_id = args.login_id.strip() or random_login_id()
    password = args.password or random_password()
    password2, block = encrypt_password(password, seed=args.seed)

    print("=== goofish 登录本地复现（随机/测试账号）===")
    print("loginId     :", login_id)
    print("password    :", password)
    print("password2   :", password2)
    print("len(hex)    :", len(password2), "(expect 256)")
    print("block[0:2]  :", block[:2].hex(), "(expect 0002)")
    print("modulus bits:", int(MODULUS_HEX, 16).bit_length())
    print("exponent    :", EXPONENT)
    print("endpoint    :", LOGIN_URL)

    if args.no_post:
        print("\n[--no-post] 跳过 HTTP")
        return 0

    body = build_login_body(login_id, password2, umid_token=args.umid_token)
    print("\n--- POST body ---")
    print(json.dumps(body, ensure_ascii=False, indent=2))

    status, raw, parsed = post_login(body)
    print("\n--- HTTP", status, "---")
    # 测试账号预期失败；关注协议是否被接受（JSON 业务码而非网关 4xx）
    preview = json.dumps(parsed, ensure_ascii=False, indent=2)
    if len(preview) > 2500:
        preview = preview[:2500] + "\n...[truncated]"
    print(preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
