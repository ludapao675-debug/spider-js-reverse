"""Resample live JCAP xyList to a new best_x target.

Input track: [[x,y,dt], ...] where dt is ms since previous sample (live JD format).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def resample(track: list[list[int]], best_x: int) -> list[list[int]]:
    if not track:
        return [[0, 0, 0], [best_x, 0, 3200]]
    src_max = max(p[0] for p in track) or 1
    scale = best_x / float(src_max)
    out: list[list[int]] = []
    last_x = -1
    for x, y, dt in track:
        nx = int(round(x * scale))
        # keep monotonic non-decreasing x
        if nx < last_x:
            nx = last_x
        # drop pure duplicates except first/last timing
        if out and nx == last_x and dt < 30:
            # merge dt into previous
            out[-1][2] += int(dt)
            continue
        out.append([nx, int(y), int(dt)])
        last_x = nx
    if out[-1][0] != best_x:
        out.append([best_x, 0, max(200, out[-1][2])])
    # ensure start
    if out[0] != [0, 0, 0]:
        out.insert(0, [0, 0, 0])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=str(Path(__file__).with_name("track_sample_live.json")))
    ap.add_argument("--best-x", type=int, required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    data = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    track = data["list"]
    out = resample(track, args.best_x)
    payload = {
        "best_x": args.best_x,
        "src_max": max(p[0] for p in track),
        "n": len(out),
        "total_dt": sum(p[2] for p in out),
        "list": out,
        "meta": data.get("meta") or {},
    }
    text = json.dumps(payload, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
