# -*- coding: utf-8 -*-
"""栈式 VM 模拟器骨架 + 轨迹回放校验（方法A++ 收口，2026-07-12）

用已还原的 handler_table.json（逐操作码算子 / arity / imm）驱动一个栈式 VM，
沿捕获的 dispatch_trace 逐 step 复算并与记录值 nxt.top 比对，锁定"算术核心自洽性"。

设计要点：
- 每一步进入时，VM 栈 = 该步记录的 cur.stack（上一步 sync 锚点保证一致），因此输入即真实输入。
- 已知算子（算术/逻辑/字符串）按其语义 pop arity 操作数 -> 计算 -> push，并与 nxt.top 比对。
- 未知/对象/函数/分支类 handler 无法离线计算，直接把栈 sync 到记录的 nxt.stack（锚点），
  避免漂移，待路径 (b) 静态提取补齐后再替换为真实算子。
- 该骨架同时是未来"纯离线 VM"的基础：补齐 object/function handler + 环境指纹后，
  即可从字节码 + 常量池驱动 run_bytecode() 复现 _signature。
"""
import json
import os

HERE = os.path.abspath(os.path.dirname(__file__))
TABLE = os.path.join(HERE, "handler_table.json")
TRACE = os.path.join(HERE, "dispatch_trace.json")
OUT = os.path.join(HERE, "vm_replay_report.json")


# ---------- 基础工具 ----------
def as_int(v):
    """仅当值可无损表为整数时返回 int（覆盖 JS 的 1.0 类整数值 float）。"""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def js_num(v):
    """JS ToNumber 的近似：数字/可整数浮点/None/布尔 可转，其余(None/字符串/列表)返 None。"""
    if v is None or v is False:
        return 0
    if v is True:
        return 1
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else v
    return None


def js_str(v):
    """JS ToString 的近似（数组逗号拼接、对象 [object Object]）。"""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, list):
        return ",".join(js_str(x) for x in v)
    if isinstance(v, dict):
        return "[object Object]"
    return str(v)


def to_int32_coerce(v):
    """JS 位运算前的 ToInt32：null/undefined->0, true->1, 数字截断, 字符串尽力转。"""
    if v is None or v is False:
        return 0
    if v is True:
        return 1
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return 0
    return 0


def js_add(a, b):
    """JS `+`：任一操作数为字符串则拼接（按 JS ToString），否则数值加（按 ToNumber）。"""
    an, bn = js_num(a), js_num(b)
    if an is not None and bn is not None:
        return an + bn
    return js_str(a) + js_str(b)


def to_int32(v):
    """JS 位运算结果按有符号 32 位解释（与浏览器一致）。"""
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


# 可在 VM 中真实计算的算子
KNOWN_OPS = {
    "ADD", "SUB", "MUL", "MOD", "DIV", "EQ", "NE", "LT", "GT", "GE", "LE",
    "MIN", "MAX", "XOR", "AND", "OR", "LSHIFT", "RSHIFT", "URSHIFT",
    "ADD32", "SUB32", "MUL32", "ADD65521", "TOINT32",
    "CONCAT", "CHARCODE_AT", "CHAR_AT", "INDEX_OF", "SELECT", "SUBSTR",
    "FROMCHARCODE", "LEN", "NEG", "NOT", "INC", "DEC", "SECOND", "DUP",
}


def apply_op(op, args):
    """按算子语义对栈顶 args（[旧...新]，二元为 [a, b]）求值，返回计算结果。

    无法计算（缺操作数 / 类型不符）时抛异常，由调用方记为不匹配。
    """
    if op == "ADD":
        return js_add(args[0], args[1])
    if op == "SUB":
        return args[0] - args[1]
    if op == "MUL":
        return args[0] * args[1]
    if op == "MOD":
        if args[1] == 0:
            raise ValueError("div0")
        return args[0] % args[1]
    if op == "EQ":
        return 1 if args[0] == args[1] else 0
    if op == "NE":
        return 1 if args[0] != args[1] else 0
    if op == "LT":
        return 1 if args[0] < args[1] else 0
    if op == "GT":
        return 1 if args[0] > args[1] else 0
    if op == "MIN":
        return min(args[0], args[1])
    if op == "MAX":
        return max(args[0], args[1])
    if op in ("XOR", "AND", "OR", "ADD32", "SUB32", "MUL32", "ADD65521"):
        ia, ib = to_int32_coerce(args[0]), to_int32_coerce(args[1])
        if op == "XOR":
            return to_int32(ia ^ ib)
        if op == "AND":
            return to_int32(ia & ib)
        if op == "OR":
            return to_int32(ia | ib)
        if op == "ADD32":
            return to_int32(ia + ib)
        if op == "SUB32":
            return to_int32(ia - ib)
        if op == "MUL32":
            return to_int32(ia * ib)
        if op == "ADD65521":
            return (ia + ib) % 65521
    if op == "TOINT32":  # a | 0：浮点截断为 int32
        a = as_int(args[0])
        if a is None:
            raise ValueError("not int")
        return int(args[0])
    if op == "CONCAT":
        return str(args[0]) + str(args[1])
    if op == "CHARCODE_AT":
        return ord(args[0][args[1]])
    if op == "CHAR_AT":
        return args[0][args[1]]
    if op == "INDEX_OF":
        return args[0].find(args[1])
    if op == "SELECT":  # 条件 args[0] 为真取 args[1]，否则 args[2]
        a, b, c = args
        truthy = a not in (0, False, None, "", [], {})
        return b if truthy else c
    if op == "SUBSTR":
        return args[0][args[1]:args[1] + args[2]]
    if op == "FROMCHARCODE":
        return chr(args[0])
    if op == "LEN":
        return len(args[0])
    if op == "NEG":
        return -args[0]
    if op == "NOT":
        return 0 if args[0] else 1
    if op == "SECOND":
        return args[1]  # 栈 NIP：输出第二操作数（丢弃第一）
    if op == "DIV":
        a, b = args
        if b == 0:
            raise ValueError("div0")
        r = a / b
        return int(r) if r == int(r) and abs(r) < 1e15 else r
    if op == "GE":
        return 1 if args[0] >= args[1] else 0
    if op == "LE":
        return 1 if args[0] <= args[1] else 0
    if op in ("LSHIFT", "RSHIFT", "URSHIFT"):
        a = to_int32(to_int32_coerce(args[0]))   # JS ToInt32：截断小数/None
        b = to_int32_coerce(args[1])
        sh = b & 31
        if op == "LSHIFT":
            return to_int32(a << sh)
        if op == "RSHIFT":
            return to_int32(a >> sh)
        return (a & 0xFFFFFFFF) >> sh  # URSHIFT：无符号 32 位右移
    if op == "INC":
        return args[0] + 1
    if op == "DEC":
        return args[0] - 1
    if op == "DUP":
        return args[0]
    if op == "SWAP":
        return args[1]  # 回放仅比对 top，arity=0 一般不进此分支
    if op == "OVER":
        return args[0]
    raise ValueError("unknown op %s" % op)


def sync_to(stack, nxt):
    """把 VM 栈整体锚定到记录的 nxt.stack 窗口（未知 handler 用）。"""
    win = nxt.get("stack") or []
    del stack[:]
    stack.extend(win)


class StackVM:
    def __init__(self, table):
        self.table = table  # x(str) -> {op, arity, imm, ...}

    def replay_trace(self, trace):
        """沿 dispatch_trace 顺序复算，返回统计与不匹配样本。"""
        stack = list(trace[0].get("stack") or []) if trace else []
        stats = {"total": 0, "known": 0, "known_match": 0,
                 "synced": 0, "no_output": 0}
        per_op = {}            # op -> [cnt, match]
        mismatches = []
        for i in range(len(trace) - 1):
            cur, nxt = trace[i], trace[i + 1]
            stats["total"] += 1
            x = str(cur.get("x"))
            h = self.table.get(x, {})
            op = h.get("op")
            arity = h.get("arity", 0)
            if op in KNOWN_OPS and arity >= 1:
                stats["known"] += 1
                rec = per_op.setdefault(op, [0, 0])
                rec[0] += 1
                out = None
                ok = False
                if len(stack) >= arity:
                    args = stack[-arity:]
                    try:
                        out = apply_op(op, args)
                    except Exception:
                        out = "<err>"
                    top = nxt.get("top")
                    if top is None:
                        stats["no_output"] += 1
                    else:
                        ok = (out == top)
                        rec[1] += (1 if ok else 0)
                        if ok:
                            stats["known_match"] += 1
                        else:
                            if len(mismatches) < 30:
                                mismatches.append(
                                    {"x": x, "op": op, "args": args,
                                     "computed": out, "recorded": top})
                # 在持久栈上施加该步效果（pop arity, push out），再锚定到 nxt
                if len(stack) >= arity and out not in (None, "<err>"):
                    for _ in range(arity):
                        stack.pop()
                    stack.append(out)
                sync_to(stack, nxt)
            else:
                stats["synced"] += 1
                sync_to(stack, nxt)
        return stats, per_op, mismatches


def main():
    table = json.load(open(TABLE, encoding="utf-8"))
    data = json.load(open(TRACE, encoding="utf-8"))
    trace = data.get("dispatch_trace", [])
    vm = StackVM(table)
    stats, per_op, mismatches = vm.replay_trace(trace)

    print("=== VM 轨迹回放校验 ===")
    print("总步数        :", stats["total"])
    print("已知算子步    :", stats["known"])
    print("  其中比对命中: %d / %d (%.1f%%)" % (
        stats["known_match"], stats["known"],
        100.0 * stats["known_match"] / stats["known"] if stats["known"] else 0))
    print("无输出(top=None)跳过: ", stats["no_output"])
    print("锚定(sync)步  :", stats["synced"])
    print("\n--- 已知算子逐 op 命中 ---")
    for op in sorted(per_op, key=lambda k: -per_op[k][0]):
        c, m = per_op[op]
        print("  %-12s %4d / %4d (%.1f%%)" % (op, m, c, 100.0 * m / c if c else 0))
    if mismatches:
        print("\n--- 不匹配样本（前 %d）---" % len(mismatches))
        for mm in mismatches[:15]:
            print("  x=%-3s %-10s args=%s computed=%r recorded=%r" % (
                mm["x"], mm["op"], mm["args"], mm["computed"], mm["recorded"]))

    json.dump({"stats": stats, "per_op": per_op,
               "mismatches": mismatches},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n回放报告已保存:", OUT)


if __name__ == "__main__":
    main()
