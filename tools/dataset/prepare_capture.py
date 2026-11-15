"""Step 1 of a field retrain (2026-11-14): photos from the robot -> a folder
ready to upload to Roboflow, already boxed by the current model.

    venv/bin/python tools/dataset/prepare_capture.py

What it does, in this order:
  1. Collects every .jpg under dataset_capture/ (all session folders the
     Orin's P key / --capture-every made, copied to the Mac with rsync).
  2. Drops near-duplicates: a robot standing still saves the same view
     every second. Two photos count as the same when their 64-bit dHash
     differs in at most --dup-bits bits (default 6 of 64).
  3. Runs the current weights/best.pt on the rest (conf --conf, default
     0.25: lower than the robot's 0.35 on purpose, so faint holes get a box
     to check instead of being missed).
  4. Writes  dataset_prepared/<time>/
         upload/   images + YOLO .txt labels + data.yaml  -> Roboflow
         no_holes/ photos where the model found nothing   -> look at them:
                   really no hole = a background photo (teaches "these
                   graphics are not holes"); a hole there = the model
                   missed it, upload it too and draw the box by hand.
         report.txt
Nothing in dataset_capture/ is changed or deleted.
"""

import argparse
import os
import shutil
import sys
import time

import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMAGE_EXT = (".jpg", ".jpeg", ".png")


def dhash(path):
    """64-bit difference hash of a grayscale 9x8 thumbnail, or None."""
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    small = cv2.resize(img, (9, 8), interpolation=cv2.INTER_AREA)
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (1 if small[y, x + 1] > small[y, x] else 0)
    return bits


def collect(src):
    paths = []
    for dirpath, _dirs, files in os.walk(src):
        for name in files:
            if name.lower().endswith(IMAGE_EXT):
                paths.append(os.path.join(dirpath, name))
    return sorted(paths)  # session folder + running number = capture order


def dedupe(paths, max_bits):
    kept, kept_hashes, unreadable = [], [], 0
    for path in paths:
        h = dhash(path)
        if h is None:
            unreadable += 1
            continue
        if any(bin(h ^ k).count("1") <= max_bits for k in kept_hashes):
            continue
        kept.append(path)
        kept_hashes.append(h)
    return kept, unreadable


def unique_name(path, src):
    # 20261114_153012/000001_153013.jpg -> 20261114_153012_000001_153013.jpg
    rel = os.path.relpath(path, src)
    return rel.replace(os.sep, "_")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.path.join(ROOT, "dataset_capture"),
                    help="folder with the captured photos (default: dataset_capture/)")
    ap.add_argument("--out", default=os.path.join(ROOT, "dataset_prepared"),
                    help="where the prepared folder goes (default: dataset_prepared/)")
    ap.add_argument("--weights", default=os.path.join(ROOT, "weights", "best.pt"))
    ap.add_argument("--conf", type=float, default=0.25, help="box threshold for the pre-labels")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--dup-bits", type=int, default=6,
                    help="dHash bits two photos may differ by and still be duplicates (0-64)")
    ap.add_argument("--max", type=int, default=0, help="keep at most this many (0 = all), spread evenly")
    args = ap.parse_args()

    paths = collect(args.src)
    if not paths:
        sys.exit(f"沒有照片：{args.src} 裡找不到 .jpg / .png（先用 rsync 從 Orin 拉回來）")
    kept, unreadable = dedupe(paths, args.dup_bits)
    if args.max and len(kept) > args.max:
        step = len(kept) / args.max
        kept = [kept[int(i * step)] for i in range(args.max)]
    print(f"照片 {len(paths)} 張，去掉重複後 {len(kept)} 張"
          + (f"（{unreadable} 張讀不到，已略過）" if unreadable else ""))

    from ultralytics import YOLO  # slow import: only once there is work
    model = YOLO(args.weights)

    out = os.path.join(args.out, time.strftime("%Y%m%d_%H%M%S"))
    up_img = os.path.join(out, "upload", "images")
    up_lbl = os.path.join(out, "upload", "labels")
    none_dir = os.path.join(out, "no_holes")
    for d in (up_img, up_lbl, none_dir):
        os.makedirs(d, exist_ok=True)

    with_holes = boxes_total = 0
    no_holes = []
    for path, result in zip(kept, model.predict(source=kept, imgsz=args.imgsz, conf=args.conf,
                                                stream=True, verbose=False)):
        name = unique_name(path, args.src)
        stem = os.path.splitext(name)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            shutil.copy2(path, os.path.join(none_dir, name))
            no_holes.append(name)
            continue
        shutil.copy2(path, os.path.join(up_img, name))
        lines = []
        for cls, (x, y, w, h) in zip(boxes.cls.tolist(), boxes.xywhn.tolist()):
            lines.append(f"{int(cls)} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
        with open(os.path.join(up_lbl, stem + ".txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        with_holes += 1
        boxes_total += len(lines)

    names = getattr(model, "names", {0: "hole"})
    with open(os.path.join(out, "upload", "data.yaml"), "w") as f:
        f.write(f"nc: {len(names)}\nnames: {[names[i] for i in sorted(names)]}\n")

    report = [
        f"來源：{args.src}（{len(paths)} 張，去重後 {len(kept)} 張，dup-bits {args.dup_bits}）",
        f"模型：{args.weights}，conf {args.conf}",
        f"有框到洞：{with_holes} 張，共 {boxes_total} 個框 -> upload/",
        f"沒框到洞：{len(no_holes)} 張 -> no_holes/（要人看：真的沒洞 = 背景照；有洞 = 漏抓，要補框）",
    ]
    with open(os.path.join(out, "report.txt"), "w") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report))
    print(f"\n輸出在：{out}")


if __name__ == "__main__":
    main()
