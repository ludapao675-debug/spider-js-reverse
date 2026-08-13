# -*- coding: utf-8 -*-
"""遥测载荷导出：从页面 __tl_cap 读全部 t.gif 样本，落盘并做字段 diff 分析"""
import base64
import json
import os
import sys
import urllib.request
from urllib.parse import parse_qsl

BACKEND = "http://127.0.0.1:27183"
TAB_ID = "8D44B9776336055378BCC173BEA94A23"
HERE = os.path.dirname(os.path.abspath(__file__))


def api_post(path, payload, timeout=60):
    req = urllib.request.Request(
        BACKEND + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    # 取全部捕获记录（含 b64 body），大结果可能落盘
    r = api_post("/api/browser/page/run-js", {
        "tab_id": TAB_ID,
        "code": "(() => ({records: window.__tl_cap || []}))()",
        "return_mode": "json"}, timeout=30)
    res = r.get("result")
    if not isinstance(res, dict) and r.get("result_stashed"):
        fn = os.path.basename(str(r.get("result_file") or ""))
        rr = json.loads(urllib.request.urlopen(
            f"{BACKEND}/api/browser/page/run-js/result?file={fn}", timeout=30).read())
        res = rr.get("data") or {}
    records = (res or {}).get("records") or []
    print(f"记录数: {len(records)}")

    samples = []
    for i, rec in enumerate(records):
        b64 = rec.get("body_b64") or ""
        try:
            raw = base64.b64decode(b64).decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[{i}] 解码失败: {e}")
            continue
        kv = dict(parse_qsl(raw, keep_blank_values=True))
        samples.append({"index": i, "len": rec.get("len"), "raw": raw, "kv": kv})

    out = os.path.join(HERE, "telemetry_samples.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=1)
    print(f"已保存: {out}")

    # 字段全集 + 逐样本值摘要
    all_keys = []
    for s in samples:
        for k in s["kv"]:
            if k not in all_keys:
                all_keys.append(k)
    print(f"\n字段全集 ({len(all_keys)}):")
    for k in all_keys:
        vals = set()
        for s in samples:
            v = s["kv"].get(k, "<MISSING>")
            vals.add(v[:60] if isinstance(v, str) else str(v)[:60])
        stable = "常量" if len(vals) == 1 else f"{len(vals)} 种值"
        print(f"  {k:20s} {stable:8s} 示例={list(vals)[:2]}")


if __name__ == "__main__":
    main()
