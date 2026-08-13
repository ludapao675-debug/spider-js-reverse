"""Extract live JCAP A.list sample from pause_scope.json (may be truncated)."""
from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAUSE = ROOT / "scratch" / "pause_scope.json"
OUT = Path(__file__).resolve().parent / "track_sample_live.json"


def main() -> None:
    raw = PAUSE.read_text(encoding="utf-8")
    m = re.search(r'"A":\{[^{}]*"value":"([^"]+)"', raw)
    if not m:
        raise SystemExit("A value not found")
    enc = m.group(1)
    A = urllib.parse.unquote(enc)
    print("A_len", len(A), "head", A[:120])
    print("tail", A[-100:])

    parts = re.findall(r"\[\d+,\d+,\d+\]", A)
    print("points", len(parts), "first", parts[:3], "last", parts[-3:])
    track = [json.loads(p) for p in parts]

    meta = {}
    for k in ("ht", "wt", "bw", "sw", "mw", "ii"):
        mm = re.search(rf'"{k}":(-?\d+)', A)
        if mm:
            meta[k] = int(mm.group(1))

    OUT.write_text(
        json.dumps({"meta": meta, "list": track, "truncated": not A.rstrip().endswith("}")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    xs = [p[0] for p in track]
    print("meta", meta)
    print("xmax", max(xs) if xs else None, "end", track[-1] if track else None)
    print("saved", OUT)


if __name__ == "__main__":
    main()
