# -*- coding: utf-8 -*-
"""
用 jsvmp_detector 直接分析今日头条 acrawler.js（真实 JSVMP 样本），
验证检测能力并暴露 string/hex 字节码的分类盲区。

绕过未重启的 MCP sidecar，直接调用 server.jsvmp_detector 模块。
"""
import json
import os
import sys

# 将 server 目录加入 import 路径
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from jsvmp_detector import analyze_jsvmp, _pick_bytecode_kind  # noqa: E402

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw", "acrawler.js")


def main():
    with open(RAW, "r", encoding="utf-8") as f:
        code = f.read()
    print("源码长度:", len(code), "字符")

    # 1) 直接静态分析
    rep = analyze_jsvmp(code)
    print("\n===== analyze_jsvmp 摘要 =====")
    print("ok:", rep.get("ok"))
    print("suspected:", rep.get("suspected"))
    print("bytecode_kind:", rep.get("bytecode_kind"))
    print("warnings:", rep.get("warnings"))
    comps = rep.get("components", [])
    print("components 数量:", len(comps))
    for c in comps[:20]:
        print("  -", c.get("kind"), "::", (c.get("snippet") or c.get("name") or "")[:80])

    instr = rep.get("instructions") or []
    print("反汇编指令数:", len(instr))
    print("加密流程摘要:", json.dumps(rep.get("encryption_flow", {}), ensure_ascii=False)[:600])

    # 2) 单独验证 _pick_bytecode_kind 行为
    from jsvmp_detector import BytecodeExtractor
    extract = BytecodeExtractor().extract(code)
    kind, var, arr = _pick_bytecode_kind(code, extract)
    print("\n===== _pick_bytecode_kind =====")
    print("bytecode 是否静态提取到:", extract.get("bytecode") is not None)
    print("判定 bytecode_kind/var/arr:", kind, var, arr)

    # 3) 单独跑强特征检测器，暴露本家族专属组件（_$jsvmprt / 13*X%241 / hex 取指）
    from jsvmp_detector import JsvmpHeuristics
    h = JsvmpHeuristics().detect(code)
    print("\n===== JsvmpHeuristics 强特征 =====")
    print("suspected:", h.get("suspected"), "| confidence:", round(h.get("confidence", 0), 3))
    for c in h.get("components", []):
        print("  -", c.get("kind"), "::", (c.get("snippet") or c.get("name") or "")[:80])

    # 4) 导出可复现的证据 JSON（供案例文档与回归对照）
    evidence = {
        "source": "cases/toutiao_acrawler/raw/acrawler.js",
        "source_len": len(code),
        "analyze_jsvmp": {
            "ok": rep.get("ok"),
            "suspected": rep.get("suspected"),
            "bytecode_kind": rep.get("bytecode_kind"),
            "confidence": rep.get("confidence"),
            "warnings": rep.get("warnings"),
            "instructions_count": len(instr),
        },
        "heuristics": {
            "suspected": h.get("suspected"),
            "confidence": h.get("confidence"),
            "components": [
                {"kind": c.get("kind"), "name": c.get("name"),
                 "snippet": (c.get("snippet") or "")[:120]}
                for c in h.get("components", [])
            ],
        },
        "pick_bytecode_kind": {"kind": kind, "var": var, "arr": arr,
                                "static_bytecode_extracted": extract.get("bytecode") is not None},
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis_evidence.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print("\n证据已导出:", out_path)



if __name__ == "__main__":
    main()
