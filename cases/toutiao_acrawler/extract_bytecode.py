# -*- coding: utf-8 -*-
"""从 acrawler.js 源码抽取完整字节码 b（末尾 _$jsvmprt("HEX",...) 的 hex 实参）。

为什么要抽完整 b：
  bytelog 只覆盖单次运行的执行路径字节（含分支洞），换 env 后控制流可能走到
  未捕获的 pc。而 b 是「静态字节码」，所有分支字节都在源码的 hex 字符串里，
  直接抽取即可得到 0..len-1 全覆盖的 pc->hexchar 字节图，供纯 Python VM 任意路径执行。
"""
import json
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
RAW = os.path.join(HERE, "raw", "acrawler.js")


def main():
    src = open(RAW, encoding="utf-8").read()
    # 匹配末尾 _$jsvmprt("484e4f...[hex]...", ...) 的第一个大 hex 字符串实参
    m = re.search(r'_jsvmprt\(\s*[\'"]([0-9a-fA-F]+)[\'"]', src)
    if not m:
        raise RuntimeError("未在 acrawler.js 末尾找到字节码 hex 字符串")
    b = m.group(1)
    print("抽取到字节码 hex 长度(字符):", len(b), " => 字节数:", len(b) // 2)
    print("magic(前16字符):", b[:16], "=>",
          "".join(chr(int(b[i:i+2], 16)) for i in range(0, 16, 2)))

    # pc -> hexchar 字节图（VM 以字符下标取指）
    pc_map = {i: b[i] for i in range(len(b))}
    out = {
        "hex": b,
        "len": len(b),
        "pc_map": pc_map,
    }
    out_path = os.path.join(HERE, "bytecode_full.json")
    json.dump(out, open(out_path, "w", encoding="utf-8"))
    print("已保存:", out_path)

    # 校验：与现有 bytelog 起点对齐（第一条取指应在 pc=29814）
    sample = json.load(open(os.path.join(HERE, "dispatch_trace.json"), encoding="utf-8"))
    dt = sample.get("dispatch_trace") or sample.get("dispatch_trace", [])
    if dt:
        first_O = dt[0]["O"]
        fetch_pc = first_O - 2
        ch0 = b[fetch_pc] if 0 <= fetch_pc < len(b) else "?"
        ch1 = b[fetch_pc + 1] if 0 <= fetch_pc + 1 < len(b) else "?"
        j = int(ch0 + ch1, 16)
        print("派发首条 O=%d -> 取指 pc=%d, 字节=%s%s, j=%d (派发 j=%d, 匹配:%s)"
              % (first_O, fetch_pc, ch0, ch1, j, dt[0]["j"], j == dt[0]["j"]))


if __name__ == "__main__":
    main()
