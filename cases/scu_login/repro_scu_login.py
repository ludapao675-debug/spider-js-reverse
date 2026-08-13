"""
四川大学统一身份认证登录复现
https://id.scu.edu.cn/frontend/login

算法：SM2 国密加密（C1C3C2 模式）
- 公钥从 POST /api/public/bff/v1.2/sm2_key 动态获取（每次登录刷新）
- 密码加密：SM2.encryptUseB64(publicKey_B64, plaintext).b64
- 登录接口：POST /api/public/bff/v1.2/rest_token（OAuth2 password grant）
- 验证码：GET /api/public/bff/v1.2/one_time_login/captcha（图片验证码）

依赖：pip install gmssl requests
"""

import base64
import json
import requests
from gmssl import sm2

# ============ 配置 ============
BASE_URL = "https://id.scu.edu.cn"
ENTERPRISE_ID = "scdx"


class SCULogin:
    """四川大学 CAS 登录客户端"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{BASE_URL}/frontend/login",
            "Origin": BASE_URL,
        })
        self.sm2_code = ""
        self.sm2_public_key_b64 = ""
        self.captcha_code = ""  # 验证码会话标识
        self.captcha_image_b64 = ""  # 验证码图片 base64

    def get_sm2_key(self) -> dict:
        """
        获取 SM2 公钥
        POST /api/public/bff/v1.2/sm2_key
        返回：{code, publicKey}
        """
        url = f"{BASE_URL}/api/public/bff/v1.2/sm2_key"
        resp = self.session.post(url, json={})
        data = resp.json()
        if data.get("success"):
            self.sm2_code = data["data"]["code"]
            self.sm2_public_key_b64 = data["data"]["publicKey"]
            print(f"[+] SM2 公钥获取成功")
            print(f"    code: {self.sm2_code}")
            print(f"    publicKey: {self.sm2_public_key_b64[:40]}...")
        else:
            raise Exception(f"获取 SM2 公钥失败: {data}")
        return data["data"]

    def encrypt_password(self, plaintext: str) -> str:
        """
        SM2 加密密码
        复现前端 SM2.encryptUseB64(publicKey_B64, plaintext).b64

        流程：
        1. Base64 解码公钥 → 65 字节（04 + X(32) + Y(32)）
        2. 取 X+Y 的 hex（去掉 04 前缀）作为 gmssl 的公钥
        3. SM2 加密（C1C3C2 模式）
        4. 密文前加 04 前缀字节
        5. Base64 编码输出
        """
        # 解码 Base64 公钥
        pub_bytes = base64.b64decode(self.sm2_public_key_b64)
        # pub_bytes[0] = 0x04（非压缩点标识），后 64 字节 = X(32) + Y(32)
        pub_hex = pub_bytes[1:].hex()  # 去掉 04 前缀，取 X+Y 的 hex

        # 初始化 SM2（C1C3C2 模式 = 国标）
        sm2_crypt = sm2.CryptSM2(public_key=pub_hex, private_key="", mode=1)  # mode=1: C1C3C2

        # 加密
        plaintext_bytes = plaintext.encode("utf-8")
        cipher_bytes = sm2_crypt.encrypt(plaintext_bytes)

        # 前端输出格式：04 + C1C3C2 密文 → Base64
        # gmssl 的 encrypt 返回不含 04 前缀的密文字节
        result = base64.b64encode(b'\x04' + cipher_bytes).decode()
        return result

    def get_captcha(self) -> str:
        """
        获取验证码
        GET /api/public/bff/v1.2/one_time_login/captcha?_enterprise_id=scdx&timestamp=xxx
        返回验证码图片 base64 和 code（会话标识）
        """
        import time
        url = f"{BASE_URL}/api/public/bff/v1.2/one_time_login/captcha"
        params = {"_enterprise_id": ENTERPRISE_ID, "timestamp": int(time.time() * 1000)}
        resp = self.session.get(url, params=params)
        data = resp.json()
        if data.get("success"):
            self.captcha_code = data["data"]["code"]
            self.captcha_image_b64 = data["data"].get("captcha", "")
            print(f"[+] 验证码获取成功, code: {self.captcha_code[:30]}...")
        return data.get("data", {})

    def login(self, username: str, password: str, captcha_text: str) -> dict:
        """
        执行登录
        POST /api/public/bff/v1.2/rest_token
        """
        # 加密密码
        enc_password = self.encrypt_password(password)
        print(f"[+] 密码加密完成: {enc_password[:40]}...")

        url = f"{BASE_URL}/api/public/bff/v1.2/rest_token"
        payload = {
            "client_id": "1371cbeda563697537f28d99b4744a973uDKtgYqL5B",
            "grant_type": "password",
            "scope": "read",
            "username": username,
            "password": enc_password,
            "_enterprise_id": ENTERPRISE_ID,
            "sm2_code": self.sm2_code,
            "cap_code": self.captcha_code,
            "cap_text": captcha_text,
        }

        self.session.headers["Content-Type"] = "application/json;charset=UTF-8"
        resp = self.session.post(url, json=payload)
        result = resp.json()
        print(f"[+] 登录响应 ({resp.status_code}): {json.dumps(result, ensure_ascii=False)[:300]}")
        return result

    def full_flow(self, username: str, password: str, captcha_text: str):
        """完整登录流程"""
        print("=" * 50)
        print("四川大学统一身份认证 - 登录流程")
        print("=" * 50)

        # 1. 获取 SM2 公钥
        self.get_sm2_key()

        # 2. 获取验证码
        self.get_captcha()

        # 3. 登录
        result = self.login(username, password, captcha_text)
        return result


def self_test_encrypt():
    """
    验证 SM2 加密输出格式是否与前端一致
    前端样本：密码 TestPass@2026，公钥 BDESVsB50Sgk...
    密文 BLeuGqrCfGDAW5eI++eYQ4PtGGTN015g...（Base64，解码后首字节应为 04）
    """
    # 用捕获的公钥
    pub_b64 = "BDESVsB50SgkvxGRiFVuPDnkNntXxqVfLeDcxm5Fc6zV0/435mfMfVOo0uwj9WGJuWQwMoxJN4WvvJqljvvsVUM="
    pub_bytes = base64.b64decode(pub_b64)
    print(f"公钥长度: {len(pub_bytes)} 字节 (期望 65)")
    print(f"公钥首字节: 0x{pub_bytes[0]:02x} (期望 0x04)")
    print(f"公钥 X: {pub_bytes[1:33].hex()}")
    print(f"公钥 Y: {pub_bytes[33:65].hex()}")

    # 验证前端密文格式
    cipher_b64 = "BLeuGqrCfGDAW5eI++eYQ4PtGGTN015gOpSdYmAvdNAc21JVggwoLju8YGt1Qi04GaNkRLJBCq1JLLTePVRbzqYxlc8HnMTd7zvTjT24rLSKRspl4BeFtsaVl5H8XeISjxBeRBR2wIpN6axAnDk="
    cipher_bytes = base64.b64decode(cipher_b64)
    print(f"\n前端密文长度: {len(cipher_bytes)} 字节")
    print(f"前端密文首字节: 0x{cipher_bytes[0]:02x} (期望 0x04 = C1 非压缩点)")

    # SM2 C1C3C2 密文结构：04(1) + C1(64) + C3(32) + C2(明文长度)
    # 明文 "TestPass@2026" = 13 字节
    # 总长 = 1 + 64 + 32 + 13 = 110 字节
    print(f"期望密文长度: 1 + 64 + 32 + 13 = 110 字节")
    print(f"实际密文长度: {len(cipher_bytes)} 字节")
    print(f"格式匹配: {'✅' if len(cipher_bytes) == 110 and cipher_bytes[0] == 0x04 else '❌'}")

    # 尝试用 gmssl 加密（SM2 有随机数，每次密文不同，但格式相同）
    pub_hex = pub_bytes[1:].hex()
    sm2_crypt = sm2.CryptSM2(public_key=pub_hex, private_key="", mode=1)
    test_cipher = sm2_crypt.encrypt(b"TestPass@2026")
    test_b64 = base64.b64encode(b'\x04' + test_cipher).decode()
    print(f"\nPython 加密结果: {test_b64[:50]}...")
    print(f"Python 密文长度: {len(base64.b64decode(test_b64))} 字节 (期望 110)")


if __name__ == "__main__":
    self_test_encrypt()

    # 完整登录示例（需要手动输入验证码）
    # client = SCULogin()
    # client.full_flow("2020141414", "TestPass@2026", "1234")
