# -*- coding: utf-8 -*-
"""
B 站 (bilibili) 网页登录接口加密复现
====================================
目标页面: https://passport.bilibili.com/login

逆向结论
--------
1. 密码加密（RSA-1024，非对称）:
   GET  https://passport.bilibili.com/x/passport-login/web/key
   ->   {"code":0,"data":{"hash":"84b96ccb...","key":"-----BEGIN PUBLIC KEY-----..."}}
   - key   : RSA-1024 公钥 PEM（每次请求动态生成）
   - hash  : 16 位十六进制随机串（每次请求动态生成）
   密码加密算法（与前端 JSEncrypt 完全一致）:
   plaintext = hash + password          # hash 前缀拼接，非直接加密 password
   cipher    = RSA/ECB/PKCS1v15(plaintext) -> base64

2. 登录提交:
   POST https://passport.bilibili.com/x/passport-login/web/login
   form: {username, password: RSA密文, keep, challenge, validate, seccode, challenges}
   - challenge/validate/seccode 为空 = 未触发验证码；触发需过滑块 geetest/极验

3. 响应 code:
   - 0      登录成功（返回 SESSDATA/bili_jct/bili_jct 等 cookie）
   - -105   验证码错误（未传验证码时返回；密码加密本身已通过校验）
   - -855   密码错误 / 账号不存在（加密格式错误才会走此分支）

4. 前置条件:
   - 需先访问 https://www.bilibili.com/ 获取 buvid3 cookie（否则 login 报 -105）
   - 风控机制 bili-sc-sdk (WASM) 采集设备指纹(Canvas/Fonts) 经 gaia-gateway 上报，
     但登录关键参数只有 RSA 密码 + geetest 验证码

用法
----
    python repro.py --user test@bilibili.com --pass test123456
    python repro.py --user 13800138000 --pass mypass --show-key   # 查看公钥不登录
"""
import argparse
import base64
import sys

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

BASE = "https://passport.bilibili.com/x/passport-login/web"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"),
    "Referer": "https://passport.bilibili.com/login",
    "Content-Type": "application/x-www-form-urlencoded",
}


def get_key(session: requests.Session) -> dict:
    """获取 RSA 公钥 + hash（每次动态生成）"""
    r = session.get(f"{BASE}/key", headers=HEADERS, timeout=15)
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"getKey 失败: {d}")
    return d["data"]


def rsa_encrypt(plaintext: str, pub_key_pem: str) -> str:
    """RSA/ECB/PKCS1v15 加密 + base64，与 JSEncrypt.encrypt 一致"""
    pub = RSA.import_key(pub_key_pem)
    cipher = PKCS1_v1_5.new(pub)
    enc = cipher.encrypt(plaintext.encode("utf-8"))
    return base64.b64encode(enc).decode()


def login(username: str, password: str) -> dict:
    s = requests.Session()
    # 1) 先访问首页拿 buvid3 cookie
    s.get("https://www.bilibili.com/", headers={
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://www.bilibili.com/",
    }, timeout=15)
    # 2) 获取 RSA 公钥 + hash
    key_data = get_key(s)
    # 3) 加密密码: hash + password
    enc_pwd = rsa_encrypt(key_data["hash"] + password, key_data["key"])
    # 4) 提交登录
    form = {
        "username": username,
        "password": enc_pwd,
        "keep": 0,
        "challenge": "",
        "validate": "",
        "seccode": "",
        "challenges": {},
    }
    r = s.post(f"{BASE}/login", data=form, headers=HEADERS, timeout=15)
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="B 站登录加密复现")
    parser.add_argument("--user", default="test@bilibili.com")
    parser.add_argument("--pass", dest="password", default="test123456")
    parser.add_argument("--show-key", action="store_true", help="仅显示公钥与加密结果，不登录")
    args = parser.parse_args()

    if args.show_key:
        s = requests.Session()
        kd = get_key(s)
        print("hash:", kd["hash"])
        print("key:", kd["key"])
        enc = rsa_encrypt(kd["hash"] + args.password, kd["key"])
        print(f"encrypted({kd['hash']}{args.password}): {enc[:80]}...")
        return

    import json
    try:
        result = login(args.user, args.password)
    except Exception as e:
        print(f"登录异常: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=1)[:800])

    code = result.get("code")
    if code == 0:
        print("[+] 登录成功")
    elif code == -105:
        print("[-] 返回 -105 验证码错误：密码 RSA 加密已通过，需过 geetest 验证码")
    elif code == -855:
        print("[-] 返回 -855 密码错误/账号不存在（若账号正确则检查加密格式）")
    else:
        print(f"[-] 返回 code={code}")


if __name__ == "__main__":
    main()
