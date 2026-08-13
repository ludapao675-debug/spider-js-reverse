"""
阅文通行证 passport.yuewen.com — 密码 RSA-1024 PKCS#1 v1.5（hex）
================================================================
密文 = RSAKey.encrypt(password).toString(16)   # JSBN，长度 256 hex
公钥来自页面 LoginV1.init({modulus, exponent:"10001"})
提交 JSONP GET https://ptlogin.yuewen.com/login/login
  username, password(密文hex), ywtoken, auto, code, sessionkey, format=jsonp
PKCS#1 随机填充：不能逐字节比对；用长度/hex/两次不同做方案确认。
"""
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# 来自 https://passport.yuewen.com/yuewen.html 的 LoginV1.init
YUEWEN_MODULUS = (
    "CC11740869A1B1BB93F18A872196C5F5AA0FDB48D4D60C70938E99C95AE83F02"
    "A67EF4D2E2ADAE09BAB169ED1E1AE50A31170163B36B9C742843A72BC30CD3D4"
    "2D51033CFA2A3BD6CF1A9C331A0D6054AB3DEF984B6C4B5B28F26E57A300FE6A"
    "49BDFF1111299F9784177F8DFFE25B2AED2EC68B0467E98319CD94B54E8F895F"
)
YUEWEN_EXPONENT = 0x10001


def encrypt_password(password: str, modulus_hex: str = YUEWEN_MODULUS) -> str:
    key = RSA.construct((int(modulus_hex, 16), YUEWEN_EXPONENT))
    ct = PKCS1_v1_5.new(key).encrypt(password.encode("utf-8"))
    return ct.hex()


def _self_check() -> None:
    a = encrypt_password("test123Pass")
    b = encrypt_password("test123Pass")
    assert len(a) == 256 and len(b) == 256
    assert a != b
    assert all(c in "0123456789abcdef" for c in a + b)
    print("[ok] RSA-1024 PKCS#1 v1.5 hex len=256, two calls differ")
    print("[*] sample =", a[:32] + "...")


if __name__ == "__main__":
    _self_check()
