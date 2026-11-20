"""Synthetic oblique and edge-cut views of labeled photos (2026-11-21, Jeremy:
"只要角度斜一點點下面那列就照不到"; no real oblique photos yet, so make them
from straight ones; holes cut by the frame edge must be in too).

    venv/bin/python tools/dataset/make_oblique.py --src dataset_prepared/raw_v3v4_labeled \
        --only 20261120 --exclude-val datasets_merged/<time> --out dataset_prepared/oblique_train
    venv/bin/python tools/dataset/make_oblique.py --check --src datasets_merged/<time>/val \
        --out dataset_prepared/oblique_check

How a view is made: the photo is a flat board facing the camera (D435 color,
69.4 deg wide). The board turns about its own center -- up / down / left /
right -- so the near side grows and the far side shrinks, like a robot
standing off to one side. The turned board is refit into 1280x720 with gray
114 (YOLO's own padding color) around it. A "cut" view then zooms 1.2-1.8x
and shifts, so some holes cross the frame edge.

Labels: each hole box becomes the box around 32 points of the ellipse inside
it, after the turn. Clipped by the frame, a box is kept (clipped) when at
least --keep-share (25 %) of it is still in the frame and it is at least
--min-px wide and high; otherwise dropped.

Training set (default): from --src photos whose name starts with --only,
minus the ones in --exclude-val (the check photos: never train on what the
check uses), --share of them (50 %) at random. Per photo: 4 directions x
(one 10-15 deg + one 20-70 deg), each one fit or cut at random, plus one
straight cut view = 9 views.

--check: every --src photo, 4 directions x 15 and 45 deg, once fit (out/fit)
and once cut (out/cut). Each is a folder train_merge.py --check-only reads
as MERGED_DIR/val.
"""

import argparse
import math
import os
import random
import re
import sys

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
W, H = 1280, 720
F = W / (2 * math.tan(math.radians(69.4 / 2)))
DIRECTIONS = ("up", "down", "left", "right")


def board_homography(direction, deg):
    """3x3: the photo as a board turned `deg` about its center, refit into the frame."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    rot = {"up": [[1, 0, 0], [0, c, -s], [0, s, c]], "down": [[1, 0, 0], [0, c, s], [0, -s, c]],
           "left": [[c, 0, s], [0, 1, 0], [-s, 0, c]], "right": [[c, 0, -s], [0, 1, 0], [s, 0, c]],
           "none": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}[direction]
    rot = np.array(rot)
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = []
    for u, v in src:
        p = rot @ np.array([u - W / 2, v - H / 2, 0.0]) + np.array([0, 0, F])
        dst.append([F * p[0] / p[2] + W / 2, F * p[1] / p[2] + H / 2])
    dst = np.float32(dst)
    x0, y0 = dst.min(0)
    x1, y1 = dst.max(0)
    k = min(W / (x1 - x0), H / (y1 - y0), 1.0)
    dst = (dst - [(x0 + x1) / 2, (y0 + y1) / 2]) * k + [W / 2, H / 2]
    return cv2.getPerspectiveTransform(src, np.float32(dst))


def zoom_shift(scale, dx, dy):
    """3x3: zoom about the frame center, then shift by (dx, dy) px."""
    return np.array([[scale, 0, (1 - scale) * W / 2 + dx], [0, scale, (1 - scale) * H / 2 + dy], [0, 0, 1]])


def warp_boxes(boxes, hm, keep_share, min_px):
    """[(cls, x, y, w, h)] after hm; (boxes, n_clipped)."""
    t = np.linspace(0, 2 * math.pi, 32, endpoint=False)
    out, clipped = [], 0
    for cls, x, y, w, h in boxes:
        pts = np.stack([(x + w / 2 * np.cos(t)) * W, (y + h / 2 * np.sin(t)) * H], 1)
        p = cv2.perspectiveTransform(pts.astype(np.float32).reshape(-1, 1, 2), hm).reshape(-1, 2)
        a0, b0 = p.min(0)
        a1, b1 = p.max(0)
        full = (a1 - a0) * (b1 - b0)
        c0, d0, c1, d1 = max(a0, 0), max(b0, 0), min(a1, W), min(b1, H)
        if c1 <= c0 or d1 <= d0 or full <= 0:
            continue
        if (c1 - c0) * (d1 - d0) < keep_share * full or c1 - c0 < min_px or d1 - d0 < min_px:
            continue
        if (c0, d0, c1, d1) != (a0, b0, a1, b1):
            clipped += 1
        out.append((cls, (c0 + c1) / 2 / W, (d0 + d1) / 2 / H, (c1 - c0) / W, (d1 - d0) / H))
    return out, clipped


def read_boxes(label):
    boxes = []
    if os.path.exists(label):
        for line in open(label):
            p = line.split()
            if len(p) == 5:
                boxes.append((int(p[0]), *map(float, p[1:])))
    return boxes


def make_view(img, boxes, direction, deg, cut, rng, keep_share, min_px):
    """(image, boxes) or None when no usable cut came out in 15 tries."""
    base = board_homography(direction, deg)
    if not cut:
        b, _ = warp_boxes(boxes, base, keep_share, min_px)
        return cv2.warpPerspective(img, base, (W, H), borderValue=(114, 114, 114)), b
    for _ in range(15):
        hm = zoom_shift(rng.uniform(1.2, 1.8), rng.uniform(-0.35, 0.35) * W, rng.uniform(-0.35, 0.35) * H) @ base
        b, clipped = warp_boxes(boxes, hm, keep_share, min_px)
        if clipped >= 1 and len(b) >= 2:
            return cv2.warpPerspective(img, hm, (W, H), borderValue=(114, 114, 114)), b
    return None


def save(out_dir, name, img, boxes):
    cv2.imwrite(os.path.join(out_dir, "images", name + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    with open(os.path.join(out_dir, "labels", name + ".txt"), "w") as f:
        for cls, x, y, w, h in boxes:
            f.write(f"{cls} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="folder with images/ + labels/")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="", help="training set: only photos whose name starts with this")
    ap.add_argument("--exclude-val", default=None, metavar="MERGED_DIR",
                    help="training set: leave out the photos in MERGED_DIR/val (train_merge.py's check)")
    ap.add_argument("--share", type=float, default=0.5, help="training set: share of the photos to use")
    ap.add_argument("--check", action="store_true", help="make the fixed check views instead")
    ap.add_argument("--keep-share", type=float, default=0.25)
    ap.add_argument("--min-px", type=float, default=6)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    names = sorted(os.path.splitext(n)[0] for n in os.listdir(os.path.join(args.src, "images"))
                   if n.lower().endswith((".jpg", ".jpeg", ".png")))
    if not names:
        sys.exit(f"{args.src}/images 裡沒有照片")

    def load(n):
        for ext in (".jpg", ".jpeg", ".png"):
            p = os.path.join(args.src, "images", n + ext)
            if os.path.exists(p):
                img = cv2.imread(p)
                if img.shape[:2] != (H, W):
                    img = cv2.resize(img, (W, H))
                return img, read_boxes(os.path.join(args.src, "labels", n + ".txt"))
        return None, []

    if args.check:
        counts = {}
        for kind in ("fit", "cut"):
            out = os.path.join(args.out, kind, "val")
            os.makedirs(os.path.join(out, "images"), exist_ok=True)
            os.makedirs(os.path.join(out, "labels"), exist_ok=True)
            counts[kind] = 0
            for n in names:
                img, boxes = load(n)
                for d in DIRECTIONS:
                    for deg in (15, 45):
                        v = make_view(img, boxes, d, deg, kind == "cut", rng, args.keep_share, args.min_px)
                        if v is None:
                            continue
                        save(out, f"{n}_{d}{deg}_{kind}", *v)
                        counts[kind] += 1
        print(f"檢查用：斜 {counts['fit']} 張（{args.out}/fit）、斜加切邊 {counts['cut']} 張（{args.out}/cut）")
        return

    excluded = set()
    if args.exclude_val:
        for n in os.listdir(os.path.join(args.exclude_val, "val", "images")):
            excluded.add(re.sub(r"^[a-z]+_\d{5}_", "", os.path.splitext(n)[0]))
    pool = [n for n in names if n.startswith(args.only) and n not in excluded]
    rng.shuffle(pool)
    picked = sorted(pool[:max(1, round(len(pool) * args.share))])
    os.makedirs(os.path.join(args.out, "images"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "labels"), exist_ok=True)
    made = cut_made = 0
    for n in picked:
        img, boxes = load(n)
        jobs = [(d, rng.uniform(10, 15)) for d in DIRECTIONS] + [(d, rng.uniform(20, 70)) for d in DIRECTIONS]
        views = [(d, deg, rng.random() < 0.5) for d, deg in jobs] + [("none", 0.0, True)]
        for d, deg, cut in views:
            v = make_view(img, boxes, d, deg, cut, rng, args.keep_share, args.min_px)
            if v is None or not v[1]:
                continue
            save(args.out, f"{n}_{d}{deg:.0f}{'_cut' if cut else ''}", *v)
            made += 1
            cut_made += cut
    print(f"照片 {len(pool)} 張可用（排除檢查用 {len([n for n in names if n.startswith(args.only) and n in excluded])} 張），"
          f"挑 {len(picked)} 張 -> {made} 張斜照片（其中 {cut_made} 張有切邊）：{args.out}")


if __name__ == "__main__":
    main()
