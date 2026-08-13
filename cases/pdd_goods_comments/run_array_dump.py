# -*- coding: utf-8 -*-
"""RCF SDK 字符串数组快速 dump：沙箱解码全数组落盘 + 搜索指纹上报相关条目"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "rcf_b9216582.js")
OUT = os.path.join(HERE, "rcf_string_array.json")

NODE_BRIDGE = r"""
const fs = require('fs');
const vm = require('vm');
const task = JSON.parse(fs.readFileSync(0, 'utf8'));
const ctx = vm.createContext({});
try {
  vm.runInContext(task.closure, ctx, {timeout: 30000});
  const len = vm.runInContext('_0x4eab().length', ctx);
  const items = vm.runInContext(
    '(function(){var o={};for(var i=0;i<' + len + ';i++){try{o[i+0x131]=_0x2538(i+0x131)}catch(e){}}return o})()',
    ctx, {timeout: 30000});
  process.stdout.write(JSON.stringify({ok: true, items}));
} catch (e) {
  process.stdout.write(JSON.stringify({ok: false, error: String(e && e.message || e), items: {}}));
}
"""


def extract_function(src, name):
    """按大括号计数提取完整函数定义（跳过字符串字面量）"""
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
    decoder = extract_function(code, "_0x2538")
    factory = extract_function(code, "_0x4eab")
    tail_marker = "(_0x4eab,0x2c76a)"
    ti = code.find(tail_marker)
    rotate = code[:ti + len(tail_marker)] + ")"
    closure = factory + "\n" + decoder + "\n" + rotate

    t0 = time.time()
    p = subprocess.run(["node", "-e", NODE_BRIDGE],
                       input=json.dumps({"closure": closure}),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    res = json.loads(p.stdout)
    if not res.get("ok"):
        print("解码失败:", res.get("error"))
        return
    items = res["items"]
    print(f"解码 {len(items)} 条（{time.time()-t0:.1f}s）")
    json.dump(items, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已保存: {OUT}")

    # 搜索指纹上报相关条目
    keywords = ["pfb", "a3", "a4", "appKey", "sign", "timestamp", "data",
                "xg.", "/api", "report", "upload", "fingerprint"]
    print("\n=== 相关条目 ===")
    for idx, v in items.items():
        s = str(v)
        for kw in keywords:
            # 精确度控制：pfb/appKey/xg 直接命中；短词需边界
            if kw in ("pfb", "appKey", "xg.", "/api", "fingerprint"):
                hit = kw in s
            elif kw in ("a3", "a4"):
                hit = bool(re.search(rf"(^|[/=.'\"\s]){kw}($|[/=.'\"\s?])", s))
            else:
                hit = s == kw or s.startswith(kw) and len(s) < len(kw) + 20
            if hit:
                print(f"  [0x{int(idx):x}] {s[:100]}")
                break


if __name__ == "__main__":
    main()
