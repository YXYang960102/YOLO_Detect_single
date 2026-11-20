"""Step 2 of a field retrain (2026-11-14): old + new photos -> a fine-tuned
model, and a side-by-side check of the old and the new model on photos
neither was trained on.

    venv/bin/python tools/dataset/train_merge.py --new ~/Downloads/<roboflow export folder> \
        --background dataset_prepared/<time>/no_holes

  --new         the corrected new-field photos: the Roboflow "YOLOv8" export
                (unzipped; its train / valid / test folders are all used), or
                any folder with images/ + labels/. Repeatable.
  --background  photos with no hole at all (dataset_prepared/.../no_holes
                after removing the ones that do show a hole). Repeatable.
  --train-only  labeled photos that go to training only, never to the check
                (make_oblique.py's synthetic views). Repeatable.
  --old         the photos the current model was trained on (default: the
                Roboflow TEL_2026_Field_V3 set, 300 photos). Always in
                training, never in the check: the old model has seen them.

How it splits: --val-share (20 %) of the new photos and of the background
photos go to the check set, the rest to training together with all old
photos -- so the model learns the new field without forgetting the old
one, and the check is fair to both models.

Training starts from weights/best.pt (not from scratch), with wider color
/ brightness augmentation than the defaults (hsv_h 0.03, hsv_s 0.8, hsv_v
0.5) so the field's graphics matter less. weights/best.pt is never
overwritten: the new model is runs/finetune/<time>/weights/best.pt, and the
end of the output says how to try it.

The check runs both models at the robot's own threshold (config.CONFIDENCE)
and counts, with a box matching a labeled hole at IoU >= 0.5:
  抓到 / 漏抓 (labeled holes with no box) / 誤抓 (boxes on no hole,
  background photos included).
"""

import argparse
import os
import random
import shutil
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
IMAGE_EXT = (".jpg", ".jpeg", ".png")
DEFAULT_OLD = os.path.join(ROOT, "TEL_2026_Field_V3.v1i.yolov8", "train")


def pairs_in(folder):
    """[(image, label or None)] for every image under folder. The label is
    the same name in the sibling labels/ folder (YOLO / Roboflow layout)."""
    out = []
    for dirpath, _dirs, files in os.walk(folder):
        for name in sorted(files):
            if not name.lower().endswith(IMAGE_EXT):
                continue
            image = os.path.join(dirpath, name)
            parts = image.split(os.sep)
            label = None
            if "images" in parts:
                i = len(parts) - 1 - parts[::-1].index("images")
                cand = os.sep.join(parts[:i] + ["labels"] + parts[i + 1:])
                cand = os.path.splitext(cand)[0] + ".txt"
                if os.path.exists(cand):
                    label = cand
            out.append((image, label))
    return out


def read_boxes(label):
    """[(cls, x, y, w, h)] normalized; [] for no label / empty."""
    if not label:
        return []
    boxes = []
    with open(label) as f:
        for n, line in enumerate(f, 1):
            p = line.split()
            if not p:
                continue
            if len(p) != 5:
                sys.exit(f"{label} 第 {n} 行不是 YOLO 框（class x y w h）。"
                         "Roboflow 匯出時要選 YOLOv8（偵測框），不是多邊形分割")
            boxes.append((int(p[0]), *map(float, p[1:])))
    return boxes


def place(items, dest, tag, background=False):
    """Copy (image, label) pairs into dest/images + dest/labels; background
    photos get an empty label (= "no hole here")."""
    os.makedirs(os.path.join(dest, "images"), exist_ok=True)
    os.makedirs(os.path.join(dest, "labels"), exist_ok=True)
    for i, (image, label) in enumerate(items):
        base = f"{tag}_{i:05d}_{os.path.basename(image)}"
        shutil.copy2(image, os.path.join(dest, "images", base))
        stem = os.path.splitext(base)[0]
        with open(os.path.join(dest, "labels", stem + ".txt"), "w") as f:
            if label and not background:
                with open(label) as src:
                    f.write(src.read())


def iou(a, b):
    ax0, ay0, ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx0, by0, bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def check(weights, val_dir, conf, imgsz, device):
    """(hit, missed, false, false_on_background) for one model."""
    from ultralytics import YOLO
    model = YOLO(weights)
    images = sorted(os.path.join(val_dir, "images", n) for n in os.listdir(os.path.join(val_dir, "images")))
    hit = missed = false = false_bg = 0
    for image, result in zip(images, model.predict(source=images, imgsz=imgsz, conf=conf, device=device,
                                                   stream=True, verbose=False)):
        stem = os.path.splitext(os.path.basename(image))[0]
        truth = [b[1:] for b in read_boxes(os.path.join(val_dir, "labels", stem + ".txt"))]
        found = result.boxes.xywhn.tolist() if result.boxes is not None else []
        used = set()
        for t in truth:
            best, best_j = 0.0, None
            for j, p in enumerate(found):
                if j in used:
                    continue
                v = iou(t, p)
                if v > best:
                    best, best_j = v, j
            if best >= 0.5:
                used.add(best_j)
                hit += 1
            else:
                missed += 1
        extra = len(found) - len(used)
        false += extra
        if not truth:
            false_bg += extra
    return hit, missed, false, false_bg


def pick_device():
    import torch
    if torch.cuda.is_available():
        return 0
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new", action="append", default=[], help="corrected new-field set (repeatable)")
    ap.add_argument("--background", action="append", default=[], help="no-hole photos (repeatable)")
    ap.add_argument("--train-only", action="append", default=[],
                    help="labeled photos for training only, e.g. make_oblique.py output (repeatable)")
    ap.add_argument("--old", default=DEFAULT_OLD, help="the current model's training photos")
    ap.add_argument("--base", default=os.path.join(ROOT, "weights", "best.pt"), help="model to start from")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--patience", type=int, default=15,
                    help="stop after this many epochs with no val improvement (>= --epochs: never stop early)")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--val-share", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--work", default=os.path.join(ROOT, "datasets_merged"), help="merged dataset folder")
    ap.add_argument("--project", default=os.path.join(ROOT, "runs", "finetune"), help="training output")
    ap.add_argument("--device", default=None, help="mps / cpu / 0 (default: what this computer has)")
    ap.add_argument("--check-only", default=None, metavar="MERGED_DIR",
                    help="skip training: only compare --base and --compare on MERGED_DIR/val")
    ap.add_argument("--compare", default=None, help="with --check-only: the second model")
    args = ap.parse_args()

    import config  # the robot's own threshold
    conf = float(config.CONFIDENCE)
    device = args.device if args.device is not None else pick_device()

    if args.check_only:
        val_dir = os.path.join(args.check_only, "val")
        report(val_dir, [("舊 " + args.base, args.base)] + ([("新 " + args.compare, args.compare)] if args.compare else []),
               conf, args.imgsz, device)
        return

    if not args.new:
        sys.exit("要給 --new（Roboflow 匯出、修正過的新場地照片資料夾）")
    rng = random.Random(args.seed)
    new_pairs, bg_pairs = [], []
    for folder in args.new:
        got = pairs_in(os.path.expanduser(folder))
        if not got:
            sys.exit(f"{folder} 裡沒有照片")
        new_pairs += got
    for folder in args.background:
        bg_pairs += [(img, None) for img, _ in pairs_in(os.path.expanduser(folder))]
    old_pairs = pairs_in(args.old)
    extra_pairs = []
    for folder in args.train_only:
        got = pairs_in(os.path.expanduser(folder))
        if not got:
            sys.exit(f"{folder} 裡沒有照片")
        extra_pairs += got
    unlabeled = [img for img, lbl in new_pairs if lbl is None]

    classes = {b[0] for _, lbl in new_pairs + old_pairs + extra_pairs for b in read_boxes(lbl)}
    if classes - {0}:
        sys.exit(f"標註裡有類別 {sorted(classes)}：這個模型只有一類 hole（0）。"
                 "Roboflow 專案只能有 hole 一個類別")

    rng.shuffle(new_pairs)
    rng.shuffle(bg_pairs)
    n_val = max(1, round(len(new_pairs) * args.val_share))
    b_val = round(len(bg_pairs) * args.val_share)
    work = os.path.join(args.work, time.strftime("%Y%m%d_%H%M%S"))
    place(old_pairs, os.path.join(work, "train"), "old")
    place(new_pairs[n_val:], os.path.join(work, "train"), "new")
    place(bg_pairs[b_val:], os.path.join(work, "train"), "bg", background=True)
    place(extra_pairs, os.path.join(work, "train"), "extra")
    place(new_pairs[:n_val], os.path.join(work, "val"), "new")
    place(bg_pairs[:b_val], os.path.join(work, "val"), "bg", background=True)
    data_yaml = os.path.join(work, "data.yaml")
    with open(data_yaml, "w") as f:
        f.write(f"path: {work}\ntrain: train/images\nval: val/images\nnc: 1\nnames: ['hole']\n")
    print(f"訓練：舊 {len(old_pairs)} + 新 {len(new_pairs) - n_val} + 背景 {len(bg_pairs) - b_val} 張"
          + (f" + 只訓練用 {len(extra_pairs)} 張" if extra_pairs else ""))
    print(f"檢查：新 {n_val} + 背景 {b_val} 張（兩個模型都沒訓練過）")
    if unlabeled:
        print(f"注意：新照片裡 {len(unlabeled)} 張沒有標註檔，當成沒有洞（Roboflow 的 null 照片就是這樣）")
    print(f"合併資料：{work}  裝置：{device}\n")

    from ultralytics import YOLO
    model = YOLO(args.base)
    model.train(data=data_yaml, epochs=args.epochs, batch=args.batch, imgsz=args.imgsz, device=device,
                patience=args.patience, project=args.project, name=os.path.basename(work),
                hsv_h=0.03, hsv_s=0.8, hsv_v=0.5, plots=True, verbose=False)
    new_best = os.path.join(str(model.trainer.save_dir), "weights", "best.pt")

    report(os.path.join(work, "val"), [("舊 weights/best.pt", args.base), ("新 " + new_best, new_best)],
           conf, args.imgsz, device)
    print("\n新模型比較好的話，先在 Orin 上備份舊的再換（指令見 tools/dataset/README.md）：")
    print(f"  新模型：{new_best}")


def report(val_dir, models, conf, imgsz, device):
    print(f"\n檢查（conf {conf}，跟機器人一樣；框和標註 IoU >= 0.5 才算抓到）")
    print(f"{'模型':<12}{'抓到':>6}{'漏抓':>6}{'誤抓':>6}{'背景上誤抓':>10}{'抓到率':>8}")
    for label, weights in models:
        hit, missed, false, false_bg = check(weights, val_dir, conf, imgsz, device)
        rate = hit / (hit + missed) if hit + missed else 0.0
        print(f"{label.split()[0]:<12}{hit:>6}{missed:>6}{false:>6}{false_bg:>10}{rate:>8.0%}   {label.split(' ', 1)[1]}")


if __name__ == "__main__":
    main()
