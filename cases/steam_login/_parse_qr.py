#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""严格解析 Steam BeginAuthSessionViaQR 响应 protobuf（解压后原始字节）。结果写入同目录 _parse_qr_out.txt。"""
import sys
import traceback
from pathlib import Path

# 输出与脚本同目录（原先硬编码到已废弃的 reproduce/，与文档描述不一致）
OUT = str(Path(__file__).with_name("_parse_qr_out.txt"))


def read_varint(buf, pos):
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("varint 越界")
        b = buf[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def parse_fields(buf, pos, end, depth=0):
    out = []
    while pos < end:
        tag, pos = read_varint(buf, pos)
        field_no = tag >> 3
        wire = tag & 0x07
        if wire == 0:
            val, pos = read_varint(buf, pos)
            out.append((field_no, "varint", val, None))
        elif wire == 2:
            ln, pos = read_varint(buf, pos)
            data = buf[pos:pos + ln]
            pos += ln
            try:
                s = data.decode("utf-8")
                is_str = True
            except Exception:
                s = None
                is_str = False
            nested = None
            if len(data) > 0 and not is_str:
                try:
                    nested = parse_fields(data, 0, len(data), depth + 1)
                except Exception:
                    nested = None
            out.append((field_no, "bytes", data, (s if is_str else nested)))
        elif wire == 5:
            val = int.from_bytes(buf[pos:pos + 4], "little")
            pos += 4
            out.append((field_no, "fixed32", val, None))
        elif wire == 1:
            val = int.from_bytes(buf[pos:pos + 8], "little")
            pos += 8
            out.append((field_no, "fixed64", val, None))
        else:
            raise ValueError(f"未知 wire type {wire} @ {pos}")
    return out


def show(fields, lines, indent=0):
    pad = "  " * indent
    for f in fields:
        no, wt, val, extra = f
        if wt == "bytes":
            if isinstance(extra, str):
                lines.append(f"{pad}field {no} (bytes, len={len(val)}): str={extra!r}")
            elif isinstance(extra, list):
                lines.append(f"{pad}field {no} (bytes, len={len(val)}): nested ->")
                show(extra, lines, indent + 1)
            else:
                lines.append(f"{pad}field {no} (bytes, len={len(val)}): hex={val.hex()}")
        else:
            lines.append(f"{pad}field {no} ({wt}): {val}")


def main():
    hexs = sys.argv[1] if len(sys.argv) > 1 else (
        "08f2cfcbfebea4f6dce801122768747470733a2f2f732e7465616d2f712f312f31363736393637333433353836313431313832361a10bfad8d1a37ea89ec06ec897bf692f122250000a0402a0208042a0208033001"
    )
    buf = bytes.fromhex(hexs)
    lines = [f"总字节数: {len(buf)}"]
    fields = parse_fields(buf, 0, len(buf))
    show(fields, lines)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write("ERROR:\n" + traceback.format_exc())
