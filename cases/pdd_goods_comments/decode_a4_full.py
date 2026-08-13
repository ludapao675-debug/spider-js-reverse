# -*- coding: utf-8 -*-
"""a4 data 完整解码器 + 指纹明文 dump
TLV 格式：每个字符串 = [0xe2,0x03] + _0x4de8a0(len) + utf8 字节
需要确认 _0x2eab31 / _0x4de8a0 实现
"""
import base64
import json
import os
import re
import sys
import zlib

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
c = open(os.path.join(HERE, "rcf_b9216582_deobf2.js"),
         encoding="utf-8", errors="replace").read()

# 提取 _0x2eab31 与 _0x4de8a0 定义
for name in ("_0x2eab31", "_0x4de8a0"):
    print(f"=== {name} ===")
    for m in re.finditer(re.escape(name) + r"\s*[=(]", c):
        i = m.start()
        seg = c[max(0, i - 10):i + 500]
        # 只打印定义处（前面是 function 或 var ... =）
        if c[max(0, i - 9):i].strip().endswith("function") or "=" in c[max(0, i - 10):i]:
            print(seg[:500])
            print("---")
            break

# 完整解码
src = open(os.path.join(HERE, "verify_a4_sign.py"), encoding="utf-8").read()
DATA = re.search(r'DATA = "([^"]+)"', src).group(1)
b64 = DATA[2:].replace("-", "+").replace("_", "/")
b64 += "=" * (-len(b64) % 4)
es = zlib.decompress(base64.b64decode(b64))
print(f"\n字节流 {len(es)} B，开始 TLV 解析...")

# 解析：模式 e2 03 <zigzag-varint 长度> <utf8 内容>
# _0x4de8a0 是 zigzag+varint：编码 n → (n<<1 ^ n>>31) 再按 7 位分组
# 验证：0x14 zigzag 解码=10="isInterval" 字节数 ✓
def read_varint(buf, pos):
    val, shift = 0, 0
    while True:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    # zigzag 还原
    return (val >> 1) ^ -(val & 1), pos

items = []
pos = 0
n = len(es)
ok = True
while pos < n:
    if es[pos] == 0xe2 and pos + 1 < n and es[pos + 1] == 0x03:
        pos += 2
        ln, pos = read_varint(es, pos)
        seg = es[pos:pos + ln]
        items.append(seg.decode("utf-8", errors="replace"))
        pos += ln
    else:
        print(f"!! 位置 {pos} 非 e203: {es[pos:pos+4].hex()}")
        ok = False
        break

print(f"解析{'成功' if ok else '失败'}，共 {len(items)} 个字符串（{len(items)//2} 对 kv）")
kv = {}
for i in range(0, len(items) - 1, 2):
    kv[items[i]] = items[i + 1]
print("\n字段清单:")
for k in kv:
    v = kv[k]
    print(f"  {k}: {v[:100]}{'...' if len(v)>100 else ''}  ({len(v)}字符)")

# 落盘完整明文
out = os.path.join(HERE, "a4_decoded_payload.json")
json.dump(kv, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n完整明文已落盘: {out}")
