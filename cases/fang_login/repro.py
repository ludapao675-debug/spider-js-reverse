import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# 1. 房天下 (fang.com) RSA 公钥参数 (模数 N 与 指数 E)
N_HEX = "978c0a92d2173439707498f0944aa476b1b62595877dd6fa87f6e2ac6dcb3d0bf0b82857439c99b5091192bc134889dff60c562ec54efba4ff2f9d55adbccea4a2fba80cb398ed501280a007c83af30c3d1a142d6133c63012b90ab26ac60c898fb66edc3192c3ec4ff66925a64003b72496099f4f09a9fb72a2cf9e4d770c41"
E_HEX = "00010001"  # 65537

def encrypt_fang_password(password: str) -> str:
    """
    模拟前端 RSAKeyPair + encryptedString 过程
    使用模数 N 和指数 E 构造 1024 位 RSA 公钥，对密码文本进行 PKCS#1 v1.5 加密并输出 Hex 字符串
    """
    n = int(N_HEX, 16)
    e = int(E_HEX, 16)
    rsa_key = RSA.construct((n, e))
    cipher = PKCS1_v1_5.new(rsa_key)
    
    # 加密密码文本
    encrypted_bytes = cipher.encrypt(password.encode('utf-8'))
    return encrypted_bytes.hex()

def test_login(username, raw_password):
    url = "https://passport.fang.com/loginwithpwdStrong.api"
    
    # 密码加密
    pwd_encrypted = encrypt_fang_password(raw_password)
    print(f"原始密码: {raw_password}")
    print(f"加密密文: {pwd_encrypted}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://passport.fang.com",
        "Referer": "https://passport.fang.com/?backurl=http://mp.fang.com/index.do",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    payload = {
        "uid": username,
        "pwd": pwd_encrypted,
        "Service": "mp",
        "AutoLogin": "0"
    }
    
    response = requests.post(url, data=payload, headers=headers)
    print(f"HTTP Status: {response.status_code}")
    print("服务端响应 JSON:", response.json())
    return response.json()

if __name__ == "__main__":
    test_login("13800138000", "myTestPass123")
