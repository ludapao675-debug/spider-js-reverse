# -*- coding: utf-8 -*-
"""
goofish (闲鱼国际版) 密码登录 RSA 加密复现
========================================
来源: https://x.alicdn.com/vip/havana-nlogin/0.10.36/index.js (阿里 passport havana-nlogin)
算法: 标准 RSA-1024 + PKCS#1 v1.5 填充 (Tom Wu / jsbn RSAKey.encrypt 等价实现)

页面调用链 (bundle 内):
  getLoginData()
    -> password2 = this.rsaPassword(this.passwordNode.value())
    -> rsaPassword(e):
         var t = new T.default;                 // T = RSAKey 类 (N)
         t.setPublic(c.config.rsaModulus, c.config.rsaExponent);
         return t.encrypt(e);                   // PKCS#1 v1.5 加密
  reqPost(this.api.loginApi, JSON.stringify(getLoginData()))
    -> POST https://passport.goofish.com/newlogin/login.do?appName=xianyu&fromSite=77

公钥 (window.viewConfig，服务端下发但为静态固定值):
  rsaModulus = 1024-bit (256 hex)
  rsaExponent = 0x10001 (65537)

输出编码: encrypt() 返回 m.modPowInt(e,n).toString(16) 的小写十六进制字符串，
  且当长度为奇数时前面补 '0'，因此固定为 256 个 hex 字符 (=128 字节密文)。
"""

import random

# 公钥：来自 window.viewConfig.rsaModulus / rsaExponent（静态固定）
MODULUS_HEX = (
    "d3bcef1f00424f3261c89323fa8cdfa12bbac400d9fe8bb627e8d27a4"
    "4bd5d59dce559135d678a8143beb5b8d7056c4e1f89c4e1f152470625b7b4194"
    "4a97f02da6f605a49a93ec6eb9cbaf2e7ac2b26a354ce69eb265953d2c29e395d6d8c1cdb688978551aa0f7521f290035fad381178da0bea8f9e6adce39020f513133fb"
)
EXPONENT = 0x10001  # 65537


def _build_pkcs1_v15_block(password: bytes, key_bytes: int, rand_func) -> bytes:
    """
    构建 PKCS#1 v1.5 编码块（与页面 BigInteger 字节序一致，大端）:
        EM = 0x00 || 0x02 || PS || 0x00 || M
      - PS: 至少 8 字节的随机非零填充（页面 nextBytes 用 C() 生成 1..255）
      - M : 密码的 UTF-8 字节
    页面校验: t < e.length+11 才允许加密（即明文最长 key_bytes-11）。
    """
    m = password
    if len(m) > key_bytes - 11:
        raise ValueError("Message too long for RSA")
    ps_len = key_bytes - 3 - len(m)  # 0x00+0x02 占 2，0x00 分隔符占 1
    # 页面填充: for(u[0]=0;0==u[0];) nextBytes(u); n[--t]=u[0]
    # 即取“非 0”的随机字节（nextBytes 填 1..255 的值，遇 0 重取）
    ps = bytearray()
    while len(ps) < ps_len:
        b = rand_func()
        if b != 0:
            ps.append(b)
    return b"\x00\x02" + bytes(ps) + b"\x00" + m


def encrypt_password(
    password: str,
    modulus_hex: str = MODULUS_HEX,
    exponent: int = EXPONENT,
    seed: int = None,
):
    """
    复现 goofish 密码登录的 password2 字段。
    返回 (ciphertext_hex, block_bytes)。
    seed 不为 None 时使用确定性随机，便于复现/比对。
    """
    n = int(modulus_hex, 16)
    key_bytes = (n.bit_length() + 7) // 8  # 1024-bit -> 128
    m = password.encode("utf-8")
    rng = random.Random(seed) if seed is not None else random
    rand_func = (lambda: rng.randint(1, 255))

    block = _build_pkcs1_v15_block(m, key_bytes, rand_func)
    m_int = int.from_bytes(block, "big")
    # 页面 doPublic: c = m^e mod n （e=65537<256? 否；n 为奇数 -> 走 Montgomery 平方-乘，
    # 数学结果与标准模幂完全一致）
    c_int = pow(m_int, exponent, n)
    c_hex = format(c_int, "x")
    if len(c_hex) % 2 == 1:  # 页面: 0==(1&o.length) ? o : "0"+o
        c_hex = "0" + c_hex
    return c_hex, block


if __name__ == "__main__":
    import sys

    pw = sys.argv[1] if len(sys.argv) > 1 else "TestPwd123!"

    # 1) 随机填充（真实运行形态，每次不同但均为合法密文）
    c_hex, _ = encrypt_password(pw)
    n = int(MODULUS_HEX, 16)
    print("待测密码      :", pw)
    print("password2    :", c_hex)
    print("密文长度     :", len(c_hex), "(应为 256 = 128 字节)")
    print("密文 < n     :", int(c_hex, 16) < n)
    print("公钥位数     :", n.bit_length())

    # 2) 确定性填充复现（固定 seed），独立重建块做一致性校验
    seed = 1234567
    c_det, blk = encrypt_password(pw, seed=seed)
    # 用相同 seed 独立重建 PS，验证块构建逻辑与模幂一致
    rng = random.Random(seed)
    kb = (n.bit_length() + 7) // 8
    ps_len = kb - 3 - len(pw.encode())
    ps = bytearray()
    while len(ps) < ps_len:
        b = rng.randint(1, 255)
        if b != 0:
            ps.append(b)
    blk_rebuilt = b"\x00\x02" + bytes(ps) + b"\x00" + pw.encode()
    expected = format(pow(int.from_bytes(blk_rebuilt, "big"), EXPONENT, n), "x")
    if len(expected) % 2 == 1:
        expected = "0" + expected
    print("\n[校验] 确定性密文 :", c_det)
    print("[校验] 块重建一致 :", blk == blk_rebuilt)
    print("[校验] 模幂一致     :", c_det == expected)
    lpw = len(pw.encode())
    # 块布局: [0x00][0x02][PS 非0 随机][0x00][密码]
    # PS 区间 = [2 : -(lpw+1)]，分隔符 0x00 位于 -(lpw+1)
    print("[校验] 块结构合法 :",
          blk[0] == 0 and blk[1] == 2
          and 0 not in blk[2:-(lpw + 1)]
          and blk[-(lpw + 1)] == 0
          and blk.endswith(pw.encode()))
