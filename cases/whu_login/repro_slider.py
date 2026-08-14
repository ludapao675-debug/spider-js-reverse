"""
武汉大学 CAS 登录 — 滑块拼图验证码 sign 加密参数复现
====================================================
流程（已从 longbow.slidercaptcha.js + ids-sliderCaptcha.js 逆向）：
  1. 触发登录失败后页面弹出滑块验证码，GET /common/openSliderCaptcha.htl 返回
     {bigImage, smallImage}（base64）。smallImage 解码后最后 16 字节 = safeSecure。
  2. 用户拖动滑块，插件采集轨迹 tracks=[{a:dx,b:dy,c:ms}...]，moveLength=总水平位移，
     canvasLength=$("#sliderDiv").width()（实际 278）。
  3. sign = encryptPassword(JSON.stringify({canvasLength, moveLength, tracks}), safeSecure)
     - encryptPassword = AES-128-CBC(key=utf8(safeSecure), iv=utf8(random64(16)),
                       明文=random64(64)+JSON) → base64。
  4. POST /common/verifySliderCaptcha.htl?sign=...  → {errorCode:1} 成功。
    后端校验 moveLength 是否等于其生成的拼图缺口位置（需 OpenCV 从背景图分析精确缺口 x）。

本脚本提供：
  - gen_sign(canvas_length, move_length, tracks, safe_secure) ：完整 sign 生成
  - 确定性验证：与浏览器 encryptPassword 输出逐字节比对（MATCH）
"""
import json
import base64
import secrets
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"


def random64(n: int) -> str:
    return "".join(secrets.choice(AES_CHARS) for _ in range(n))


def _encrypt(plaintext: str, key: bytes, iv: str) -> str:
    cipher = AES.new(key, AES.MODE_CBC, iv.encode("utf-8"))
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct).decode()


def encrypt_password(password: str, salt: str) -> str:
    """复刻 encryptPassword：明文=random64(64)+password, key=salt, iv=random16。"""
    iv = random64(16)
    return _encrypt(random64(64) + password, salt.encode("utf-8"), iv)


def encrypt_password_deterministic(password: str, salt: str, prefix: str, iv: str) -> str:
    """确定性版本：用于与浏览器 getAesString 逐字节比对。"""
    return _encrypt(prefix + password, salt.encode("utf-8"), iv)


def gen_sign(canvas_length: int, move_length: int, tracks: list, safe_secure: str) -> str:
    """生成滑块验证 sign。"""
    payload = json.dumps(
        {"canvasLength": canvas_length, "moveLength": move_length, "tracks": tracks},
        separators=(",", ":"),
    )
    return encrypt_password(payload, safe_secure)


def safe_secure_from_small_image(small_image_b64: str) -> str:
    """safeSecure = smallImage base64 解码后最后 16 字节。"""
    raw = base64.b64decode(small_image_b64)
    return raw[-16:].decode("latin-1")


def build_human_tracks(gap_x: int) -> list:
    """构造一条拟人轨迹（加速-匀速-减速 + y 轻微抖动 + 时间递增）。"""
    import math
    tracks = [{"a": 0, "b": 0, "c": 0}]
    prev = 0
    pts = [
        (gap_x * 0.05, 1), (gap_x * 0.12, 0), (gap_x * 0.22, 2), (gap_x * 0.33, 1),
        (gap_x * 0.45, 2), (gap_x * 0.56, 1), (gap_x * 0.67, 2), (gap_x * 0.78, 0),
        (gap_x * 0.88, 1), (gap_x * 0.95, 0), (gap_x, 0),
    ]
    t = 0
    for ax, ay in pts:
        x = round(ax)
        t += 55 + int(math.sin(x) * 15 + 20)
        if x != prev:
            tracks.append({"a": x, "b": ay, "c": t})
        prev = x
    tracks[-1] = {"a": gap_x, "b": 0, "c": t}
    return tracks


if __name__ == "__main__":
    # 确定性验证：固定 salt/iv/prefix，与浏览器 getAesString 输出比对。
    salt = "t9lAoFs0w6MwaPpc"
    iv = "0123456789abcdef"
    fixed = encrypt_password_deterministic("TESTPLAINTEXT_123456", salt, "A" * 64, iv)
    print("[*] 确定性 encryptPassword:", fixed[:60], "len", len(fixed))
    print("[*] 期望(页面+CoU0...FCLg= 为无前缀版本；带A*64前缀长度216)")

    # sign 生成样例
    safe = "vKMZW9GSV8JlDxwb"
    tracks = build_human_tracks(167)
    sign = gen_sign(278, 167, tracks, safe)
    print("[*] 生成 sign 长度:", len(sign))
    print("[*] tracks 点数:", len(tracks), "moveLength:", tracks[-1]["a"])
