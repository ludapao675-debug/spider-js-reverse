# -*- coding: utf-8 -*-
"""
====================================================================
同花顺 / 爱问财 (iwencai.com) SSO 登录密码 RSA 加密复现脚本
====================================================================
"""

from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

def encrypt_iwencai_password(password: str) -> str:
    """
    使用同花顺 SSO 官方公钥对明文密码进行 RSA-1024 加密
    :param password: 明文密码
    :return: 256 字符 Hex 密文
    """
    # 来自 https://upass.iwencai.com/pubkey/default.js 的模数 (n) 与指数 (e)
    modulus_hex = "D90F4DD5BF444916913F7B434F192587C354387FA531F2964725B5188FB9D5B40FDDD2B34F61B5560468D1F5C568796EB15F7799F03E4A3301EAF8B79B655F1B2B7DC6FFE1084E4C14A05DD9C6D0C72C5ED75890DC5D11AB5990A3C7DEBA0D68EFFD8C619B2A21AEFA3E7FF902CDAE0502025901EE2D42B76A0D7AD389F0BF69"
    exponent_int = 65537  # 0x10001
    
    n = int(modulus_hex, 16)
    e = exponent_int
    
    # 构造 RSA 公钥
    pub_key = RSA.construct((n, e))
    cipher = PKCS1_v1_5.new(pub_key)
    
    # 执行加密
    encrypted_bytes = cipher.encrypt(password.encode('utf-8'))
    # 转为小写 Hex 字符串
    return encrypted_bytes.hex()

if __name__ == "__main__":
    test_account = "32fwef"
    test_password = "testpass123"
    
    encrypted_hex = encrypt_iwencai_password(test_password)
    print("=" * 65)
    print("      同花顺 / 爱问财 SSO 登录密码 RSA 加密复现      ")
    print("=" * 65)
    print(f"[*] 测试账号: {test_account}")
    print(f"[*] 明文密码: {test_password}")
    print(f"[+] 加密密文: {encrypted_hex}")
    print(f"[+] 密文长度: {len(encrypted_hex)} 字符 (Hex)")
    print("=" * 65)
