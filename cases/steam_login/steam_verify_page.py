# -*- coding: utf-8 -*-
"""
闭环验证：用 self-generated 私钥解密【页面 RSA.encrypt】产出的真实密文，确认还原为原始明文。

逻辑：
  - 页面用我们生成的公钥 (n, e) 加密 "STEAM_REPRO_PW_2026"，返回 base64 密文 c1/c2
  - 用对应私钥 d 做 RSA 解密：m = c^d mod n
  - 剥离 PKCS#1 v1.5 填充，提取明文
  - 若明文 == 原密码，则证明【页面 RSA.encrypt】== 标准 RSA PKCS#1 v1.5 == 本仓库 rsa_encrypt_steam 的算法

密文取自实测：ch_page_run_js 在 Steam 登录页调用 RSA.encrypt('STEAM_REPRO_PW_2026', RSA.getPublicKey(n_hex, e_hex))
"""
import base64
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.join(HERE, ".steam_key.json")

# 页面真实密文（实测取得，对应 n_hex 见 .steam_key.json）
C1 = "xDG2S/cAIxN2b7W5JIHdg1iRRuyT4wJ78pEA5kx8FRLOEsagOFG0PBNzUW58ELvoK8JH4qx6D8KIE4b3zi8zpGg8G21aZjkJQdknBDd+UP1EyssvGxLeC5YH61qPfIIwvyScvHCA/5slPVqXAZrhZyydLjk+u1mlZi8A/NVSreA="
C2 = "a3JEjZaEy+DrUJKgtHMYbnkRB7yYxlayCSjFCTfhszlwihxxG7iWqAU/280+uixKx1pT/AnDnU/XQIMI1Fc6mBeCE+n/IhQBi1r4Cylw7XurC9M0Gp+1l55TUpcCCl43ftnQW8nVgxIj4O9YCtG+fSnAmOdvU3uP677NBu/C67k="
EXPECTED = b"STEAM_REPRO_PW_2026"


def decrypt_and_strip(cipher_b64: str, n: int, d: int, expected: bytes) -> dict:
    c = int.from_bytes(base64.b64decode(cipher_b64), "big")
    m = pow(c, d, n)  # 等价 RSA 私钥解密
    key_size = (n.bit_length() + 7) >> 3
    buf = m.to_bytes(key_size, "big")
    valid = buf[0] == 0 and buf[1] == 2
    idx = 2
    while idx < key_size and buf[idx] != 0:
        idx += 1
    plaintext = buf[idx + 1:] if idx < key_size else b""
    match = valid and plaintext == expected
    return {
        "valid_pkcs1v15": valid,
        "plaintext": plaintext.decode("latin-1", "replace"),
        "match": match,
    }


def main():
    with open(KEY_PATH, "r", encoding="utf-8") as f:
        k = json.load(f)
    n, d = k["n"], k["d"]
    r1 = decrypt_and_strip(C1, n, d, EXPECTED)
    r2 = decrypt_and_strip(C2, n, d, EXPECTED)
    print("[页面密文 c1]", r1)
    print("[页面密文 c2]", r2)
    ok = r1["match"] and r2["match"]
    print("[闭环结论]", "PASS —— 页面 RSA.encrypt == 标准 RSA PKCS#1 v1.5，本仓库复现等价" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
