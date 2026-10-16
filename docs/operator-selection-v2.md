# Operator target selection — protocol v2 (2026-10-16)

This is the Orin implementation contract for Claude's Mega phase 2.
Deploy matching v2 Mega and Orin together. `vision_main.main()` explicitly uses
version 2; the existing config values and the reusable VisionSerial constructor's
legacy default remain unchanged. Custom callers must pass protocol_version=2.

## Wire and lifecycle

115200 baud, newline ASCII. Mega sends MEGA_READY,2 and MEGA_HEARTBEAT,2.
Orin returns VISION_STANDBY/STARTING/READY/ERROR,2. Existing lifecycle is retained.
Mega also sends `MEGA_TARGET,2,<id>` on change and every 100 ms. Allowed ids:
0 (existing automatic behavior), 4..12 (operator choice). IDs 1..3 are bonus holes
and cannot be requested. Selection packets do not refresh the heartbeat timer.
Invalid version, missing/extra fields or invalid id are ignored; prior selection
is retained. No selection received defaults to 0. Serial reconnect/heartbeat loss
retains the last choice until a valid new selection (including 0); production
must use --wait-for-mega, and Mega must verify returned id before using a frame.

Orin sends the unchanged five fields `tx,ty,distance,target_id,valid`.
Selected hole absent/unreliable/duplicate: `0,0,0,0,0`. Never choose another hole.
Selected reliable hole: existing depth validity logic; depth-only remains invalid.
Webcam mode still allows valid=1,distance=0 (existing bench behavior); competition
must use RGB-D and Mega must gate on valid distance. Invalid depth can retain the
selected id/offsets but valid=0,distance=0, as before.

## Selection and coordinates

Mega alone converts keyboard ids. Key→vision:
1→10, 2→7, 3→4, 4→11, 5→8, 6→5, 7→12, 8→9, 9→6.
Formula for key k: col=(k-1)//3, row_bottom=(k-1)%3;
vision_id=4+(2-row_bottom)*3+col. Example key1→4+2*3+0=10.
Vision grid: top 4/5/6, middle 7/8/9, bottom 10/11/12.
No second conversion occurs in Orin.

Flow: poll_mega stores id → run_vision_session supplies it to select → operator
branch matches exactly one reliable hole → existing depth resolver → serial send.
The override uses existing confidence/edge checks but bypasses automatic ranking,
red priority, shot budget and stable-frame waiting. It leaves the automatic
manager's state untouched; id0 resumes its original code. This is deliberate
operator selection, not a change to the automatic selection algorithm.

Offsets remain pixels: tx=cx-width//2, ty=cy-height//2; right/down positive.
For (250,350) in 1000×800: tx=-250,ty=-50. Distance remains mm.
Mega numeric packet timeout stays 300 ms; existing Orin Mega-heartbeat timeout
stays 1 s. These are distinct timers, not new latency guarantees.

## Evidence and remaining limits

Host suite covers all nine choices, fragmented/malformed/versioned UART,
selection not masquerading as heartbeat, missing/duplicate/unreliable targets,
zero restoring existing behavior, unchanged automatic state, depth-only invalidity,
full-grid positional IDs and a mocked camera session through actual serial output.
No physical UART, camera recording, Jetson deployment or motor test performed.

IDs come from position/geometry/anchor memory, not semantic YOLO hole classes.
Full synthetic grid verifies row-major numbering; partial cold starts, occlusion,
tilt and flow drift remain unproven. Existing layout fallbacks can infer a position
from incomplete evidence; this addition does not certify physical ID identity.
Do not change recognition/memory to address that without Jeremy's approval.

Next: outputs disabled, paired v2 deployment; choose each key and confirm physical
hole id/offset, cover selected hole (must invalid, no fallback), restore it,
switch rapidly, restart each peer, and verify timeout/inhibit on Mega. Record
latency and partial-grid behavior before competition use.
