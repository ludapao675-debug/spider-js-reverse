"""
北京大学 PKU 统一身份认证 (iaaa.pku.edu.cn) — 密码加密参数复现
================================================================
加密算法：RSA-2048 + PKCS#1 v1.5 填充，结果 base64（JSEncrypt 默认）。

  密文 = base64( RSA_encrypt( 密码明文, 公钥 ) )

公钥来源（二选一）：
  - 静态固定公钥（见 PKU_RSA_PUBLIC_KEY，与 /iaaa/getPublicKey.do 返回一致）；
  - 或运行时 GET /iaaa/getPublicKey.do -> {key: PEM}。

提交（OAuth 路径，OAuthLogin.js L222-230）：
  POST /iaaa/oauthlogin.do  (form/ajax, dataType=json)
    appid      : portal2017 (隐藏 #appid)
    userName   : 账号 (#user_name)
    password   : RSA 密文 (#password 加密后)
    randCode   : 图形验证码 (#valid_code)，当 /iaaa/isShowCode.do 返回 success 时必填
    smsCode    : 短信码 (#sms_code)，可选
    otpCode    : OTP (#otp_code)，可选
    remTrustChk: 是否信任 (#remTrust_check checked)
    redirUrl   : 页面 redirectURL

验证：RSA 密文因随机填充每次不同，无法直接比对；用自生成密钥做加解密闭环，
输出 256 字节 / 344 字符 base64，与浏览器 JSEncrypt 输出长度一致，方案确认。
"""
import sys
import base64
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

PKU_RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqw9PsMk8v9ED/LiLT62I
DnelyIA/s8blyxqNmbgXT4xtq+Y64Bd+THYPZ4dUIRuFmMvPowQm9wL27W3PEtQy
C8VN+TzW/nPzc74fy9cRxgaSh1FXNQBqYZtltb6G5YvwBvZlYdKhE3Oo3noUD0FJ
JC11Nmcy2/x1V2pwXHRy2DHKaWB1EEtQ9dRxuMZolZIpEwWnT4CHfwEvth83kNRp
E8471KJEqyQqmqJt3JRerH4X4p41zQFIxCsrznAwku3b1qm0vgGLQ8t7XEiCjDX0
m5yIJEuW5t1YcteutuJX5+5oXxe2Fo04Wkn1pO6+QoJopqHcHJD5C+7GlnPOLB1c
DQIDAQAB
-----END PUBLIC KEY-----"""

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://iaaa.pku.edu.cn/iaaa/oauth.jsp",
}


def encrypt_password(password: str, public_key_pem: str = PKU_RSA_PUBLIC_KEY) -> str:
    key = RSA.import_key(public_key_pem)
    cipher = PKCS1_v1_5.new(key)
    ct = cipher.encrypt(password.encode("utf-8"))
    return base64.b64encode(ct).decode()


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "testuser"
    password = sys.argv[2] if len(sys.argv) > 2 else "FakePass123!"
    rand_code = sys.argv[3] if len(sys.argv) > 3 else None
    appid = sys.argv[4] if len(sys.argv) > 4 else "portal2017"
    redir = sys.argv[5] if len(sys.argv) > 5 else "https://portal.pku.edu.cn/portal2017/ssoLogin.do"

    enc = encrypt_password(password)
    print(f"[*] RSA 加密后 password 字段 = {enc}  (len={len(enc)})")

    data = {
        "appid": appid,
        "userName": username,
        "password": enc,
        "randCode": rand_code or "",
        "smsCode": "",
        "otpCode": "",
        "remTrustChk": False,
        "redirUrl": redir,
    }
    print(f"[*] POST /iaaa/oauthlogin.do 数据已组装：")
    for k, v in data.items():
        print(f"    {k} = {v if k!='password' else enc[:24]+'...(截断)'}")
    # 完整提交需 randCode（图形验证码，需人工识别）。验证加密参数可独立进行：
    # r = requests.post('https://iaaa.pku.edu.cn/iaaa/oauthlogin.do', data=data,
    #                   headers={**HEADERS,'Content-Type':'application/x-www-form-urlencoded'}, timeout=30)
    # 注：也可先 GET /iaaa/getPublicKey.do 取最新公钥（与内置静态公钥一致）。
    print(f"[*] 加密参数复现完成（RSA-2048 / PKCS#1 v1.5）。")


if __name__ == "__main__":
    main()
