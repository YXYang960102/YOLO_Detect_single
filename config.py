MODEL_PATH = "weights/best.pt"

# Camera input. Use "realsense" for the Solomon SLM SVRBP-0092C and
# "opencv" when testing with a normal webcam.
CAMERA_SOURCE = "realsense"
CAMERA_INDEX = 0
IMAGE_SIZE = 640
CONFIDENCE = 0.35
# Live view only (2026-11-15, Jeremy: why a hole isn't boxed): with the
# window open YOLO runs at this lower threshold and the boxes between it
# and CONFIDENCE are drawn gray with their C -- never used for anything.
# --no-display (the match) runs at CONFIDENCE as before.
DEBUG_LOW_CONFIDENCE = 0.15

ROWS = 4
COLS = 3
TOP_ROW_SIZE_RATIO = 0.90
GRID_MEMORY_MIN_HOLES = 8
GRID_MEMORY_PARTIAL_MAX_HOLES = 5
GRID_MEMORY_MAX_DISTANCE_RATIO = 0.85
GRID_MEMORY_SMOOTHING = 0.25
GRID_GEOMETRY_MAX_ERROR_RATIO = 0.75
GRID_GEOMETRY_ANCHOR_WEIGHT = 0.35
# Tilted view (2026-11-21, Jeremy: a few degrees off and the bottom row is
# gone). Rows were grouped by plain image y, so a tilted row split into two
# and everything past the 4th "row" was dropped. Now the rows' slope is
# measured (each hole to its nearest neighbour within GRID_ROW_PAIR_MAX_DEG
# of horizontal and GRID_ROW_PAIR_MAX_GAP_RATIO median box widths, median
# angle) and, from GRID_DESKEW_MIN_DEG up, rows / columns are grouped in
# coordinates turned back by that angle. Below it nothing changes.
GRID_DESKEW_MIN_DEG = 3.0
GRID_ROW_PAIR_MAX_DEG = 35.0
GRID_ROW_PAIR_MAX_GAP_RATIO = 3.0
# Steep view (2026-11-21, Jeremy: the robot sees the board up to ~45 deg to
# the side): one side nearer, so a row's holes differ in size / y / spacing.
# When the y rows aren't a plausible grid (more than 4 rows or a row of more
# than 3), rows are rebuilt as chains of right-hand neighbours within this
# many degrees of horizontal (and the pair gap ratio above, of the wider box).
GRID_ROW_CHAIN_MAX_DEG = 25.0
# Chain link length: this x the widest of the two boxes and the median box
# (2026-11-21 capture: bonus holes are small but spaced like the big ones;
# a 145 px link failed a 142 px limit at 3.0).
GRID_ROW_CHAIN_MAX_GAP_RATIO = 4.0
# Boxes that can't be grid holes are left out before ids (2026-11-21: a face
# and a door knob boxed). Only with at least GRID_OUTLIER_MIN_HOLES boxes:
# diagonal > SIZE_RATIO x median, or nearest box > ISOLATION_RATIO x the
# median nearest-box distance.
GRID_OUTLIER_MIN_HOLES = 6
GRID_OUTLIER_SIZE_RATIO = 1.9
GRID_OUTLIER_ISOLATION_RATIO = 2.5
# Protocol v3 (2026-10-27): when the operator's hole is out of view, its
# position is predicted from the holes in view with the same affine grid
# fit the geometry assignment uses (hole_grid.predict_hole_position). Needs
# at least this many identified holes, a fit within
# GRID_GEOMETRY_MAX_ERROR_RATIO, and a prediction no more than
# GRID_PREDICT_MAX_OUTSIDE_RATIO frame widths / heights outside the frame.
GRID_PREDICT_MIN_HOLES = 3
GRID_PREDICT_MAX_OUTSIDE_RATIO = 1.0
GRID_TRACKER_MIN_MATCHES = 3
GRID_TRACKER_MAX_ERROR_RATIO = 0.65
# Downscale factor applied only inside GridTracker's optical-flow motion
# hint (not detection/tracking itself) -- 0.75 chosen as a conservative
# first step (2026-10-09) after measuring grid_tracker as the dominant,
# highly variable per-frame cost (40-141ms) on real hardware.
# 0.5 since 2026-11-01: grid_tracker was still the largest stage at 0.75
# (25 ms of a 67 ms frame on the Orin: resize+gray 9, features 10, flow 5)
# while the Orin ran 15 fps with one CPU core at 97% and the GPU mostly
# idle. Half the width and height = 1/4 of the pixels (0.75 was 0.56).
# The hint only disambiguates hole ids; tx / ty to the Mega don't use it.
GRID_TRACKER_MOTION_SCALE = 0.5

RED_SCORE_THRESHOLD = 0.05
RED_TARGET_SWITCH_MARGIN = 0.03
TARGET_STABLE_FRAMES = 3
RING_SCALE = 1.25
INNER_SCALE = 0.90

GENERAL_TARGET_CONFIDENCE = 0.50
GENERAL_TARGET_STABLE_FRAMES = 3
TARGET_EDGE_MARGIN_RATIO = 0.015
MAX_SHOTS_PER_HOLE = 3
RED_TARGET_IDS = (1, 2, 3)

SERIAL_BAUD = 115200
SERIAL_HEARTBEAT_SECONDS = 0.10
SERIAL_RECONNECT_SECONDS = 0.50
SERIAL_IDLE_POLL_SECONDS = 0.02
CONTROLLER_PROTOCOL_VERSION = 1
MEGA_HEARTBEAT_TIMEOUT_SECONDS = 1.0
CAMERA_RECOVERY_MAX_ATTEMPTS = 3
CAMERA_RECOVERY_BACKOFF_SECONDS = 1.0
CAMERA_RECOVERY_RESET_SECONDS = 10.0

# RGB-D distance estimation. All depth and serial distance values are mm.
# The ring samples the board around a detected hole instead of the empty
# center of the hole, which is normally more stable for this target.
# Ratios are of the detection box's half-size. 1.15-1.60 (2026-10-18, was
# 0.60-1.10): with the box on the hole opening, the old ring was mostly
# inside the opening (the net returns little or no depth), so the board was
# only ~25% of the ring against DEPTH_MIN_VALID_FRACTION 0.20 and the
# distance came and went with small box changes. Measured on the Orin with
# the new ring: valid 0.66-1.00 (Jeremy, bench poster at 1.44 m).
DEPTH_MIN_MM = 200
DEPTH_MAX_MM = 8000
DEPTH_RING_INNER_RATIO = 1.15
DEPTH_RING_OUTER_RATIO = 1.60
DEPTH_MIN_VALID_SAMPLES = 40
DEPTH_MIN_VALID_FRACTION = 0.20
# Dashboard ring view (2026-10-28): the ring is cut into 8 sectors (0 =
# right, clockwise on screen); a sector counts as "has depth" when at least
# this share of its pixels is usable. Display only, not the distance.
DEPTH_RING_SECTORS = 8
DEPTH_RING_SECTOR_GOOD_FRACTION = 0.5
DEPTH_MAD_SCALE = 3.5
DEPTH_SMOOTHING = 0.25

# Fallback when the outer-ring board-surface sample is unavailable or too
# noisy (reflection, glare, partial occlusion): sample inside the hole
# opening instead and correct with the field's fixed hole recess depth.
# DEPTH_HOLE_RECESS_MM is a signed offset measured on the real field:
#   z_board_mm = z_hole_mm - DEPTH_HOLE_RECESS_MM
# (positive = the hole cavity reads farther from the camera than the board
# face). Leave it None until measured on the actual field; the fallback
# stays disabled with None instead of guessing a distance.
DEPTH_HOLE_INNER_RATIO = 0.35
DEPTH_HOLE_RECESS_MM = None

# Fallback when YOLO finds zero holes in a frame (too far, hole too small in
# frame, poor lighting for RGB): detect candidate hole positions directly
# from the depth image instead. A hole's net funnel reads farther than the
# surrounding board face, or returns no depth (dark mesh material) -- both
# count as evidence. Diameters are the field's physical hole sizes (main
# 40cm, TLE bonus 20cm) with slack for measurement tolerance and off-angle
# viewing. DEPTH_HOLE_DETECT_MIN_CONFIDENCE is set above GENERAL_TARGET_CONFIDENCE
# (0.50) so depth-only candidates pass the existing target_manager reliability
# check without changing that file.
DEPTH_HOLE_DETECT_DOWNSAMPLE = 8
DEPTH_HOLE_DETECT_DEVIATION_MM = 25.0
DEPTH_HOLE_DETECT_MIN_DIAMETER_MM = 180.0
DEPTH_HOLE_DETECT_MAX_DIAMETER_MM = 420.0
DEPTH_HOLE_DETECT_DIAMETER_TOLERANCE = 0.45
DEPTH_HOLE_DETECT_MIN_AREA_PX = 20
DEPTH_HOLE_DETECT_MIN_CONFIDENCE = 0.55

# "range" sends the straight-line camera-to-target distance.
# "z" sends only the forward distance along the optical axis.
DEPTH_DISTANCE_MODE = "range"
DEPTH_DISPLAY_MAX_MM = 3000

# Solomon SLM SVRBP-0092C is an Intel RealSense active-stereo camera.
REALSENSE_WIDTH = 1280
REALSENSE_HEIGHT = 720
REALSENSE_FPS = 30
REALSENSE_SERIAL = None
REALSENSE_TIMEOUT_MS = 5000
REALSENSE_WARMUP_FRAMES = 15
REALSENSE_ENABLE_EMITTER = True
# Branch camera-process (2026-11-01): RealSense wait + align + depth
# conversion in a separate process (camera_process.ProcessCamera), on
# another CPU core, instead of ~20 ms of every frame in the vision loop.
# False = the in-process camera, exactly as on main.
CAMERA_IN_SEPARATE_PROCESS = True

# Training-image capture (2026-11-14, frame_capture.py): raw color frames
# into CAPTURE_DIR/<start time>/ with --capture-every N seconds or 'p'.
# Off unless asked for. CAPTURE_MAX_IMAGES caps the whole folder (1280x720
# JPEG ~0.2-0.3 MB each: 3000 ~ 0.6-0.9 GB of the Orin's disk).
CAPTURE_DIR = "dataset_capture"
CAPTURE_MAX_IMAGES = 3000
CAPTURE_JPEG_QUALITY = 95
# The Dashboard's P toggle (2026-11-14): one frame every this many seconds
# (--capture-every, when given, sets the interval instead).
CAPTURE_REMOTE_EVERY_SECONDS = 1.0

# Depth fills a missing hole (2026-11-15, Jeremy: other holes are seen, one
# isn't -> use the depth; every such hole counts like a YOLO one). For each
# grid hole 1-12 YOLO missed this frame that the YOLO holes in view place
# inside the frame (the v3 grid prediction), the depth detector's
# candidates (DEPTH_HOLE_DETECT_*) are searched near that spot: within
# DEPTH_CONFIRM_MAX_OFFSET_RATIO hole widths, and a candidate width of
# DEPTH_CONFIRM_MIN/MAX_SIZE_RATIO times the YOLO holes' width in that row
# (all rows when none of the row is boxed). A match is added as a seen hole
# ("depth_confirmed": target choice, seen mask, lock, ring distance, shot).
# Depth alone, without the YOLO grid placing the hole, still never counts
# (2026-08-19 review). False = YOLO holes only, as before.
DEPTH_CONFIRM_MISSING = True
DEPTH_CONFIRM_MAX_OFFSET_RATIO = 0.5
DEPTH_CONFIRM_MIN_SIZE_RATIO = 0.6
DEPTH_CONFIRM_MAX_SIZE_RATIO = 1.6
