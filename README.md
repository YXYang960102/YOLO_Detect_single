# YOLO Detect Single

Vision pipeline for the TEL 2026 robot project.

This project detects `hole` targets with YOLOv8, assigns 4x3 hole IDs, detects the red LED scoring ring, and outputs a packet for Arduino:

```text
tx,ty,distance,target_id,valid
```

Example:

```text
-38,12,0,7,1
```

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Place the trained model at:

```text
weights/best.pt
```

The model file is intentionally ignored by git. Keep large model files in GitHub Releases, Git LFS, or copy them manually onto the Jetson.

## Run With Webcam

```bash
python3 vision_main.py
```

The old test entrypoint still works:

```bash
python3 test_coordinate.py
```

## Run With Serial Output

```bash
python3 vision_main.py --serial --serial-port /dev/ttyUSB0
```

On macOS the port may look like:

```bash
python3 vision_main.py --serial --serial-port /dev/tty.usbmodemXXXX
```

## Folders

```text
weights/                         trained deployment weights, not committed
samples/images/                  optional local test images, not committed
samples/videos/                  optional local test videos, not committed
TEL_2026_Field_V3.v1i.yolov8/    Roboflow YOLO dataset
runs/                            YOLO training/prediction output, not committed
```

## Notes

- `distance` is currently `0` until the AccuPick3D depth stream is connected.
- `valid=0` means no reliable red target is selected.
- `runs/` and `venv/` should not be committed.
