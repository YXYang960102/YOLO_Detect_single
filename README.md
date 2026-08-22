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

For the competition power sequence, keep Orin powered and wait for the Mega
UART heartbeat before loading YOLO or starting RealSense:

```bash
python3 test_coordinate.py --source realsense \
  --serial --serial-port /dev/ttyTHS1 --wait-for-mega
```

`/dev/ttyTHS1` is an example Jetson header-UART device name. Replace it with
the UART device verified on the deployed Orin.

On some Linux systems, the user must be added to the serial device group before using `/dev/ttyUSB0` or `/dev/ttyACM0`:

```bash
sudo usermod -a -G dialout $USER
```

Log out and log back in after changing the group.

## Orin / Mega Power-Gated Startup

`--wait-for-mega` is opt-in so ordinary webcam and RealSense tests retain their
existing immediate-start behavior. It requires both `--serial` and an explicit
`--serial-port`.

The UART is ASCII, newline-delimited, 115200 baud, protocol version `1`:

| Direction | Message | Meaning |
| --- | --- | --- |
| Mega → Orin | `MEGA_READY,1` | Mega completed safe firmware initialization. |
| Mega → Orin | `MEGA_HEARTBEAT,1` | Mega is still powered and running. |
| Orin → Mega | `VISION_STANDBY,1` | Orin is waiting without a model or camera stream. |
| Orin → Mega | `VISION_STARTING,1` | Orin is loading/warming the model and camera. |
| Orin → Mega | `VISION_READY,1` | Warm-up completed; vision packets may be consumed. |
| Orin → Mega | `VISION_ERROR,1` | Vision output is unavailable; recovery is running or a fatal exit is pending. |
| Orin → Mega | `tx,ty,distance,target_id,valid` | Existing target packet, unchanged. |

Mega should repeat `MEGA_READY,1` or `MEGA_HEARTBEAT,1`; a one-time boot line
can be missed if Orin opens the UART later. Orin polls at 20 ms intervals while
waiting and treats the Mega link as lost after 1.0 s without a valid version-1
heartbeat. For example, if the last heartbeat was received at `12.4 s`, the
session remains active through `13.4 s`; after that it closes RealSense,
releases the model/CUDA cache, clears vision tracking state, and returns to
`WAIT_MEGA`.

The state flow is:

```text
WAIT_MEGA --MEGA_READY/HEARTBEAT--> STARTING --warm-up--> ACTIVE
ACTIVE --1.0 s heartbeat timeout--> WAIT_MEGA
ACTIVE --recoverable camera error--> ERROR --reopen succeeds--> ACTIVE
ERROR --camera retries exhausted/fatal error--> process exit --> systemd restart
```

During `WAIT_MEGA`, `ultralytics`, PyTorch/CUDA, the YOLO model, and the
RealSense pipeline are not loaded or started. Linux and the lightweight Python
UART monitor remain running. The measured Mega-power-on to `VISION_READY` time
is printed to the terminal and must be confirmed on the real Orin against the
45-second competition loading window.

### Two-layer vision recovery

A recoverable RealSense open, warm-up, frame-wait, alignment, or frame-access
error immediately forces the neutral numeric packet `0,0,0,0,0`, announces
`VISION_ERROR,1`, closes the failed camera pipeline, and reopens it without
reloading the YOLO model. Per-camera tracking and depth state are rebuilt. The
default policy allows 3 reopen attempts with a 1.0-second delay; after at least
10 seconds of stable active operation, the consecutive-failure count resets.

The fourth consecutive camera failure raises a fatal error and exits non-zero.
Model loading, CUDA/inference, configuration, and unexpected programming errors
also remain fatal instead of being mistaken for camera faults. A systemd
service can then provide process-level recovery. The repository includes an
editable [deployment example](deploy/README.md), but does not install or enable
it automatically.

With the current 5000 ms RealSense frame timeout, one missing-frame failure can
take up to about 5 seconds to be detected before the 1-second reopen delay,
camera exposure warm-up, and first inference. `VISION_READY,1` is sent again
only after that first inference succeeds. The Mega must treat every
`VISION_ERROR,1` as invalid output and keep actuators using its safe behavior
until a later `VISION_READY,1` arrives.

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

If YOLO finds zero holes in a frame (too far, hole too small in frame, poor
lighting), `depth_hole_detector.py` looks for candidate hole positions directly
in the depth image instead -- a hole's net funnel reads farther than the
surrounding board face, or returns no depth at all, and either counts as
evidence. Candidates are filtered by the field's physical hole diameters
(main 40cm, TLE bonus 20cm) at the locally estimated distance. The debug
overlay's `Det:` field shows `yolo` or `depth` per frame.

**`Det:depth` is fully observation-only.** A depth-only detection has no
RGB/YOLO evidence a real hole is there -- ordinary sensor dropout
(reflection, noise, edge, out-of-range) looks identical to a hole to this
detector. Depth-only candidates never reach the grid-ID memory, `GridTracker`,
red-target stabilizer, or `TargetManager` -- they get display-only IDs
(`build_observation_holes`) and are drawn straight to the debug overlay, so a
noisy frame can never bias what a later YOLO frame locks onto. The serial
packet for a depth-only frame is always the canonical neutral
`(0, 0, 0, 0, 0)`. This stays true until a depth-specific quality gate is
built from real RealSense captures.

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
