# -*- coding: utf-8 -*-
"""
Steam 登录密码加密 —— 本地复现（纯 Python，无需浏览器/第三方库）。

算法结论（源码取证自 store.steampowered.com/login.js + crypto/rsa.js + crypto/jsbn.js）：
  - 登录流程：POST /login/getrsakey/ 取本次会话的 RSA 公钥 (publickey_mod / publickey_exp / timestamp)
  - 密码处理：先 strip 非 ASCII（password.replace(/[^\\x00-\\x7F]/g, '')）
  - 加密：RSA.encrypt(password, pubKey)
      * PKCS#1 v1.5 加密填充（block type = 0x02），填充字节 = Math.floor(Math.random()*254)+1（范围 1..254，非零）
      * 用 jsbn 的 modPowInt(e, n) 做 m^e mod n
      * 结果 toString(16) → Hex.decode → Base64.encode
  - 提交字段：password = 密文(base64)，rsatimestamp = 服务端返回的 timestamp

本模块 `rsa_encrypt_steam` 严格复现上述过程（stdlib only）。
`self_test()` 自生成密钥对并做"加密→私钥解密→剥离填充→还原明文"的闭环，证明实现等价于标准 RSA PKCS#1 v1.5。
"""

import base64
import os
import random

try:
    from Crypto.PublicKey import RSA as _RSA  # 仅 self_test 生成测试密钥对用
    _HAVE_CRYPTO = True
except ImportError:
    _HAVE_CRYPTO = False


def _pkcs1_pad2(data: bytes, key_size: int) -> int:
    """严格复现 rsa.js 的 RSA.pkcs1pad2：返回 PKCS#1 v1.5 填充后的大整数。

    结构（从尾部向前填充）：
        [00][02][随机非零字节 ...][00][明文]
    填充字节取值 = random(1..254)，与 JS Math.floor(Math.random()*254)+1 一致。
    """
    if key_size < len(data) + 11:
        raise ValueError("密钥长度不足以容纳明文 + PKCS#1 v1.5 填充")

    buffer = bytearray(key_size)
    i = len(data) - 1
    # 1) 明文从尾部向前写入
    while i >= 0 and key_size > 0:
        buffer[key_size - 1] = data[i]
        key_size -= 1
        i -= 1
    # 2) 明文前的 0x00 分隔符
    key_size -= 1
    buffer[key_size] = 0
    # 3) 随机非零填充（1..254），直到仅剩 [00][02] 两个字节
    while key_size > 2:
        key_size -= 1
        buffer[key_size] = random.randint(1, 254)
    # 4) block type = 0x02 与首字节 0x00
    key_size -= 1
    buffer[key_size] = 2
    key_size -= 1
    buffer[key_size] = 0
    return int.from_bytes(bytes(buffer), "big")


def rsa_encrypt_steam(password: str, mod_hex: str, exp_hex: str) -> str:
    """复现 Steam 的 RSA.encrypt(password, pubKey)，返回 base64 密文。

    :param password: 原始密码（注意：Steam 会先 strip 非 ASCII，调用方应自行保证）
    :param mod_hex: 服务端 publickey_mod（十六进制）
    :param exp_hex: 服务端 publickey_exp（十六进制，通常为 "010001"）
    :return: base64 编码的密文
    """
    n = int(mod_hex, 16)
    e = int(exp_hex, 16)
    key_size = (n.bit_length() + 7) >> 3  # 与 JS ($pubkey.modulus.bitLength()+7)>>3 一致

    # 明文按单字节（ASCII）处理，与 JS charCodeAt 一致
    data = password.encode("latin-1") if all(ord(c) < 256 for c in password) else password.encode("utf-8")
    m = _pkcs1_pad2(data, key_size)

    c = pow(m, e, n)  # 等价于 jsbn 的 modPowInt(e, n)

    hex_str = format(c, "x")
    if len(hex_str) & 1:
        hex_str = "0" + hex_str
    raw = bytes.fromhex(hex_str)  # 等价于 JS Hex.decode
    return base64.b64encode(raw).decode("ascii")


def _strip_pkcs1_v15(cipher_int: int, n: int, expected: bytes) -> bool:
    """用私钥 d 解密并剥离 PKCS#1 v1.5 填充，校验是否能还原 expected 明文。"""
    d = _CURRENT_D
    key_size = (n.bit_length() + 7) >> 3
    m = pow(cipher_int, d, n)
    buf = m.to_bytes(key_size, "big")
    # 结构校验
    if buf[0] != 0 or buf[1] != 2:
        return False
    # 找 0x00 分隔符（填充区不允许出现 0x00）
    idx = 2
    while idx < key_size and buf[idx] != 0:
        idx += 1
    if idx >= key_size:
        return False
    plaintext = buf[idx + 1:]
    return plaintext == expected


_CURRENT_D = None  # self_test 时临时写入私钥


def self_test(bits: int = 1024) -> dict:
    """自生成 RSA 密钥对，验证 rsa_encrypt_steam 的闭环正确性。

    返回验证结果字典（供断言/打印）。
    """
    if not _HAVE_CRYPTO:
        return {"ok": False, "reason": "需要 pycryptodome 运行 self_test（pip install pycryptodome）"}
    key = _RSA.generate(bits)
    n, e, d = key.n, key.e, key.d
    mod_hex = format(n, "x")
    if len(mod_hex) & 1:
        mod_hex = "0" + mod_hex
    exp_hex = format(e, "x")

    samples = ["STEAM_REPRO_PW_2026", "Abc123!@#", "short", "x" * 80]
    results = []
    global _CURRENT_D
    _CURRENT_D = d
    for pw in samples:
        cipher_b64 = rsa_encrypt_steam(pw, mod_hex, exp_hex)
        c_int = int.from_bytes(base64.b64decode(cipher_b64), "big")
        ok = _strip_pkcs1_v15(c_int, n, pw.encode("latin-1") if all(ord(c) < 256 for c in pw) else pw.encode("utf-8"))
        results.append({"pw_len": len(pw), "cipher_b64_len": len(cipher_b64), "decrypt_match": ok})
    return {"ok": all(r["decrypt_match"] for r in results), "bits": bits, "samples": results}


def build_login_payload(username: str, password: str, mod_hex: str, exp_hex: str, timestamp: str) -> dict:
    """拼装 Steam 登录 POST 表单字段（不含 CSRF/hidden 动态字段，按需补充）。

    真实提交还需带上页面内的 hidden 字段（如 donotcache、captcha_gid、captcha_text 等）与 cookie。
    """
    return {
        "username": username,
        "password": rsa_encrypt_steam(password, mod_hex, exp_hex),
        "rsatimestamp": timestamp,
    }


if __name__ == "__main__":
    import json
    import sys

    # 优先用 self_test 做闭环验证
    st = self_test(1024)
    print("[self_test]", json.dumps(st, ensure_ascii=False))

    # 若命令行给了 n_hex e_hex，则演示对真实公钥的加密
    if len(sys.argv) >= 4:
        _, pw, mod_hex, exp_hex, ts = (sys.argv + [""])[:5]
        if not pw:
            pw = "STEAM_REPRO_PW_2026"
        payload = build_login_payload("demo_user", pw, mod_hex, exp_hex, ts or "<timestamp>")
        print("[demo payload]", json.dumps(payload, ensure_ascii=False))
    else:
        print("[提示] 用法: python steam_login.py <password> <mod_hex> <exp_hex> [timestamp]")
