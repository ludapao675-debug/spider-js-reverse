"""
武汉大学 (WHU) 统一身份认证登录 — 密码加密参数复现
=========================================================
加密算法：AES-128-CBC + PKCS7 填充，结果 base64（无 "Salted__" 前缀）。

  密文 = base64( AES-128-CBC( 明文 = random64(64) + password,
                               key  = utf8(pwdEncryptSalt),
                               iv   = utf8(random64(16)) ) )

其中：
  - pwdEncryptSalt：登录页隐藏字段 #pwdEncryptSalt 的值（16 字节 → AES-128 key，动态盐）
  - random64(n)：从字符集 ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678 取 n 个随机字符
提交时：
  - 可见密码框 #password 的值被忽略；
  - 加密结果写入隐藏字段 #saltPassword（name=password）；
  - 还需 captcha（图形验证码）、_eventId=submit、cllt=userNameLogin、dllt=generalLogin、
    lt（可能为空）、execution（如 e3s1）。

验证：用确定性输入比对浏览器 getAesString，Python 与浏览器输出逐字节一致
（已验证：fixed plain/salt/iv → "+CoU0m2TgRNcvl6u6BP1B/6LqQ9/P6i35OCnk0jFCLg="）。
"""
import re
import sys
import secrets
import base64
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

LOGIN_URL = (
    "https://cas.whu.edu.cn/authserver/login"
    "?service=https%3A%2F%2Fadbjh.whu.edu.cn%2F"
)

AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def random64(n: int) -> str:
    return "".join(secrets.choice(AES_CHARS) for _ in range(n))


def encrypt_password(password: str, salt: str) -> str:
    """复刻页面 encryptPassword()：AES-128-CBC(key=salt, iv=random16)。"""
    prefix = random64(64)
    iv = random64(16)
    plaintext = (prefix + password).encode("utf-8")
    key = salt.encode("utf-8")          # 16 字节 → AES-128
    iv_b = iv.encode("utf-8")           # 16 字节
    cipher = AES.new(key, AES.MODE_CBC, iv_b)
    ct = cipher.encrypt(pad(plaintext, AES.block_size))
    return base64.b64encode(ct).decode()


def encrypt_password_deterministic(password: str, salt: str, prefix: str, iv: str) -> str:
    """确定性版本：用于与浏览器 getAesString(random64(64)+pwd, salt, random64(16)) 逐字节比对。"""
    plaintext = (prefix + password).encode("utf-8")
    cipher = AES.new(salt.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    return base64.b64encode(cipher.encrypt(pad(plaintext, AES.block_size))).decode()


def _field(html: str, name: str):
    m = re.search(r'name=["\']%s["\'][^>]*?value=["\'](.*?)["\']' % re.escape(name), html)
    if not m:
        m = re.search(r'id=["\']%s["\'][^>]*?value=["\'](.*?)["\']' % re.escape(name), html)
    return m.group(1) if m else ""


def fetch_form(session: requests.Session):
    r = session.get(LOGIN_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text
    return {
        "pwdEncryptSalt": _field(html, "pwdEncryptSalt"),
        "execution": _field(html, "execution") or "e3s1",
        "lt": _field(html, "lt"),
        "cllt": _field(html, "cllt") or "userNameLogin",
        "dllt": _field(html, "dllt") or "generalLogin",
    }


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "testuser"
    password = sys.argv[2] if len(sys.argv) > 2 else "FakePass123!"
    captcha = sys.argv[3] if len(sys.argv) > 3 else None

    session = requests.Session()
    form = fetch_form(session)
    print(f"[*] pwdEncryptSalt = {form['pwdEncryptSalt']}")
    print(f"[*] execution={form['execution']} lt={form['lt']!r}")

    enc = encrypt_password(password, form["pwdEncryptSalt"])
    print(f"[*] 加密后 password 字段 = {enc}  (len={len(enc)})")

    data = {
        "username": username,
        "password": enc,                 # 隐藏字段 #saltPassword
        "captcha": captcha or "",        # 需人工识别（图形验证码）
        "_eventId": "submit",
        "cllt": form["cllt"],
        "dllt": form["dllt"],
        "lt": form["lt"],
        "execution": form["execution"],
    }
    print(f"[*] POST 数据(不含captcha)已组装。")
    print(f"    username={username}")
    print(f"    password(密文)={enc}")
    print(f"    lt={form['lt']!r} execution={form['execution']}")
    # 注：完整提交需 captcha；此处仅验证加密参数。如需实发，补充验证码后：
    # r = session.post(LOGIN_URL, data=data, headers={**HEADERS,'Content-Type':'application/x-www-form-urlencoded'}, allow_redirects=True)
    print(f"[*] 加密参数复现完成。")


if __name__ == "__main__":
    main()
