#!/usr/bin/env python3
"""Steam 登录密码加密 —— 本地复现脚本 (crypto-hunter-lite)

识别结论 (ch_detect_login_encryption 误判为 unknown, 实为 RSA):
  - 加密库: store.akamai.steamstatic.com/public/shared/javascript/crypto/rsa.js
            + crypto/jsbn.js  (基于 jsbn 的 RSA 实现, 全局名 `RSA`)
  - 加密入口: login.js -> CLoginPromptManager.OnRSAKeyResponse
        pubKey = RSA.getPublicKey(publickey_mod, publickey_exp)
        password = password.replace(/[^\\x00-\\x7F]/g, '')   # 去除非 ASCII
        encryptedPassword = RSA.encrypt(password, pubKey)
  - RSA.encrypt 算法: PKCS#1 v1.5 填充 (pkcs1pad2) -> m^e mod n -> Base64 输出

等价性验证 (闭环, 已通过):
  在 Steam 登录页内调用 RSA.encrypt(明文, 公钥) 得到 Base64 密文,
  用对应的本地 RSA 私钥解密, 还原出原始明文 (decrypt==plain: True, 128 字节)。
  => 本地实现与页面内 RSA.encrypt 完全等价。

本地复现步骤:
  1. 从 /login/getrsakey/ 取公钥 (publickey_mod / publickey_exp, 均为十六进制)
  2. 密码去除非 ASCII 字符
  3. RSA-1024 + PKCS#1 v1.5 加密 -> Base64 即为登录请求体 password 字段值

注: getrsakey 接口受 Steam/Akamai 频率限制与风控, 直接用脚本外部请求可能
    被重定向回登录页 HTML。 解决: 从浏览器 DevTools Network 面板抓取一次
    getrsakey 的真实 JSON 响应, 把 publickey_mod/exp 填到下方即可。
"""
import base64
import re
import sys

from cryptography.hazmat.primitives.asymmetric import rsa, padding


def encrypt_steam_password(password: str, publickey_mod: str, publickey_exp: str) -> str:
    """复现 Steam 登录密码加密, 返回 Base64 密文。

    Args:
        password: 明文密码
        publickey_mod: getrsakey 返回的 publickey_mod (十六进制字符串)
        publickey_exp: getrsakey 返回的 publickey_exp (十六进制字符串, 通常 010001=65537)
    """
    n = int(str(publickey_mod), 16)
    e = int(str(publickey_exp), 16)
    pub = rsa.RSAPublicNumbers(e, n).public_key()
    # 与 login.js 一致: 去除非 ASCII 字符
    pw = re.sub(r'[^\x00-\x7F]', '', password)
    ct = pub.encrypt(pw.encode('ascii'), padding.PKCS1v15())
    return base64.b64encode(ct).decode('ascii')


def fetch_rsakey(username: str, session_cookies: dict | None = None) -> dict:
    """从 Steam 获取 RSA 公钥。受 Akamai 风控时可能返回 HTML 而非 JSON。

    建议: 优先用浏览器页面内请求或手动从 DevTools 抓取真实 JSON。
    """
    import httpx
    sess = httpx.Client(timeout=25, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120 Safari/537.36"})
    if session_cookies:
        sess.cookies.update(session_cookies)
    sess.get("https://store.steampowered.com/login/?l=schinese")
    r = sess.post("https://store.steampowered.com/login/getrsakey/",
                  data={"username": username},
                  headers={"Referer": "https://store.steampowered.com/login/?l=schinese",
                            "X-Requested-With": "XMLHttpRequest",
                            "Accept": "application/json, text/javascript, */*; q=0.01"})
    try:
        return r.json()
    except Exception:
        raise RuntimeError("getrsakey 返回非 JSON (Steam/Akamai 风控), body 前 200 字符:\n"
                           + r.text[:200])


if __name__ == '__main__':
    # ===== 把真实 getrsakey 返回的公钥填到这里 =====
    PUBLICKEY_MOD = sys.argv[1] if len(sys.argv) > 1 else "<publickey_mod_from_getrsakey>"
    PUBLICKEY_EXP = sys.argv[2] if len(sys.argv) > 2 else "010001"
    PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "MyTestPass!2026"

    if PUBLICKEY_MOD.startswith("<"):
        print("[!] 未提供真实公钥。请先获取 getrsakey 的 publickey_mod/exp:")
        print("    python cases/steam_login/steam_login_repro.py <publickey_mod> <publickey_exp> <password>")
        print("    (publickey_exp 默认 010001=65537)")
        print("    获取方式: 浏览器 DevTools -> Network -> 触发登录时抓 /login/getrsakey/ 响应")
        sys.exit(2)

    enc = encrypt_steam_password(PASSWORD, PUBLICKEY_MOD, PUBLICKEY_EXP)
    print("encrypted_password (Base64, 即登录请求 password 字段):")
    print(enc)
