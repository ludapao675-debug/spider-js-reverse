# -*- coding: utf-8 -*-
"""
acrawler 取指轨迹回灌脚手架（离线复现阶段，需浏览器先捕获 bytelog）。

流程：
  1. 浏览器注入 acrawler_instrument.js，触发 __acrawler_capture_sign(url)
     拿到 {"signature": "...", "bytelog": [{pc, val, hex}, ...]}
  2. 把 bytelog 存成 JSON，传给本脚本
  3. 本脚本：提取单字节流 -> 尝试 analyze_jsvmp(runtime_fetch=...) 还原

已知瓶颈（详见案例文档）：
  - 当前 BytecodeExtractor 提取不到 acrawler 混淆闭包里的 handler 语义
    （analyze_acrawler.py 显示 instructions=0），因此符号执行无法还原加密流程。
  - 本脚本会如实打印工具能做到的程度，并把「字节流」作为第一手证据落地，
    供后续扩展 BytecodeExtractor（识别混淆闭包 handler）或纯动态重放使用。
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from jsvmp_detector import analyze_jsvmp, BytecodeExtractor  # noqa: E402

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw", "acrawler.js")


def load_bytelog(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 优先用已配对还原的字节流（方法A 捕获产物直接带 bytes 字段）
    if "bytes" in data:
        return [b & 0xFF for b in data["bytes"]]
    if "bytelog" in data:
        bl = data["bytelog"]
        if bl and bl[0].get("kind") == "str":
            # 十六进制字符串字节码：相邻两两配对还原 1 字节
            chars = [e["ch"] for e in bl]
            out = []
            i = 0
            while i + 1 < len(chars):
                try:
                    out.append(int(chars[i] + chars[i + 1], 16))
                except ValueError:
                    pass
                i += 2
            return out
        return [e["val"] & 0xFF for e in bl]
    raise ValueError("JSON 需含 bytelog 或 bytes 字段")


def main():
    if len(sys.argv) < 2:
        print("用法: python repro_acrawler.py <bytelog.json>")
        sys.exit(1)
    bytestream = load_bytelog(sys.argv[1])
    print("字节流长度:", len(bytestream))
    print("字节流(hex):", "".join("%02x" % b for b in bytestream[:120]),
          "..." if len(bytestream) > 120 else "")

    code = open(RAW, "r", encoding="utf-8").read()
    ex = BytecodeExtractor().extract(code)
    print("\n静态提取能力核查:")
    print("  opcode_map 非空:", bool(ex.get("opcode_map")))
    print("  handlers 数量:", len(ex.get("handlers") or {}))
    print("  说明: 若 handlers 为空，符号执行无法还原（混淆闭包提取不到 handler 语义）")

    # 尝试回灌：把字节流当作真实取指序列喂给 runtime 模式
    try:
        res = analyze_jsvmp(code, runtime_fetch=bytestream)
        print("\nanalyze_jsvmp(runtime_fetch) 结果:")
        print("  runtime:", res.get("runtime"))
        print("  execution_trace_available:", res.get("execution_trace_available"))
        print("  instructions:", len(res.get("instructions") or []))
        flow = res.get("encryption_flow") or {}
        print("  detected_crypto_ops:", flow.get("detected_crypto_ops"))
        if res.get("execution_trace"):
            print("  trace 前 8 步:", res["execution_trace"][:8])
    except Exception as e:  # noqa: BLE001
        print("回灌异常（预期内，handler 语义缺失）:", repr(e))


if __name__ == "__main__":
    main()
