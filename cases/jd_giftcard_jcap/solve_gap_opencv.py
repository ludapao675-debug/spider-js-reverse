"""JCAP 拼图缺口：OpenCV 多策略（轮廓白边 + Canny 模板匹配）

输入 b1(底图)/b2(滑块) dataURL 或 --json {b1,b2}
输出 JSON: bestX / score / votes / source
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def load_data_url(s: str) -> np.ndarray:
    raw = s.split(",", 1)[1] if "," in s else s
    buf = np.frombuffer(base64.b64decode(raw), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("imdecode failed")
    return img


def piece_mask(piece: np.ndarray) -> np.ndarray:
    if piece.ndim == 3 and piece.shape[2] == 4:
        return piece[:, :, 3] > 128
    rgb = piece[:, :, :3] if piece.ndim == 3 else piece
    # 京东 b2：黑底 + 白描边块；近黑=背景
    if piece.ndim == 2:
        return rgb > 20
    near_black = (rgb[:, :, 0] < 25) & (rgb[:, :, 1] < 25) & (rgb[:, :, 2] < 25)
    near_white = (rgb[:, :, 0] > 245) & (rgb[:, :, 1] > 245) & (rgb[:, :, 2] > 245)
    # 白边也算块轮廓
    return (~near_black) | near_white


def match_template_votes(bg_e: np.ndarray, pt_e: np.ndarray, mask: np.ndarray | None) -> list[dict]:
    methods = [
        ("TM_CCORR_NORMED", cv2.TM_CCORR_NORMED),
        ("TM_CCOEFF_NORMED", cv2.TM_CCOEFF_NORMED),
        ("TM_SQDIFF_NORMED", cv2.TM_SQDIFF_NORMED),
    ]
    votes = []
    for name, method in methods:
        # OpenCV 5: mask 可选
        try:
            # mask 在部分 OpenCV/图上会给出 inf，优先无 mask
            res = cv2.matchTemplate(bg_e, pt_e, method)
        except Exception:
            continue
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if method == cv2.TM_SQDIFF_NORMED:
            loc, score = min_loc, float(1.0 - min_val)
        else:
            loc, score = max_loc, float(max_val)
        # 贴左缘几乎一定是假阳性
        if loc[0] < 20 and score < 0.55:
            continue
        if score != score or score == float("inf") or score == float("-inf"):
            continue
        votes.append({"method": name, "x": int(loc[0]), "y": int(loc[1]), "score": float(score)})
    return votes


def find_white_outline_x(bg: np.ndarray, y0: int, y1: int, min_x: int = 40) -> dict | None:
    """京东缺口常有亮白描边：在块高度带内找竖直亮边簇的左缘。"""
    gray = cv2.cvtColor(bg[:, :, :3], cv2.COLOR_BGR2GRAY)
    band = gray[y0:y1, :]
    # 高亮边缘
    bright = (band > 200).astype(np.uint8) * 255
    # 竖向投影：每列亮点数
    col = bright.sum(axis=0).astype(np.float64)
    # 平滑
    k = np.ones(5) / 5.0
    col = np.convolve(col, k, mode="same")
    # 只看右 70% 区域（缺口不会贴左）
    start = max(min_x, band.shape[1] // 5)
    region = col[start:]
    if region.max() < (y1 - y0) * 2:  # 太弱
        return None
    peak = int(np.argmax(region)) + start
    # 从峰值向左找亮边起点
    thr = region.max() * 0.35
    x = peak
    while x > start and col[x] >= thr:
        x -= 1
    return {"method": "white_outline", "x": int(x + 1), "y": int(y0), "score": float(col[peak] / max(1, (y1 - y0)))}


def solve(b1: np.ndarray, b2: np.ndarray) -> dict:
    bg = b1[:, :, :3] if b1.ndim == 3 else cv2.cvtColor(b1, cv2.COLOR_GRAY2BGR)
    piece = b2
    mask = piece_mask(piece)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return {"ok": False, "error": "empty_piece"}

    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    crop = piece[y0:y1, x0:x1]
    cm = mask[y0:y1, x0:x1]
    if crop.ndim == 2:
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    elif crop.shape[2] == 4:
        crop_rgb = crop[:, :, :3].copy()
    else:
        crop_rgb = crop[:, :, :3].copy()
    crop_rgb[~cm] = 0

    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    pt_gray = cv2.cvtColor(crop_rgb, cv2.COLOR_BGR2GRAY)
    bg_e = cv2.Canny(bg_gray, 60, 140)
    pt_e = cv2.Canny(pt_gray, 60, 140)
    pt_e[~cm] = 0

    th, tw = pt_e.shape[:2]
    bh, bw = bg_e.shape[:2]
    if th >= bh or tw >= bw:
        return {"ok": False, "error": "piece_too_large", "bg": [bw, bh], "piece": [tw, th]}

    votes = []
    for v in match_template_votes(bg_e, pt_e, cm):
        v["method"] = v["method"] + "_edge"
        votes.append(v)
    for v in match_template_votes(bg_gray, pt_gray, cm):
        v["method"] = v["method"] + "_gray"
        votes.append(v)

    outline = find_white_outline_x(bg, y0, y1, min_x=max(40, tw))
    if outline:
        votes.append(outline)

    if not votes:
        return {"ok": False, "error": "no_votes"}

    # 缺口 y 必须落在滑块高度带附近（灰度全图匹配易漂到水珠纹理）
    y_lo, y_hi = max(0, y0 - 12), min(bh - 1, y1 + 12)

    def in_band(v: dict) -> bool:
        if v["method"] == "white_outline":
            return True
        return y_lo <= int(v.get("y", y0)) <= y_hi

    banded = [v for v in votes if in_band(v)]
    pool = banded or votes

    # 优先边缘匹配；同带内再按分数
    edge = [v for v in pool if "_edge" in v["method"] and "CCORR" in v["method"]]
    edge2 = [v for v in pool if "_edge" in v["method"]]
    gray_ok = [v for v in pool if "_gray" in v["method"] and "CCOEFF" in v["method"]]
    cand = edge or edge2 or gray_ok or pool
    best = max(cand, key=lambda v: v["score"])
    best_x = int(best["x"])

    # 边缘投票中位数稳健
    edge_xs = sorted(v["x"] for v in pool if "_edge" in v["method"])
    if edge_xs:
        mid = edge_xs[len(edge_xs) // 2]
        if abs(mid - best_x) <= 8:
            best_x = mid

    if outline and in_band(outline) and abs(outline["x"] - best_x) <= 18:
        best_x = int(outline["x"])
        best = {**best, "x": best_x, "refinedBy": "white_outline"}

    return {
        "ok": True,
        "bestX": int(best_x),
        "bestY": int(best.get("y", y0)),
        "score": float(best["score"]),
        "votes": votes,
        "band": [int(y_lo), int(y_hi)],
        "bg": [int(bw), int(bh)],
        "piece": [int(piece.shape[1]), int(piece.shape[0])],
        "pieceBox": [x0, y0, x1 - 1, y1 - 1],
        "cropOffsetX": x0,
        "source": "opencv_multi",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="path to {b1,b2} dataURL json")
    ap.add_argument("--b1")
    ap.add_argument("--b2")
    args = ap.parse_args()
    if args.json:
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
        b1 = load_data_url(data["b1"])
        b2 = load_data_url(data["b2"])
    else:
        b1 = cv2.imread(args.b1, cv2.IMREAD_UNCHANGED)
        b2 = cv2.imread(args.b2, cv2.IMREAD_UNCHANGED)
    out = solve(b1, b2)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
