"""
昆明理工大学 CAS 登录密码加密复现
https://cas.kmust.edu.cn/lyuapServer/login

算法：Stanford jsbn Barrett RSA（教科书式 RSA，无 padding）
- 公钥硬编码在前端 app.js 中（固定不变）
- 密码加密：encryptedString(key, password)
- loginUserToken：encryptedString(key, "lyasp" + timestamp_ms)
- 字节序：小端（jsbn 的 biFromBytes 是 little-endian）
- 输出：hex 字符串（256 字符 = 128 字节 = RSA-1024）
"""

import time
import requests

# ============ 公钥参数（硬编码在 app.js 中，固定不变） ============
MODULUS_HEX = (
    "00b5eeb166e069920e80bebd1fea4829d3d1f3216f2aabe79b6c47a3c18dcee5"
    "fd22c2e7ac519cab59198ece036dcf289ea8201e2a0b9ded307f8fb704136eae"
    "b670286f5ad44e691005ba9ea5af04ada5367cd724b5a26fdb5120cc95b64316"
    "04bd219c6b7d83a6f8f24b43918ea988a76f93c333aa5a20991493d4eb1117e7b1"
)
EXPONENT_HEX = "010001"  # 65537
TAG = "lyasp"

# 解析为整数（去掉前导 00 符号位，实际 modulus 是 128 字节 = 1024 bit）
N = int(MODULUS_HEX[2:], 16)  # 去掉前导 "00"
E = int(EXPONENT_HEX, 16)
# 输出长度固定 256 hex 字符（128 字节）
OUTPUT_LEN = 256


def jsbn_encrypt(plaintext: str) -> str:
    """
    复现 Stanford jsbn encryptedString 算法：
    1. 将明文字符串转为 UTF-8 字节
    2. 按小端序组装成大整数 m（jsbn biFromBytes 是 little-endian）
    3. c = pow(m, e, n)
    4. 输出 hex（补齐到 modulus 长度 = 256 字符）
    """
    # 明文 → UTF-8 字节
    data = plaintext.encode("utf-8")

    # jsbn 的 chunkSize = 2 * (biHighIndex(modulus) + 1)
    # 对于 1024-bit modulus，chunkSize ≈ 128 字节
    # 如果明文超过 chunkSize，需要分块加密（每块独立 powMod，空格分隔）
    chunk_size = (N.bit_length() + 7) // 8  # 128 bytes for 1024-bit

    if len(data) <= chunk_size:
        # 单块：小端序转整数
        m = int.from_bytes(data, byteorder="little")
        c = pow(m, E, N)
        # 输出 hex，固定 256 字符（128 字节 = RSA-1024 密文长度）
        result = format(c, "x").zfill(OUTPUT_LEN)
        return result
    else:
        # 多块加密（长密码场景）
        blocks = []
        for i in range(0, len(data), chunk_size):
            chunk = data[i : i + chunk_size]
            m = int.from_bytes(chunk, byteorder="little")
            c = pow(m, E, N)
            blocks.append(format(c, "x").zfill(OUTPUT_LEN))
        return " ".join(blocks)


def gen_login_user_token() -> str:
    """
    生成 loginUserToken 请求头
    公式：encryptedString(key, "lyasp" + str(timestamp_ms))
    """
    ts_ms = int(time.time() * 1000)
    plaintext = TAG + str(ts_ms)
    return jsbn_encrypt(plaintext)


def self_test():
    """
    用浏览器捕获的样本验证：
    密码 TestPass@2026 → 061deeb9f0dc2adbc2cacc263b10281f...
    """
    test_password = "TestPass@2026"
    expected = (
        "061deeb9f0dc2adbc2cacc263b10281f458b375639deba759712e17ffd35b226"
        "256c0dc5105ad293dffdcdd973789961952db68b099e8a24334a6f370c594d09"
        "fb0ee73037a28565cc8e4a455d88bcb6e01f4a256d7aa9f16cc23dade8989e6a"
        "feb18a834ecb5e40b9cb2ad40f9999efacacd12d8468c222b62c0cea757feffa"
    )

    result = jsbn_encrypt(test_password)
    print(f"密码: {test_password}")
    print(f"期望: {expected}")
    print(f"结果: {result}")
    print(f"匹配: {'✅ OK' if result == expected else '❌ MISMATCH'}")

    # 测试 loginUserToken 生成
    token = gen_login_user_token()
    print(f"\nloginUserToken 样本: {token[:64]}...")
    print(f"Token 长度: {len(token)} (期望 256)")
    assert len(token) == 256, f"Token 长度错误: {len(token)}"


def live_login(username: str, password: str, captcha: str, captcha_id: str):
    """
    完整登录请求复现
    POST https://cas.kmust.edu.cn/lyuapServer/v1/tickets
    """
    url = "https://cas.kmust.edu.cn/lyuapServer/v1/tickets"

    # 加密密码
    enc_password = jsbn_encrypt(password)

    # 生成 loginUserToken
    token = gen_login_user_token()

    # 组装表单
    data = {
        "username": username,
        "password": enc_password,
        "service": "https://i.kust.edu.cn",
        "loginType": "",
        "id": captcha_id,
        "code": captcha,
        "otpcode": "",
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "loginUserToken": token,
        "loginToken": "loginToken",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://cas.kmust.edu.cn/lyuapServer/login",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    resp = requests.post(url, data=data, headers=headers)
    print(f"\n状态码: {resp.status_code}")
    print(f"响应: {resp.text[:500]}")
    return resp


if __name__ == "__main__":
    print("=" * 60)
    print("昆明理工大学 CAS 登录加密复现")
    print("=" * 60)
    self_test()
