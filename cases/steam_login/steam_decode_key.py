# -*- coding: utf-8 -*-
"""解码 Steam 新登录流捕获的两个 protobuf，提取 RSA 公钥与加密凭证结构。"""
import base64
import json
from pathlib import Path

# ---- 数据（来自监听器捕获） ----
# GetPasswordRSAPublicKey 响应体（base64 编码的 protobuf）
KEY_RESP_B64 = ("CoAEZDcyZGNmZTA4NTU5ODM2MGEwM2FmMmU0MjczZWE2MDFiNmI0YjBhZDc0OWQ2MmJl"
                "MjMzNjM3YjU4OTNhM2IyNTk3MDYxNGNiYmI2NGExZTRiMmY3NWIxMjRiZmFlZmM1M2Fj"
                "YWZlNDEzYWYzY2RlZTcwYjFhNmZhMjVkYmU2ZTAwNDIxYjg4MmUyYWZiYjI2ODdiNWQ0"
                "M2YyODI5YWFmNDc2MjM3ZDRiNGU4ZjFlMGQ1OTI2YzYyZGI0OTMzNjJjNjFiNjgwOWVm"
                "OWI0Zjc5M2ZkNmViMThmMWJiOWNhZWY1MjFhZWYxNzNkNWY5NWRmYzdkNDQ1ZDI3ZTgw"
                "ODVmYzQyNjY4YzYyYWE0M2FlNmZmYWFhZjcwMGUzMDg2MWU4MzE0MjM4NTMwYmI2YjJl"
                "MDQxOGQ2NzQxOWY2ODkzYzNkYmM1OWZiMTkxMDhlZWU2MmFlNzEzZWJjMDkwM2I0MmEz"
                "NTMyZmYxN2VlMDEyY2Y0ZjYxNDkyM2QzMzVhNjkxNGZmOWI4MzgxMWU0MGEyMjllNGZi"
                "Y2Y0ZmQxZDEwNjFkMTUwN2Y1MTIwNjQwMTgwZGE4NTVhZGYzOWI5YjUwNzg5Mjc2NmYx"
                "NzAzMjRiNWQ4NTYxNzQxOGM2Yzk5NmE2ZWVmMWRkNDE1N2RjNDdhZjFjMzNjOTA3YzI2"
                "MzY0YzcSBjAxMDAwMRjAgInf1wE=")

# BeginAuthSessionViaCredentials 请求体里的 input_protobuf_encoded（base64 编码的 protobuf）
CRED_REQ_B64 = ("EhJ0ZXN0X3JldmVyc2VfcHJvYmUa2AJBeUFieWRPRUtQcVVCaTB6WlQ2RUMwVDhkakFH"
                "T0RGQmtjUWs4NWNqWlZpNWQ4aFNhZWFyZitvMWp2Q3VhUXlaVXg2ZTVMR0YwVk1pNkFz"
                "S2NBK2YzRlJucjhiOHFhRmROTzJGcE1sZnlYcFRueC9KOUY1VU5saFVzRlhzMWVMMllW"
                "Q3BKY3FhQlBOQUZFZzB0eGlOYXl0Vm4vQ1g4S2pZRXNOVVZGWXo4QldZaWlNMnhjcEEv"
                "N0JMU09WWjVHaXJqSTExdCtiZXdDTC9iU0hoZTVqMzJkVGZYTlN4b21TSmJDZ2ZOYXFS"
                "dkVuRmdFTkU3MENueXJheENOczlUdG0rM0k3aU5SdlIyTXRZcldPM0xCRXRIS3hsbHpD"
                "TzFiTmtMMnhZQ1dGTk5MQm9JZnJzQmtJamtvY0psRmZxSXdZbElNZEx5WjRsM3MwWHJk"
                "VTIvZmR1Wmc9PSDAgInf1wEoATgBQgVTdG9yZUpzCm9Nb3ppbGxhLzUuMCAoV2luZG93"
                "cyBOVCAxMC4wOyBXaW42NDsgeDY0KSBBcHBsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBs"
                "aWtlIEdlY2tvKSBDaHJvbWUvMTMxLjAuMC4wIFNhZmFyaS81MzcuMzYQAlgG")


def read_varint(data, i):
    """从 data[i] 读取一个 varint，返回 (value, next_i)。"""
    shift = 0
    result = 0
    while True:
        b = data[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, i


def parse_protobuf(data):
    """极简 protobuf 解析：返回 {field_no: value}，重复字段取最后一次。
    length-delimited 值保留原始 bytes；varint 取整数。"""
    fields = {}
    i = 0
    n = len(data)
    while i < n:
        tag, i = read_varint(data, i)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:  # varint
            val, i = read_varint(data, i)
            fields[field_no] = val
        elif wire_type == 2:  # length-delimited
            length, i = read_varint(data, i)
            val = data[i:i + length]
            i += length
            fields[field_no] = val
        elif wire_type == 5:  # 32-bit
            val = data[i:i + 4]
            i += 4
            fields[field_no] = val
        elif wire_type == 1:  # 64-bit
            val = data[i:i + 8]
            i += 8
            fields[field_no] = val
        else:
            raise ValueError("未知 wire_type=%d" % wire_type)
    return fields


def main():
    print("="*70)
    print("【1】GetPasswordRSAPublicKey 响应解析")
    print("="*70)
    key_bytes = base64.b64decode(KEY_RESP_B64)
    kf = parse_protobuf(key_bytes)
    print("原始字节数:", len(key_bytes))
    for fno, v in sorted(kf.items()):
        if isinstance(v, (bytes, bytearray)):
            try:
                s = v.decode('utf-8', 'replace')
            except Exception:
                s = repr(v)
            print("  field %d (bytes/%d): %s" % (fno, len(v), (s[:200] + '...') if len(s) > 200 else s))
        else:
            print("  field %d (varint): %d  (hex=%s)" % (fno, v, hex(v)))

    mod_hex = kf.get(1, b'').decode('utf-8', 'replace') if isinstance(kf.get(1), (bytes, bytearray)) else None
    exp_raw = kf.get(2)
    exp_hex = exp_raw.decode('utf-8', 'replace') if isinstance(exp_raw, (bytes, bytearray)) else None
    ts = kf.get(4)
    print("\n>>> 提取结论：")
    print("    modulus (field1, hex 字符串):", (mod_hex[:64] + '...' + mod_hex[-32:]) if mod_hex else None, " len=", len(mod_hex) if mod_hex else 0)
    print("    exponent (field2):", exp_hex, " -> int =", int(exp_hex, 16) if exp_hex else None)
    print("    timestamp? (field4 varint):", ts)

    print("\n" + "="*70)
    print("【2】BeginAuthSessionViaCredentials 请求 input_protobuf 解析")
    print("="*70)
    cred_bytes = base64.b64decode(CRED_REQ_B64)
    cf = parse_protobuf(cred_bytes)
    print("原始字节数:", len(cred_bytes))
    for fno, v in sorted(cf.items()):
        if isinstance(v, (bytes, bytearray)):
            try:
                s = v.decode('utf-8', 'replace')
                is_text = True
            except Exception:
                s = repr(v)
                is_text = False
            if is_text:
                print("  field %d (string): %s" % (fno, (s[:120] + '...') if len(s) > 120 else s))
            else:
                print("  field %d (bytes/%d): %s" % (fno, len(v), repr(v[:40])))
        else:
            print("  field %d (varint): %d (hex=%s)" % (fno, v, hex(v)))

    account = cf.get(1, b'').decode('utf-8', 'replace') if isinstance(cf.get(1), (bytes, bytearray)) else None
    enc_pw = cf.get(2)
    enc_ts = cf.get(4)
    ua = cf.get(6)
    print("\n>>> 提取结论：")
    print("    account (field1):", account)
    print("    encrypted_password (field2, base64 字符串长度):", len(enc_pw.decode()) if isinstance(enc_pw, (bytes, bytearray)) else None)
    print("    encrypted_password (field2) preview:", (enc_pw.decode()[:80] + '...') if isinstance(enc_pw, (bytes, bytearray)) else None)
    print("    encryption_timestamp? (field4 varint):", enc_ts)
    print("    user_agent (field6):", ua.decode('utf-8', 'replace') if isinstance(ua, (bytes, bytearray)) else None)

    # 落盘供复现脚本使用
    out = {
        "modulus_hex": mod_hex,
        "exponent_hex": exp_hex,
        "key_timestamp_varint": ts,
        "account": account,
        "encrypted_password_b64": enc_pw.decode('utf-8', 'replace') if isinstance(enc_pw, (bytes, bytearray)) else None,
        "cred_timestamp_varint": enc_ts,
    }
    # 输出与脚本同目录（原先硬编码到已废弃的 reproduce/）
    out_path = Path(__file__).with_name("steam_key_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("\n[已保存] steam_key_data.json")


if __name__ == "__main__":
    main()
