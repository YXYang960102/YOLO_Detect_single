# Operator target selection — protocol v3 (2026-10-27)

v3 extends [v2](operator-selection-v2.md). Deploy it together with the
matching TEL_Robot_2026 Mega firmware (its `VisionConstants::Transport::
PROTOCOL_VERSION = 3`). A v2 peer is refused both ways: lifecycle and
heartbeat lines carry the version, and the frame now has six fields.
`vision_main.main()` uses version 3. `VisionSerial(protocol_version=2)`
still behaves exactly as v2; the existing v2 tests run unchanged.

## What changes

| | v2 | v3 |
|---|---|---|
| `MEGA_TARGET,<v>,<id>` | 0, 4–12 | 0–12: the bonus holes 1–3 (Dashboard Q W E) can be chosen |
| Frame | `tx,ty,distance,target_id,valid` | `tx,ty,distance,target_id,valid,seen_mask` |
| `valid` | 0 / 1 | 0 / 1 / **2 = predicted** |
| Selected hole in view, depth invalid | `valid=0` | `valid=1, distance=0`: tx/ty kept |
| Selected hole out of view | `0,0,0,0,0` | predicted position, `valid=2`, distance 0, when the grid fit allows it; otherwise as before |

- **`seen_mask`**: bit `id − 1` is set for every reliable, RGB-detected hole
  in this frame (`TargetManager.seen_mask`). Depth-only detections never
  count. Example: ids 4, 5, 8 → 8 + 16 + 128 = 152.
- **Prediction** (`hole_grid.predict_hole_position`, used by
  `TargetManager.select(..., predict_missing=True)`). It is only used when
  the chosen hole is absent or unreliable.
  - Each id has canonical grid coordinates `col = (id−1) % 3`,
    `row = (id−1) // 3`. Row 0 is the bonus row.
  - A least-squares affine fit over the other identified holes:
    `x = a·col + b·row + c`, `y = d·col + e·row + f`. This is the same model
    `geometry_assignment_score` uses.
  - That fit is then evaluated at the chosen hole's (col, row).
  - It is refused when:
    - fewer than `GRID_PREDICT_MIN_HOLES` (3) other holes are identified;
    - the target column (row) isn't in view and fewer than 2 columns
      (rows) are;
    - the fit's mean error is above `GRID_GEOMETRY_MAX_ERROR_RATIO` hole
      sizes;
    - the result is more than `GRID_PREDICT_MAX_OUTSIDE_RATIO` (1.0) frame
      sizes outside the frame.
  - Example in a 1280×720 frame:
    - the left and middle columns are at x = 900 and 1150, so
      a = 250 px/column and c = 900;
    - the right column (col 2) comes out at x = 1400, outside the frame;
    - tx = 1400 − 640 = **+760**, so the turret turns right.
- **Mega side**:
  - A predicted frame is aim-only. `Vision::isPredicted()` makes the turret
    follow tx, but it is never `isValid()`, never a lock, a distance or a
    shot.
  - tx is accepted up to ±4000 and clamped to ±400 for the controller.
  - The Mega stops following predictions 3 s after the first one, unless
    the hole is really seen or the selection changes.

## Test overlay

`--show-depth-ring` (or key `d` in the display window) draws the target's
depth sampling ring exactly as `depth_distance` samples it: the ellipse
annulus `DEPTH_RING_INNER_RATIO`…`DEPTH_RING_OUTER_RATIO` × the box half-size.
- Sampled pixels are tinted green (usable depth) or red (missing or out of
  range).
- It also shows `ring good/total`.
- A predicted target is drawn as a magenta arrow from the frame center with
  `PRED <id>`.
- It costs a few ms per frame. Keep it off for matches.

## Evidence

- `venv/bin/python -m unittest discover -s tests`: 62 tests, OK. That is the
  54 v2 tests unchanged, plus 8 v3 cases in
  `tests/test_operator_selection.py`:
  - v3 accepts 0–12 and only v3;
  - the 6-field packet (v2 stays 5 fields);
  - bonus selection only with `allow_bonus`;
  - the predicted position (1400, 360), with `valid=2`;
  - `seen_mask`;
  - depth failure keeps `valid=1` only in v3;
  - the overlays draw;
  - an end-to-end v3 session sends `500,-150,0,6,2,<mask>`.
- Not run on the Jetson, a camera, or the field.

## Remaining limits

- The bonus holes' depth ring is the same ratio as the big holes. Check on
  the field that it gives a distance (use the `d` overlay).
- The bonus row's predicted y uses the grid's row spacing, which is
  approximate for the bonus row. It only matters for turning toward it.
