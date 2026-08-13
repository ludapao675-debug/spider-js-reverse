# -*- coding: utf-8 -*-
"""从已有数据重建自洽 bytelog。

关键事实：dispatch_trace.json 中每条派发记录的
    j = parseInt(b[O] + b[O+1], 16)
因此取指字节 b[O], b[O+1] 可由 j 直接反推：
    b[O]   = hex(j >> 4)
    b[O+1] = hex(j & 0xf)
而各 handler 的「立即数字节」宽度由 handler_table.json 的 imm（hex 字符数）给出，
其字节值来自静态字节码 bytelog_sample.json（b 是固定的，跨运行不变）。

本脚本：
  1. 以 bytelog_sample.json 的字节图为基础
  2. 用 dispatch_trace.json 的 j/O 反推并覆盖取指字节
  3. 统计执行路径上所有需读取的 pc 的覆盖率（缺口 = 分支未覆盖区域）
  4. 保存合并后的 bytelog_merged.json（沿用 dispatch_trace 的 signature）
"""
import json
import os

HERE = os.path.abspath(os.path.dirname(__file__))


def hex1(n):
    return "%x" % (n & 0xf)


def main():
    dt = json.load(open(os.path.join(HERE, "dispatch_trace.json"), encoding="utf-8"))
    dispatch = dt["dispatch_trace"]
    signature = dt.get("signature")

    bl = json.load(open(os.path.join(HERE, "bytelog_sample.json"), encoding="utf-8"))
    base = {e["pc"]: e["ch"] for e in bl["bytelog"]}

    table = json.load(open(os.path.join(HERE, "handler_table.json"), encoding="utf-8"))

    merged = dict(base)
    fetch_needed = set()
    imm_needed = set()
    imm_missing = set()

    for e in dispatch:
        O = e["O"]
        j = e["j"]
        # 1) 取指字节（由 j 反推，覆盖 base 中可能的不一致）
        merged[O] = hex1(j >> 4)
        merged[O + 1] = hex1(j & 0xf)
        fetch_needed.add(O)
        fetch_needed.add(O + 1)
        # 2) 立即数字节：handler_table[x].imm = 取指后读取的 hex 字符数
        h = table.get(str(e["x"]))
        if h and h.get("imm"):
            w = h["imm"]  # hex 字符数（2/4/8...）
            # 读取区间：O+2 .. O+1+w（每个 hex 字符 1 个 pc）
            for k in range(O + 2, O + 2 + w):
                imm_needed.add(k)
                if k not in base:
                    imm_missing.add(k)

    # 覆盖率统计
    fetch_ok = sum(1 for p in fetch_needed if p in merged)
    imm_ok = sum(1 for p in imm_needed if p in merged)

    # 保存合并 bytelog（与 bytelog_sample.json 同构：{signature, bytelog:[{pc,ch}]}）
    out = {
        "signature": signature,
        "bytelog": [{"pc": p, "ch": merged[p]} for p in sorted(merged.keys())],
    }
    out_path = os.path.join(HERE, "bytelog_merged.json")
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)

    print("dispatch 步数:        ", len(dispatch))
    print("base(byetlog_sample)字节数:", len(base))
    print("merged 字节数:        ", len(merged))
    print("取指 pc 需求/覆盖:    ", len(fetch_needed), "/", fetch_ok)
    print("立即数 pc 需求:       ", len(imm_needed))
    print("立即数 pc 已覆盖:     ", imm_ok)
    print("立即数 pc 缺口:       ", len(imm_missing))
    if imm_missing:
        miss_sorted = sorted(imm_missing)
        print("  缺口示例(pc):      ", miss_sorted[:20], "..." if len(miss_sorted) > 20 else "")
        # 缺口是否集中在某区间
        print("  缺口 pc 范围:      ", miss_sorted[0], "..", miss_sorted[-1])
    print("已保存:", out_path, " signature:", signature)


if __name__ == "__main__":
    main()
