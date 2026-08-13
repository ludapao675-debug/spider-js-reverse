# -*- coding: utf-8 -*-
"""
快手 __NS_hxfalcon 签名纯 Python 复现
=======================================
移植自开源实现 ikenxuan/amagi（packages/core/src/platform/kuaishou/sign/）。
算法全为硬编码常量 + 标准变体算法，无接口下发密钥。

签名结构：HUDR_<base64url>$HE_<hex>
- HUDR_ 段：载荷(count/scriptCount/SECS) -> XOR 0x23 -> ChaCha20变体 -> Base64URL
- $HE_ 段：BLAKE2s变体 -> CTS/LFSR流变换 -> hashField -> preHex拼接 -> LRC + 异或变换

用法:
    from kuaishou_hxfalcon import sign_live_api_url
    result = sign_live_api_url("https://live.kuaishou.com/live_api/liveroom/websocketinfo?caver=2&liveStreamId=xxx", cookie="kwfv1=...")
    # result = {"url": 带签名URL, "headers": {"kww": ...}, "sign_result": ..., "sign_input": ...}
"""
import struct
import time
import random as _random

# ============================================================
# 32 位整数工具（模拟 JS Int32 / >>> 语义）
# ============================================================

_U32 = 0xFFFFFFFF


def _i32(x: int) -> int:
    """截断为有符号 Int32（模拟 JS 位运算结果）"""
    x &= _U32
    return x - 0x100000000 if x & 0x80000000 else x


def _ror32(v: int, s: int) -> int:
    """32 位循环右移"""
    v &= _U32
    return ((v >> s) | (v << (32 - s))) & _U32


def _le_hex(value: int, size: int) -> str:
    """数值 -> 固定长度小端 hex（等价 toLittleEndianHex，BigInt.asUintN 语义）"""
    v = int(value) & ((1 << (size * 8)) - 1)
    out = ""
    for i in range(size):
        out += format((v >> (8 * i)) & 0xFF, "02x")
    return out


def _le_bytes(value: int, size: int = 4) -> list:
    """数值 -> 小端字节列表（等价 toLittleEndianBytes）"""
    if size >= 4 and value >= 2 ** 32:
        return [255, 255, 255, 255]
    return [(value >> (8 * i)) & 0xFF for i in range(size)]


def _bytes_to_hex(data) -> str:
    """字节序列 -> 小写 hex"""
    return "".join(format(b & 0xFF, "02x") for b in data)


def _hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h)


# ============================================================
# BLAKE2s 变体（b2has / b2sa）
# ============================================================

_B2S_IV = [2837534710, 2845986804, 2436420605, 706843635,
           719254516, 2557931286, 2596197199, 2432949778]

_B2S_SIGMA = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
    [11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4],
    [7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8],
    [9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13],
    [2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9],
    [12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11],
    [13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10],
    [6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5],
    [10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0],
]


def _b2s_quarter(st, a, b, c, d, x, y):
    st[a] = (st[a] + st[b] + x) & _U32
    st[d] = _ror32(st[d] ^ st[a], 16)
    st[c] = (st[c] + st[d]) & _U32
    st[b] = _ror32(st[b] ^ st[c], 12)
    st[a] = (st[a] + st[b] + y) & _U32
    st[d] = _ror32(st[d] ^ st[a], 8)
    st[c] = (st[c] + st[d]) & _U32
    st[b] = _ror32(st[b] ^ st[c], 7)


def _b2s_compress(h, words, offset, counter, length, is_last):
    work = [0] * 16
    block = [0] * 16
    for i in range(8):
        work[i] = h[i] & _U32
        work[i + 8] = _B2S_IV[i] & _U32
    work[12] ^= counter & _U32
    if is_last:
        work[14] ^= _U32
    for i in range(length):
        block[i % 16] ^= words[offset + i] & _U32
    for sg in _B2S_SIGMA:
        _b2s_quarter(work, 0, 4, 8, 12, block[sg[0]], block[sg[1]])
        _b2s_quarter(work, 1, 5, 9, 13, block[sg[2]], block[sg[3]])
        _b2s_quarter(work, 2, 6, 10, 14, block[sg[4]], block[sg[5]])
        _b2s_quarter(work, 3, 7, 11, 15, block[sg[6]], block[sg[7]])
        _b2s_quarter(work, 0, 5, 10, 15, block[sg[8]], block[sg[9]])
        _b2s_quarter(work, 1, 6, 11, 12, block[sg[10]], block[sg[11]])
        _b2s_quarter(work, 2, 7, 8, 13, block[sg[12]], block[sg[13]])
        _b2s_quarter(work, 3, 4, 9, 14, block[sg[14]], block[sg[15]])
    for i in range(8):
        h[i] = (h[i] ^ work[i] ^ work[i + 8]) & _U32
    return h


def _b2has_words(value: str) -> list:
    """字符串 -> UTF-8 -> 0填充至4倍数 -> 小端 Int32 word 列表"""
    raw = value.encode("utf-8")
    pad = (-len(raw)) % 4
    padded = raw + b"\x00" * pad
    return [struct.unpack("<i", padded[i:i + 4])[0] for i in range(0, len(padded), 4)]


def _b2has_hash(words: list) -> list:
    h = list(_B2S_IV)
    h[0] ^= 16842784  # 0x01010120 参数块
    offset, length, counter = 0, len(words), 0
    while length > 64:
        length -= 64
        counter += 64
        _b2s_compress(h, words, offset, counter, 64, False)
        offset += 64
    return _b2s_compress(h, words, offset, counter + length, length, True)


def derive_b2has(value: str) -> str:
    """BLAKE2s 变体摘要 hex（8 个 uint32 直序 hex 拼接）"""
    return "".join(format(w & _U32, "08x") for w in _b2has_hash(_b2has_words(value)))


def derive_b2sa(value: str) -> bytes:
    """b2has 结果的 UTF-8 字节"""
    return derive_b2has(value).encode("utf-8")


# ============================================================
# CTS / LFSR 流变换
# ============================================================

_CTS_VECTOR = bytes([
    98, 0, 0, 128, 49, 117, 185, 253, 224, 172, 104, 36, 223, 155, 87, 19,
    32, 0, 0, 64, 2, 0, 0, 16, 255, 255, 255, 127, 255, 255, 255, 63,
    0, 0, 0, 240, 0, 0, 0, 192, 0, 0, 0, 128, 255, 255, 255, 15,
])
_CTS_SEED = "Vuz4fCHxn1CO"


def _cts_create_state() -> dict:
    v = _CTS_VECTOR
    rd = lambda a, b: struct.unpack("<i", v[a:b])[0]
    return {
        "s": rd(12, 16), "u": rd(8, 12), "c": rd(4, 8), "l": rd(0, 4),
        "p": rd(16, 20), "f": rd(20, 24), "d": rd(24, 28), "y": rd(28, 32),
        "h": rd(44, 48), "E": rd(40, 44), "m": rd(36, 40), "b": rd(32, 36),
    }


def _cts_seed(st: dict, seed: str):
    chars = [ord(ch) for ch in seed]
    for i in range(4):
        ch = chars[i + 4]
        st["s"] = _i32((st["s"] << 8) | ch)
        st["u"] = _i32((st["u"] << 8) | ch)
        st["c"] = _i32((st["c"] << 8) | ch)
    if st["s"] == 0:
        st["s"] = 324508639
    if st["u"] == 0:
        st["u"] = 610839776
    if st["c"] == 0:
        st["c"] = 4256789809 & _U32  # 4256789809 > INT32_MAX，JS Number 直接存储


def _cts_byte(st: dict, value: int) -> int:
    """单字节 LFSR 变换（JS 位运算语义精确模拟）"""
    result = 0
    right_bit = st["u"] & 1
    left_bit = st["c"] & 1
    for _ in range(8):
        if st["s"] & 1:
            st["s"] = _i32((st["s"] ^ (st["l"] >> 1)) | st["E"])
            if st["u"] & 1:
                st["u"] = _i32((st["u"] ^ (st["p"] >> 1)) | st["m"])
                right_bit = 1
            else:
                st["u"] = _i32((st["u"] >> 1) & st["y"])
                right_bit = 0
        else:
            st["s"] = _i32((st["s"] >> 1) & st["d"])
            if st["c"] & 1:
                st["c"] = _i32((st["c"] ^ (st["f"] >> 1)) | st["b"])
                left_bit = 1
            else:
                st["c"] = _i32((st["c"] >> 1) & st["h"])
                left_bit = 0
        mixed = ((result << 1) & _U32) | (right_bit ^ left_bit)
        # 钳制到 Int8 范围（JS 三元钳制语义）
        if mixed > 127:
            result = mixed - 256
        elif mixed < -128:
            result = mixed + 256
        else:
            result = mixed
    return (value ^ (result + 3)) & 0xFF


def derive_cts(data: bytes) -> bytes:
    """CTS 字节流变换（种子固定 Vuz4fCHxn1CO）"""
    st = _cts_create_state()
    _cts_seed(st, _CTS_SEED)
    return bytes(_cts_byte(st, b & 0xFF) for b in data)


# ============================================================
# LRC 与 $HE 最终变换
# ============================================================

def compute_lrc_hex(hex_str: str) -> str:
    """8-bit LRC 校验（对 hex 字节求和后取负低8位）"""
    total = sum(b for b in _hex_to_bytes(hex_str))
    return format((-total) & 0xFF, "02x")


def transform_he_hex(prefix_hex: str, checksum_hex: str) -> str:
    """末字节为 key，对前缀逐字节异或"""
    data = _hex_to_bytes(prefix_hex + checksum_hex)
    key = data[-1]
    out = bytes(b ^ key for b in data[:-1]) + bytes([key])
    return _bytes_to_hex(out)


# ============================================================
# HUDR_ 段（ChaCha20 变体 + Base64URL）
# ============================================================

_HUDR_PREFIX = "HUDR_"
_HUDR_MASK = 35  # 0x23
_HUDR_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_HUDR_CHACHA_KEY = [4183807412, 394484062, 1106561997, 2378328696,
                    630790222, 2546784104, 2891127470, 1922531795]
_HUDR_CHACHA_NONCE = [2215853858, 1643070585, 1849059804]


class _ChaCha:
    """快手 HUDR 专用 ChaCha20 变体（常量/计数器起点均非标准）"""

    def __init__(self, key, nonce):
        self.key = [k & _U32 for k in key]
        self.nonce = [n & _U32 for n in nonce]

    @staticmethod
    def _rotl(v, s):
        v &= _U32
        return ((v << s) | (v >> (32 - s))) & _U32

    def _quarter(self, t, a, b, c, d):
        t[a] = (t[a] + t[b]) & _U32
        t[d] ^= t[a]
        t[d] = self._rotl(t[d], 16)
        t[c] = (t[c] + t[d]) & _U32
        t[b] ^= t[c]
        t[b] = self._rotl(t[b], 12)
        t[a] = (t[a] + t[b]) & _U32
        t[d] ^= t[a]
        t[d] = self._rotl(t[d], 8)
        t[c] = (t[c] + t[d]) & _U32
        t[b] ^= t[c]
        t[b] = self._rotl(t[b], 7)

    def _refill(self):
        work = list(self.state)
        for _ in range(0, 20, 2):
            self._quarter(work, 0, 4, 8, 12)
            self._quarter(work, 1, 5, 9, 13)
            self._quarter(work, 2, 6, 10, 14)
            self._quarter(work, 3, 7, 11, 15)
            self._quarter(work, 0, 5, 10, 15)
            self._quarter(work, 1, 6, 11, 12)
            self._quarter(work, 2, 7, 8, 13)
            self._quarter(work, 3, 4, 9, 14)
        return [(work[i] + self.state[i]) & _U32 for i in range(16)]

    def encrypt(self, data: bytes) -> bytes:
        self.state = [0] * 16
        # 非标准常量（对齐页面 $encode）
        self.state[0] = 394484062
        self.state[1] = 2378328696
        self.state[2] = 630790222
        self.state[3] = 1922531795
        for i in range(8):
            self.state[4 + i] = self.key[i]
        self.state[12] = 1  # 计数器从 1 开始
        self.state[13] = self.nonce[0]
        self.state[14] = self.nonce[1]
        self.state[15] = self.nonce[2]
        mixed = self._refill()

        out = bytearray(len(data))
        word_index = 0
        for i, b in enumerate(data):
            if word_index == 64:
                self.state[12] = (self.state[12] + 1) & _U32
                mixed = self._refill()
                word_index = 0
            word = mixed[word_index >> 2]
            ks = (word >> ((word_index & 3) << 3)) & 0xFF
            word_index += 1
            out[i] = b ^ ks
        return bytes(out)


def _encode_base64_url(data: bytes) -> str:
    """标准 Base64 后做 URL 变体替换：+ -> -  / -> _  = -> ."""
    import base64
    s = base64.b64encode(data).decode("ascii")
    return s.replace("+", "-").replace("/", "_").replace("=", ".")


def build_hudr_info_cache(script_count: int = 0) -> list:
    return [68, 0] + _le_bytes(script_count, 4)


def build_hudr_payload(count: int, script_count: int, stack_tail: str, secs_count: int) -> bytes:
    """构造 HUDR 原始载荷（未异或未加密）"""
    payload = [45, 61, 0, 2]
    payload += build_hudr_info_cache(script_count)
    payload += [112, 0] + _le_bytes(count, 4)
    payload += [114, 1] + _le_bytes(len(stack_tail), 2) + [ord(ch) for ch in stack_tail]
    payload += [115, 0] + _le_bytes(secs_count, 4)
    return bytes(payload)


def derive_hudr_body(count: int, script_count: int, stack_tail: str, secs_count: int) -> str:
    """生成 HUDR_<base64url> 段（含前缀）"""
    payload = build_hudr_payload(count, script_count, stack_tail, secs_count)
    masked = bytes(b ^ _HUDR_MASK for b in payload)
    cipher = _ChaCha(_HUDR_CHACHA_KEY, _HUDR_CHACHA_NONCE)
    encrypted = cipher.encrypt(masked)
    return _HUDR_PREFIX + _encode_base64_url(encrypted)


# ============================================================
# $HE_ 段
# ============================================================

_HE_HEADER = "4B54"
_HE_VERSION = "cda9"
_HE_STARTUP_MARKER = "ab"
_HE_FIXED_BODY = "0100000001"
_HE_INPUT_XOR_MASK = [45, 211, 69, 192]
_HE_COUNTER_XOR = 3131873467
_HE_TIME_XOR = 3360347992
_HE_TAIL = "9b563eda7b563e"
_HE_RANDOM_MAX = 281474976710655  # 2^48 - 1


def derive_he_hash_field(sign_input: str, hudr_body: str) -> str:
    """hashField = xor( cts(b2sa(signInput + 'HUDR_' + hudrBody))[:4], mask )"""
    hash_input = f"{sign_input}HUDR_{hudr_body}"
    digest = derive_cts(derive_b2sa(hash_input))
    first4 = digest[:4]
    xored = bytes(b ^ m for b, m in zip(first4, _HE_INPUT_XOR_MASK))
    return _bytes_to_hex(xored)


def derive_he_hex(count: int, hudr_body: str, sign_input: str,
                  startup_random: int, timestamp: int, random_value: float = None) -> str:
    """生成 $HE_ 段最终 hex"""
    if random_value is None:
        random_value = _random.random()
    random48 = int(random_value * _HE_RANDOM_MAX)
    hash_field = derive_he_hash_field(sign_input, hudr_body)
    time_xor = (timestamp ^ _HE_TIME_XOR) & ((1 << 48) - 1)
    pre_hex = "".join([
        _HE_HEADER,
        _HE_VERSION,
        _HE_STARTUP_MARKER,
        _le_hex(startup_random, 6),
        _le_hex(random48, 6),
        _HE_FIXED_BODY,
        _le_hex((count ^ _HE_COUNTER_XOR) & _U32, 4),
        hash_field,
        _le_hex(time_xor, 6),
        _HE_TAIL,
        compute_lrc_hex(_HE_TAIL),
    ])
    return transform_he_hex(pre_hex, compute_lrc_hex(pre_hex))


# ============================================================
# signInput 构造 / kww 派生
# ============================================================

_SKIP_KEYWORD = "__NS"


def build_sign_input(path: str, query: dict, form: dict = None, request_body: dict = None) -> str:
    """
    signInput = pathname + sorted(key=value) + JSON(requestBody)
    - query/form 合并后排除含 __NS 的 key
    - 按 "key=value" 字符串字典序排序后直接拼接（无分隔符）
    """
    combined = dict(query)
    if form:
        combined.update(form)
    entries = []
    for k, v in combined.items():
        if _SKIP_KEYWORD in k:
            continue
        if isinstance(v, dict):
            entries.append(f"{k}=[object Object]")
        else:
            entries.append(f"{k}={v}")
    entries.sort()
    body_str = ""
    if request_body:
        import json
        body_str = json.dumps(request_body, separators=(",", ":"), ensure_ascii=False)
    return f"{path}{''.join(entries)}{body_str}"


def derive_kww(cookie: str = "") -> str:
    """kww：有 kwfv1 直接复用；否则匿名 AES 生成（需 cryptography 库）"""
    import re
    m = re.search(r"(?:^|;\s*)kwfv1=([^;]*)", cookie or "")
    if m and m.group(1):
        return m.group(1)
    # 匿名路径：AES-128-CBC(key=IV='K8wm5PvY9nX7qJc2') 加密 "时间戳|8位随机" + "###ssrd"
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as _pad
        key = b"K8wm5PvY9nX7qJc2"
        seed = f"{int(time.time() * 1000)}|{''.join(_random.choice(_ALNUM) for _ in range(8))}"
        padder = _pad.PKCS7(128).padder()
        padded = padder.update(seed.encode()) + padder.finalize()
        enc = Cipher(algorithms.AES(key), modes.CBC(key)).encryptor()
        import base64
        return base64.b64encode(enc.update(padded) + enc.finalize()).decode() + "###ssrd"
    except ImportError:
        return ""


_ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


# ============================================================
# 顶层入口
# ============================================================

class HxfalconSigner:
    """进程级签名器（模拟页面 $encode 的全局状态复用）"""

    def __init__(self, script_count: int = 0, stack_tail: str = None):
        self.cat_version = "2"
        self.count = 100                       # KUAISHOU_DEFAULT_COUNT
        self.startup_random = int(time.time() * 1000)
        self.script_count = script_count
        # SECS.s：页面取 Error().stack 末 100 字符；本地构造等效浏览器栈尾
        self.stack_tail = stack_tail or self._default_stack_tail()

    @staticmethod
    def _default_stack_tail() -> str:
        tail = ("Error\n    at Object.x (https://live.kuaishou.com/_nuxt/static/app.js:2:1614795)\n"
                "    at HTMLDocument.f (https://live.kuaishou.com/_nuxt/static/liveRoom.js:1:27382)")
        return tail[-100:]

    def sign(self, path: str, query: dict, form: dict = None, request_body: dict = None) -> dict:
        """对单个请求签名，返回 {sign_result, sign_input, cat_version}"""
        sign_input = build_sign_input(path, query, form, request_body)
        secs_count = self.count
        hudr_full = derive_hudr_body(self.count, self.script_count, self.stack_tail, secs_count)
        hudr_body = hudr_full[len(_HUDR_PREFIX):]
        he_hex = derive_he_hex(
            count=self.count,
            hudr_body=hudr_body,
            sign_input=sign_input,
            startup_random=self.startup_random,
            timestamp=int(time.time() * 1000),
        )
        self.count += 1
        return {
            "sign_result": f"{hudr_full}$HE_{he_hex}",
            "sign_input": sign_input,
            "cat_version": self.cat_version,
        }


def sign_live_api_url(url: str, cookie: str = "", signer: HxfalconSigner = None) -> dict:
    """
    对快手 live_api URL 签名
    返回 {url: 带签名URL, headers: {kww}, sign_result, sign_input}
    """
    from urllib.parse import urlparse, parse_qsl, urlencode
    if signer is None:
        signer = HxfalconSigner()
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "caver" not in query:
        raise ValueError(f"URL 缺少 caver 参数: {url}")
    result = signer.sign(parsed.path, query)
    query["__NS_hxfalcon"] = result["sign_result"]
    query["caver"] = result["cat_version"]
    signed_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(query)}"
    headers = {}
    kww = derive_kww(cookie)
    if kww:
        headers["kww"] = kww
    return {
        "url": signed_url,
        "headers": headers,
        "sign_result": result["sign_result"],
        "sign_input": result["sign_input"],
    }


if __name__ == "__main__":
    # 自检：生成一次签名并打印结构
    signer = HxfalconSigner(script_count=18)
    r = signer.sign("/live_api/liveroom/websocketinfo",
                    {"caver": "2", "liveStreamId": "CkbZcn9KwMc"})
    print("sign_input:", r["sign_input"])
    print("sign_result:", r["sign_result"])
    hudr, he = r["sign_result"].split("$HE_")
    print(f"HUDR 段长度: {len(hudr)} | $HE 段长度: {len(he)}")
