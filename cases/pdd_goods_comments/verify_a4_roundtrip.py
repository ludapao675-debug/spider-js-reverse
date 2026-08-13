# -*- coding: utf-8 -*-
"""a4 TLV 编码往返验证（字节级闭环）
目的：证明 TLV 编/解码器与原 SDK 完全一致
步骤：解码 es → 有序解析 kv → 用自实现 TLV 编码重建 es' → 断言 es' == es
"""
import base64
import os
import re
import sys
import zlib

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def zigzag_encode(n):
    # 对应 _0x4de8a0：n<<1 ^ n>>31（JS 32 位语义）
    n &= 0xFFFFFFFF
    z = ((n << 1) ^ (n >> 31)) & 0xFFFFFFFF
    return z


def varint_bytes(z):
    # 7 位分组，低字节在前，高位带续位（LEB128）
    out = bytearray()
    while True:
        b = z & 0x7F
        z >>= 7
        if z:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def encode_str(s):
    # _0xd63dc4：[tag=0xf1][len][utf8]，tag/len 均 zigzag+varint
    raw = s.encode("utf-8")
    return varint_bytes(zigzag_encode(0xF1)) + varint_bytes(zigzag_encode(len(raw))) + raw


def read_varint(buf, pos):
    val, shift = 0, 0
    while True:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return (val >> 1) ^ -(val & 1), pos


# 1) 解码原始 data → es
src = open(os.path.join(HERE, "verify_a4_sign.py"), encoding="utf-8").read()
DATA = re.search(r'DATA = "([^"]+)"', src).group(1)
b64 = DATA[2:].replace("-", "+").replace("_", "/")
b64 += "=" * (-len(b64) % 4)
es = zlib.decompress(base64.b64decode(b64))

# 2) 有序解析 kv
pairs = []
pos, n = 0, len(es)
while pos < n:
    assert es[pos] == 0xE2 and es[pos + 1] == 0x03, f"bad tag @{pos}"
    pos += 2
    ln, pos = read_varint(es, pos)
    seg = es[pos:pos + ln].decode("utf-8")
    pos += ln
    pairs.append(seg)
keys = pairs[0::2]
vals = pairs[1::2]
print(f"有序解析: {len(keys)} 对 kv")

# 3) 重建 es'
es2 = bytearray()
for k, v in zip(keys, vals):
    es2 += encode_str(k)
    es2 += encode_str(v)
es2 = bytes(es2)

# 4) 断言
print("原始 es 长度:", len(es))
print("重建 es 长度:", len(es2))
print("字节级一致:", es == es2)
if es != es2:
    for i in range(min(len(es), len(es2))):
        if es[i] != es2[i]:
            print("首个差异位置:", i, es[i - 4:i + 4].hex(), "vs", es2[i - 4:i + 4].hex())
            break
else:
    print("\n★★★ TLV 编解码器与原 SDK 字节级一致，a4 data 可完全本地构造 ★★★")
