# -*- coding: utf-8 -*-
"""RCF SDK 解混淆·第四轮：手动构造 setup 闭包 + vm_lite 解码 + 内联替换
根因：数组工厂函数在文件尾部(654K)，Tier1 正则漏检、webcrack 沙箱前向引用失败。
本脚本显式拼装 setup：decoder(_0x2538) + array_factory(_0x4eab) + rotate IIFE，
交给 string_array_vm_lite.decodeClosure 在隔离 vm 求值。
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "rcf_b9216582.js")
VM_LITE = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                       "server", "webcrack_tool", "super_deobf", "string_array_vm_lite.cjs")

# Node 桥：沙箱执行 setup（factory+decoder+rotate）后直接枚举全数组解码
# 不依赖 vm_lite 的调用点收集（全文都是别名调用，直接调用 _0x2538( 几乎为零）
NODE_BRIDGE = r"""
const fs = require('fs');
const vm = require('vm');
const task = JSON.parse(fs.readFileSync(0, 'utf8'));
const ctx = vm.createContext({});
try {
  // setup：数组工厂 → 解码器 → 旋转器（rotator 内部会调解码器校验）
  vm.runInContext(task.closure, ctx, {timeout: 30000});
  const len = vm.runInContext('_0x4eab().length', ctx);
  // 一次性枚举全部索引（decoder 内部 index-0x131 取数组元素）
  const items = vm.runInContext(
    '(function(){var o={};for(var i=0;i<' + len + ';i++){try{o[i+0x131]=_0x2538(i+0x131)}catch(e){}}return o})()',
    ctx, {timeout: 30000});
  process.stdout.write(JSON.stringify({ok: true, count: Object.keys(items).length, items}));
} catch (e) {
  process.stdout.write(JSON.stringify({ok: false, error: String(e && e.message || e), items: {}, count: 0}));
}
"""


def extract_function(src, name):
    """按大括号计数提取完整函数定义"""
    i = src.find("function " + name)
    if i < 0:
        return ""
    j = src.find("{", i)
    depth, k = 0, j
    while k < len(src):
        c = src[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        elif c in "\"'":
            # 跳过字符串字面量
            q = c
            k += 1
            while k < len(src) and src[k] != q:
                if src[k] == "\\":
                    k += 1
                k += 1
        k += 1
    return ""


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    code = open(SRC, encoding="utf-8", errors="replace").read()
    print(f"源码 {len(code)} 字符")

    decoder = extract_function(code, "_0x2538")
    factory = extract_function(code, "_0x4eab")
    print(f"decoder {len(decoder)}B factory {len(factory)}B")
    if not decoder or not factory:
        print("提取失败")
        return

    # rotate IIFE：文件从头部到 }(_0x4eab,0x2c76a) 即为旋转器
    tail_marker = "(_0x4eab,0x2c76a)"
    ti = code.find(tail_marker)
    rotate = code[:ti + len(tail_marker)] + ")" if 0 <= ti < 5000 else ""
    # 原文件是 (function(){...}(args) 形式，尾部补右括号闭合
    print(f"rotate IIFE {len(rotate)}B")

    # setup 顺序：factory → decoder → rotate（rotator 会调 decoder 校验）
    closure = factory + "\n" + decoder + "\n" + rotate

    task = {"closure": closure, "full_code": code,
            "array_name": "_0x4eab", "decoder_name": "_0x2538",
            "timeout_ms": 120000, "max_items": 20000}
    t0 = time.time()
    env = dict(os.environ, VM_LITE_PATH=VM_LITE)
    p = subprocess.run(["node", "-e", NODE_BRIDGE], input=json.dumps(task),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180, env=env)
    print(f"vm 解码耗时 {time.time()-t0:.1f}s")
    if p.returncode != 0:
        print("node 错误:", p.stderr[:500])
        return
    res = json.loads(p.stdout)
    print(f"ok={res['ok']} count={res['count']} sandbox_mode={res.get('sandbox_mode')}")
    if not res["ok"]:
        print("error:", res.get("error"))
        return

    items = res["items"]  # {index(str): decoded}
    # 展示样本
    for k, v in list(items.items())[:5]:
        print(f"  [{k}] {str(v)[:60]}")

    # 内联替换：_0x2538(0x...) → 'decoded'（仅常量参数调用点）
    def repl(mm):
        idx_raw = mm.group(1)
        idx = str(int(idx_raw, 16) if idx_raw.lower().startswith("0x") else int(idx_raw))
        v = items.get(idx)
        if v is None:
            return mm.group(0)
        return json.dumps(v)

    call_pat = re.compile(r"_0x2538\s*\(\s*(0x[0-9a-fA-F]+|\d+)\s*\)")
    before_calls = len(call_pat.findall(code))
    out_code = call_pat.sub(repl, code)
    after_calls = len(call_pat.findall(out_code))
    print(f"直接调用点: {before_calls} → 残留 {after_calls}")

    # 传播式别名解析：var b = a 链（a 可能是 _0x2538 或已解析别名），迭代到不动点
    alias_decl = re.compile(r"var\s+(_0x[0-9a-f]+)\s*=\s*(_0x[0-9a-f]+)\s*[,;]")
    resolved = {"_0x2538"}
    changed = True
    while changed:
        changed = False
        for m in alias_decl.finditer(out_code):
            name, src = m.group(1), m.group(2)
            if src in resolved and name not in resolved:
                resolved.add(name)
                changed = True
    print(f"别名链解析: {len(resolved)} 个解码器等价名")
    total_alias_repl = 0
    for alias in resolved - {"_0x2538"}:
        ap = re.compile(re.escape(alias) + r"\s*\(\s*(0x[0-9a-fA-F]+|\d+)\s*\)")
        n = len(ap.findall(out_code))
        if n:
            out_code = ap.sub(repl, out_code)
            total_alias_repl += n
    print(f"别名调用点替换: {total_alias_repl} 处")

    out_path = os.path.join(HERE, "rcf_b9216582_deobf2.js")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_code)
    print(f"★ 已保存: {out_path}（{len(out_code)} 字符）")
    # 验证关键字符串是否已现明文
    for kw in ("pfb", "appKey", "getClickData", "XMLHttpRequest", "canvas"):
        hit = out_code.find(kw)
        print(f"  关键词 {kw!r}: {'✓' if hit >= 0 else '✗'}")
    # 统计残留解码器风格调用（含未解析的两参数 RC4 调用）
    resid = len(re.findall(r"_0x[0-9a-f]+\s*\(\s*0x[0-9a-f]+\s*\)", out_code))
    print(f"残留十六进制索引调用: {resid} 处")


if __name__ == "__main__":
    main()
