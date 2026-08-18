# YOLO Detect Single

Vision pipeline for the TEL 2026 robot project.

This project detects `hole` targets with YOLOv8, assigns 4x3 hole IDs, detects the red LED scoring ring, selects a reliable autonomous target, and outputs a packet for Arduino:

```text
tx,ty,distance,target_id,valid
```

Example:

```text
-38,12,0,7,1
```

## Model File

Place the trained model at:

```text
weights/best.pt
```

The model file is intentionally ignored by git. Keep large model files in GitHub Releases, Git LFS, or copy them manually onto the Jetson.

## Windows Setup

Open PowerShell in this project folder:

```powershell
cd path\to\YOLO_Detect_single
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the virtual environment activation script, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate the environment again:

```powershell
.\venv\Scripts\Activate.ps1
```

Run with the default webcam:

```powershell
python vision_main.py
```

Run with serial output:

```powershell
python vision_main.py --serial --serial-port COM3
```

Replace `COM3` with the Arduino port shown in Device Manager.

## macOS Setup

Open Terminal in this project folder:

```bash
cd /path/to/YOLO_Detect_single
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

Run with the default webcam:

```bash
python3 vision_main.py
```

Run with serial output:

```bash
python3 vision_main.py --serial --serial-port /dev/tty.usbmodemXXXX
```

Replace `/dev/tty.usbmodemXXXX` with the Arduino port on your Mac.

## Linux Setup

Open a terminal in this project folder:

```bash
cd /path/to/YOLO_Detect_single
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

Run with the default webcam:

```bash
python3 vision_main.py
```

Run with serial output:

```bash
python3 vision_main.py --serial --serial-port /dev/ttyUSB0
```

On some Linux systems, the user must be added to the serial device group before using `/dev/ttyUSB0` or `/dev/ttyACM0`:

```bash
sudo usermod -a -G dialout $USER
```

Log out and log back in after changing the group.

## Autonomous Target Selection

- A stable red target on top-row ID 1, 2, or 3 has first priority.
- Without a reliable red target, the selector prefers a reliable large hole that needs less aiming movement.
- A normal target must remain stable for several frames before `valid=1`.
- Boxes touching the frame edge or below the general-target confidence threshold are rejected.
- A locked normal target is retained while it remains reliable, preventing frame-to-frame target changes.
- After all 12 holes are seen, a temporal grid tracker preserves IDs during gradual camera movement and vertical or horizontal cropping.
- If fewer than three holes can be matched reliably after the board is remembered, the frame is rejected instead of guessing IDs.
- The existing grid ID, geometry, and anchor-memory calculations in `hole_grid.py` run before this selection layer and are unchanged.

For camera-only testing, press `s` to simulate one confirmed shot at the current target. After three simulated shots, that ID is excluded. Press `c` to clear all simulated shot counts. Real shot counting will require a confirmed ball-sensor message from Arduino.

## Run Notes

Show the full target board once before testing partial views. The vision code remembers stable hole positions when enough holes are visible, then uses that memory only when the frame has very few holes left. Press `r` in the display window to reset the remembered grid after moving the camera a lot. Press `Esc` to close the display window.

With the RealSense source, distance is estimated from the aligned depth image.
The primary sample is the board-surface ring around the selected hole. A second
path can sample inside the hole when the ring is invalid, but it remains disabled
while `DEPTH_HOLE_RECESS_MM` is `None`. Measure the signed recess on the real
field before enabling it; the correction is:

```text
board_z_mm = hole_z_mm - DEPTH_HOLE_RECESS_MM
```

The debug overlay reports `Src:ring` or `Src:hole_fallback`. With RealSense,
invalid depth forces `valid=0` so the controller does not act on a target with an
unknown distance. A normal OpenCV webcam has no depth stream, so it preserves the
camera-only test behavior: target coordinates may remain valid while distance is
`0`.

The old test entrypoint still works:

```bash
python3 test_coordinate.py
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

- `distance` is measured in millimetres from RealSense depth when available; it
  remains `0` for an OpenCV webcam or an invalid depth estimate.
- `valid=0` means neither a reliable red target nor a reliable normal target is selected.
- The serial packet is repeated as a heartbeat even when its values do not change, allowing Arduino to detect a lost Jetson connection.
- `runs/` and `venv/` should not be committed.
