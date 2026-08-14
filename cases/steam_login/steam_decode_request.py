# -*- coding: utf-8 -*-
"""
解析 Steam 登录请求体（IAuthenticationService/BeginAuthSessionViaCredentials）的 protobuf。

从 ch_extract_request 取得的 request_body 中取出 input_protobuf_encoded（base64），
按 protobuf wire format 解析，提取关键字段：account_name / encrypted_password(RSA 密文) /
encryption_timestamp / user_agent / device_details。

用法:
  python steam_decode_request.py "<input_protobuf_encoded 的 base64>"
或直接在 __main__ 中粘贴。
"""
import base64
import binascii
import sys


def _read_varint(buf, pos):
    """读取一个 varint，返回 (value, new_pos)。"""
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _try_decode(b: bytes):
    """尝试把 length-delimited 字节解释为 utf-8；否则返回 hex/可打印预览。"""
    out = {}
    try:
        out["utf8"] = b.decode("utf-8")
    except Exception:
        out["utf8"] = None
    # 若看起来像 base64（且长度 %4==0），再解一层看是否二进制 RSA 密文
    s = out["utf8"]
    if s is not None and len(s) % 4 == 0 and set(s) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="):
        try:
            raw = base64.b64decode(s, validate=True)
            out["b64_decoded_len"] = len(raw)
            out["b64_decoded_hex_head"] = raw[:16].hex()
        except Exception:
            pass
    out["hex_head"] = b[:16].hex()
    out["len"] = len(b)
    return out


def parse_protobuf(buf: bytes):
    pos = 0
    n = len(buf)
    fields = []
    while pos < n:
        tag, pos = _read_varint(buf, pos)
        field_no = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:
            val, pos = _read_varint(buf, pos)
            fields.append((field_no, "varint", val))
        elif wire_type == 1:
            val = int.from_bytes(buf[pos:pos + 8], "little")
            pos += 8
            fields.append((field_no, "fixed64", val))
        elif wire_type == 2:
            length, pos = _read_varint(buf, pos)
            val = buf[pos:pos + length]
            pos += length
            fields.append((field_no, "bytes", _try_decode(val)))
        elif wire_type == 5:
            val = int.from_bytes(buf[pos:pos + 4], "little")
            pos += 4
            fields.append((field_no, "fixed32", val))
        else:
            raise ValueError("unknown wire type %d" % wire_type)
    return fields


def main():
    if len(sys.argv) > 1:
        b64 = sys.argv[1]
    else:
        # 默认：从 25880.355（信任点击）抓到的 BeginAuthSessionViaCredentials 请求体
        b64 = ("EhJ0ZXN0X3JldmVyc2VfcHJvYmUa2AJCaDZQV3I0UmUrQ0Evck81Sk1vYWtkTDREbW5ENjVt"
               "VFFUWGdWWWFsNUhsOUQ3UWZxTkdOR2NVSkRDOWV0SmVHbHZqd3JCZHI2WHV0VEtkcmZucEhr"
               "UmFGb2hEelhodi9qb0JTd3dMSEJtSVpQN3lOTnluYVFiVkExblZHRVdDM0dqa0s1QmFtWk5r"
               "OWZVRHNNZkQrU1RVMThVTUJzVXRWeE1CcTFLTFNTbWNMVmJ6QjZHSnJidHFSdERUVzVMUWxy"
               "RVlWQWZmSFhYa1p1czNTMjA3MHB0YkFsbXRBV1lGYmNweG1YWi9HOSsvYUxVLzdoTWo4Wkxr"
               "akVvNVlyR0ZhZ0NsaFpDT1ZGZkFxRXVVK0ppeEw1dk9NMVhmZlVkVDBwTU1MZEVjSUFnTEFx"
               "eE5uVmtidjgyRW9FUzFpbUtkYjlUc3ZGcXpHS01ZQmV2Q0FKLzhUZ0E9PSCg3truyQEoATgBQ"
               "gVTdG9yZUpzCm9Nb3ppbGxhLzUuMCAoV2luZG93cyBOVCAxMC4wOyBXaW42NDsgeDY0KSBBcG"
               "BsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBsaWtlIEdlY2tvKSBDaHJvbWUvMTMxLjAuMC4wIFN"
               "hZmFyaS81MzcuMzYQAlgG")
    raw = base64.b64decode(b64)
    fields = parse_protobuf(raw)
    print("protobuf 总长: %d bytes" % len(raw))
    print("=" * 60)
    for fno, ftype, val in fields:
        if ftype == "bytes":
            d = val
            line = "field#%d [%s] len=%d" % (fno, ftype, d["len"])
            print(line)
            if d.get("utf8") is not None:
                print("    utf8 :", d["utf8"][:200])
            if "b64_decoded_len" in d:
                print("    内含base64解码(bytes)长度: %d  -> 疑似RSA密文(2048位=256B)" % d["b64_decoded_len"])
                print("    RSA密文hex头: %s" % d["b64_decoded_hex_head"])
        else:
            print("field#%d [%s] = %s" % (fno, ftype, val))


if __name__ == "__main__":
    main()
