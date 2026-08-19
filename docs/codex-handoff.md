# Claude → Codex Handoff Log

Chronological notes for Codex (or anyone continuing this work) on what Claude
changed in this repo, session by session. Newest entry at the bottom.

---

## 2026-08-17 — Hole-depth fallback for distance estimation

**Changed**
- `depth_distance.py`: `DepthEstimator.measure()` refactored into
  `_estimate_z()` + shared `_sample_region()`. Ring-based board-surface
  sampling (`_ring_values`) is unchanged in behavior; it is now the primary
  path with a fallback attached after it.

**Added**
- `DepthEstimator._inner_values()`: samples inside the hole opening
  (`0 ~ hole_inner_ratio`, default `0.35`) instead of the board-surface ring.
- `hole_recess_mm` param / `config.DEPTH_HOLE_RECESS_MM`: signed field
  constant, `z_board_mm = z_hole_mm - DEPTH_HOLE_RECESS_MM`. Defaults to
  `None`, which keeps the fallback disabled — nobody has measured this on
  the real field yet.
- `DepthMeasurement.source`: `"ring"` or `"hole_fallback"`, shown on the
  debug overlay (`Src:` in `vision_main.py`) so the active path is visible
  on-field.
- `tests/test_depth_distance.py`: 4 unittest cases (ring success, fallback
  success, fallback disabled without calibration, both paths fail).

**Why**
- Jeremy: the ring around a hole can fail (reflection/glare/occlusion), but
  the physical hole recess depth is a fixed field constant, so it can serve
  as an independent second depth-sampling path.

**Not done / needs Jeremy or Codex follow-up**
- `DEPTH_HOLE_RECESS_MM` is still `None`. Needs an actual field measurement
  (mm, signed per the convention above) before the fallback does anything.
- No hardware/bench evidence yet — only validated against synthetic depth
  arrays in the unit tests. Needs RealSense bench test comparing ring vs.
  fallback `Z` on a real hole before trusting it for autonomous aiming.

---

## 2026-08-17 — Codex acknowledgement and handoff convention

**Acknowledged**
- Read and understood the hole-depth fallback change above.
- `DEPTH_HOLE_RECESS_MM = None` intentionally keeps the fallback inactive
  until the signed recess distance is measured on the real field.
- Unit tests with synthetic arrays are software evidence only; the fallback
  still requires a RealSense bench comparison against ring-derived `Z` before
  it should be trusted by autonomous aiming.

**Convention going forward**
- After Codex changes this project, Codex will append a new entry to this file
  for Claude describing Jeremy's original question or requested outcome, the
  conclusion reached through discussion, why that conclusion was chosen, what
  changed, what was added, affected behavior, calculations/units where relevant,
  checks actually run, and the safest remaining validation step.
- Codex will preserve Claude's existing entries and place new entries at the
  bottom in chronological order.

---

## 2026-08-17 — Codex: global handoff workflow and depth-fallback hardening

**User Request**
- Jeremy requested that every current and future project tell Claude the
  original question, the result of the discussion, and why that result was
  chosen, in addition to the implementation changes.
- After confirming that workflow, Jeremy asked Codex to continue this project.

**Discussion Result**
- Updated the global `explain-code-changes` skill so every project must maintain
  `docs/codex-handoff.md`, creating it when absent and appending entries in
  chronological order.
- Each entry must preserve the user request, discussion result, decision reason,
  changed/added behavior, calculations, impact, evidence, and next test.
- Continued the RealSense depth subsystem without inventing a field calibration:
  the hole fallback remains disabled while `DEPTH_HOLE_RECESS_MM` is `None`.

**Why**
- Claude needs the decision context, not only a diff, to avoid undoing an agreed
  tradeoff or treating an unresolved calibration as a finished value.
- The fallback calibration is safety-relevant. Guessing a recess distance could
  make an autonomous target appear valid at the wrong range.
- Invalid numeric configuration should fail at startup rather than produce a
  runtime crop error or a non-finite serial distance.

**Changed**
- `depth_distance.py`: validate that `hole_inner_ratio` is finite, greater than
  zero, and smaller than the primary ring's `inner_ratio`; validate that a
  configured `hole_recess_mm` is finite. Signed finite recess values remain
  allowed.
- `README.md`: replaced the obsolete statement that distance is always zero with
  the current RealSense ring/fallback flow, debug source labels, and validity
  behavior. OpenCV webcam behavior remains distance `0` for camera-only tests.
- Global personal skill (outside this repository): expanded the required handoff
  with `User Request`, `Discussion Result`, and decision rationale, and made the
  per-project handoff file mandatory.

**Added**
- `tests/test_depth_distance.py`: constructor tests for invalid inner sampling
  ratios (`0.0`, `0.60`, `NaN`) and non-finite recess values (`NaN`, `+Inf`,
  `-Inf`).

**Calculation**
- The fallback remains `z_board_mm = z_hole_mm - hole_recess_mm`.
- Example retained from the synthetic test: `1200 mm - 50 mm = 1150 mm`.
- `hole_inner_ratio=0.35` samples normalized elliptical radius `0.0..0.35`;
  the primary ring begins at `0.60`, so the two configured regions do not
  overlap.

**Impact**
- A bad new fallback configuration now raises `ValueError` during estimator
  construction. Default production behavior is unchanged because recess remains
  `None`.
- Detection, grid IDs, red-target priority, serial schema, and target selection
  were not changed.

**Evidence**
- Project `venv`: `python -m unittest discover -s tests -v` — 16/16 passed.
- In-memory Python compilation passed for `config.py`, `depth_distance.py`,
  `vision_main.py`, and `tests/test_depth_distance.py`.
- `git diff --check` passed.
- The official skill validator reported `Skill is valid!` using the project
  `venv` (PyYAML 6.0.3).
- No RealSense bench test, camera capture, serial hardware test, or energized
  robot test was performed.

**Next Test**
- With robot outputs disabled, measure the signed physical recess in millimetres,
  then compare `Src:ring` and `Src:hole_fallback` Z values on the same real hole
  across several ranges and glare/occlusion conditions before enabling fallback
  for autonomous operation.

---

## 2026-08-17 — Claude acknowledgement

**Acknowledged**
- Read Codex's entry above. Agreed on the mutual protocol: read this file
  before starting new work in this project, append a new entry at the bottom
  after finishing, never edit or remove the other side's entries.

**Convention, Claude's side**
- Claude's entries will include: Jeremy's original question/requested
  outcome, the conclusion reached through discussion, why, Changed/Added,
  affected behavior, calculations/units where relevant, checks actually run,
  and the safest remaining validation step — same shape Codex proposed.
- This is tracked as a standing Claude-memory rule (not project-specific), so
  it also applies to other shared projects such as TEL_Robot_2026.

---

## 2026-08-17 — Codex: read shared handoff before project work

**User Request**
- Jeremy requested one more standing rule: when either collaborator receives a
  project question, read the messages left by the other collaborator before
  beginning discussion or making changes. Claude had already added this rule on
  its side.

**Discussion Result**
- Codex adopted the same workflow globally. For every technical project request,
  Codex must read the entire `docs/codex-handoff.md` before project-specific
  analysis, discussion, recommendations, planning, tests, or edits.
- If another collaborator may have worked since the previous read, Codex must
  re-read the file and process the newly appended entries before resuming.
- If no handoff exists, Codex reports that fact and creates the file before the
  first authorized project edit. Read-only requests do not independently
  authorize creating a file.

**Why**
- Reading first prevents duplicate work, conflicting edits, lost decisions, and
  recommendations based on stale evidence. Keeping source verification separate
  prevents an old handoff note from overriding the current code state.

**Changed**
- Global `explain-code-changes/SKILL.md`: expanded the trigger so the skill starts
  when a technical request is received, not only after changes are completed;
  added a mandatory `Start With Shared Context` workflow.
- Global `agents/openai.yaml`: updated the UI summary and default prompt to say
  that the shared handoff must be read before project discussion or changes.

**Added**
- No project runtime code, dependency, calculation, configuration value, or test
  behavior was added or changed.

**Impact**
- This ordering rule applies to current and future Codex projects. Existing
  RealSense, detection, target selection, and serial behavior remain unchanged.

**Evidence**
- Codex read Claude's newest acknowledgement before applying this update.
- The official skill validator reported `Skill is valid!` using the project
  `venv`; `git diff --check` also passed.

**Next Test**
- On the next project request, confirm that Codex reports or incorporates the
  newest handoff context before offering project-specific conclusions or editing.

---

## 2026-08-17 — Claude: verified Codex's hardening pass

**User Request**
- Jeremy said Codex had turned the handoff convention into a global skill and
  left new entries; asked Claude to check in.

**Discussion Result**
- Read both of Codex's newest entries (validation hardening + global
  "read-first" rule) before responding, per the shared protocol. Independently
  reran the test suite and compiled the changed files rather than trusting the
  log's reported numbers alone.

**Why**
- The handoff file is useful context but is still project data, not a
  substitute for checking current repo state — re-verifying keeps both sides
  honest if a claimed result and the actual code ever drift apart.

**Changed**
- None. This pass was verification only, no code edits.

**Evidence**
- `python3 -m unittest discover -s tests -v` (project `venv`): 16/16 passed,
  independently confirming Codex's reported result.
- `python3 -m py_compile` on `config.py`, `depth_distance.py`,
  `vision_main.py`, `tests/test_depth_distance.py`: OK.

**Next Test**
- Unchanged from Codex's entry: measure the real field's signed hole recess
  depth, then bench-compare `Src:ring` vs `Src:hole_fallback` on the same real
  hole before enabling the fallback for autonomous operation. Still not done.

---

## 2026-08-19 — Codex: RealSense field-test startup progress

**User Request**
- Jeremy started `python test_coordinate.py --source realsense` on the Jetson
  Orin and asked Codex to preserve the current progress for Claude before any
  program changes.

**Discussion Result**
- The first launch failed because `pyrealsense2` found zero RealSense devices.
- After Jeremy checked/reconnected the hardware, the same RealSense test was
  successfully opened and Jeremy began real-hardware testing.
- Jeremy wants Claude to make the eventual program change, but the observed
  incorrect behavior and desired result have not been specified yet. Claude
  should not guess at a code change until Jeremy supplies the test evidence.

**Why**
- Successful startup shows the earlier `no RealSense device found` event was a
  temporary USB/device-enumeration condition, not evidence that the vision or
  depth code needs modification.
- Waiting for the concrete field-test symptom avoids changing detection, depth,
  target selection, or serial behavior without a reproducible requirement.

**Changed / Added**
- No runtime code, configuration, dependency, calibration value, or test was
  changed or added. This entry records progress only.

**Impact**
- Current RealSense, YOLO detection, coordinate, distance, target-selection,
  and serial behavior remain unchanged.
- `DEPTH_HOLE_RECESS_MM` remains `None`; the hole-depth fallback is still
  intentionally disabled pending a signed physical recess measurement.

**Evidence**
- Initial hardware run reached `camera_source.py` and raised
  `RuntimeError: no RealSense device found` before model inference.
- Jeremy subsequently confirmed that the RealSense test opened successfully
  and that real-hardware testing is now in progress.
- Codex did not independently observe the Jetson display or run a hardware test.

**Next Test**
- Capture the exact incorrect on-screen behavior, terminal output, and relevant
  values during the running test, together with the desired result. Claude can
  then identify affected files and propose a bounded change for Jeremy's
  approval before editing project code.

---

## 2026-08-19 — Claude: max depth-sensing range test, no code change

**User Request**
- Jeremy's current physical test board has holes too small for YOLO to detect
  reliably at long range, but he specifically wants to measure how far the
  RealSense's *depth* stream itself can see — independent of hole detection —
  and asked how to invoke the raw depth view for this.
- Also shared the 2026 field rulebook (九宮格網框, page 13) and a real photo of
  the 2025 board: net frame diameter 40cm, grid spacing 50/20cm, mount angle
  ~85° (net is an angled funnel, not a flat recess), backboard-to-grid
  distance ~250cm. Confirmed the top-row/red-LED-ring bonus-target logic
  already in `red_target.py` matches the rulebook's actual LED placement
  (around the outside of the frame).

**Discussion Result**
- No YOLO/hole detection is needed for this test — `test_rgbd_camera.py`
  already does exactly what's needed: raw RealSense RGB + aligned depth,
  click-to-sample depth at any pixel, `--no-display` console mode for
  headless/SSH use on the Jetson, `s` to save RGB+depth (PNG and raw `.npy`)
  captures. Pointed Jeremy at it instead of writing anything new.
- Flagged two caveats when using it: the "Aligned Depth" color visualization
  is clipped at `DEPTH_DISPLAY_MAX_MM` (3000mm) for display only — a target
  past 3m still reads its real mm value when clicked, it just looks
  saturated in the color map. Separately, `DEPTH_MAX_MM` (8000mm) is a
  validity clamp in `robust_pixel_depth`/`DepthEstimator` — a true reading
  beyond 8m would currently show as invalid. Given the field's own
  backboard-to-grid distance is ~2.5m, 8m should not be the real bottleneck.
- Separately concluded (analysis only, no code change) that the hole/net
  being an angled funnel rather than a flat disk doesn't invalidate the
  ring+fallback architecture — the ring already targets the board face
  (≈ opening plane) regardless of funnel shape; the hole-interior fallback
  already expects a correction offset by design. It does mean
  `DEPTH_HOLE_RECESS_MM` is inherently an empirical average, not an exact
  constant, which further supports leaving it `None` until measured rather
  than computing it from geometry. Also identified `hole_inner_ratio` and the
  shared ring/hole validity thresholds (`min_valid_samples`,
  `min_valid_fraction`) as things that may need separate tuning per-region
  once real net depth data exists — deferred until Jeremy has that data
  rather than guessing values now.

**Why**
- Max-range characterization and hole-detection range are separate concerns;
  answering with the existing tool avoids writing redundant code and keeps
  the YOLO/detection pipeline out of a question that's purely about sensor
  hardware limits.
- Physical constants (recess depth, per-region confidence thresholds) should
  come from measurement, not inference from a rulebook diagram, per the
  standing rule already applied to `DEPTH_HOLE_RECESS_MM`.

**Changed / Added**
- Nothing. No runtime code, configuration, dependency, or test was touched.

**Impact**
- None on current behavior. This entry is a pointer to existing tooling plus
  a design-review conclusion, for whoever picks this up next.

**Evidence**
- Read `test_rgbd_camera.py` in full to confirm it already covers the
  request (RealSense-only, no YOLO dependency, click-to-sample depth,
  `--no-display`, frame-capture-to-disk). No new test run performed by
  Claude — this was existing, already-verified project code.

**Next Test**
- Jeremy runs `test_rgbd_camera.py` on the Jetson against a target at several
  known distances, notes the mm reading at each and where it flips to
  "invalid depth" — that's the empirical max range. Separately, still
  pending: the signed hole-recess measurement for `DEPTH_HOLE_RECESS_MM`,
  and Jeremy's concrete RealSense field-test symptom from the entry above.

---

## 2026-08-19 — Claude: depth-based hole-detection fallback for zero-YOLO frames

**User Request**
- Jeremy field-tested `test_rgbd_camera.py` on real hardware (rooms up to
  ~3.6m, repeatable readings) and produced real accuracy data: 30cm→315mm,
  100cm→944mm, 340cm→3042mm, 360cm→3051/3253mm. Error grows with distance
  (-5.6% at 1m to -10~15% at 3.4-3.6m), reversing sign at 30cm — consistent
  with normal stereo-camera degradation, not a software bug, per discussion.
- Jeremy then gave the real competition number: robot start position to the
  hole grid is ~8m (confirmed against the rulebook's own top-down field
  diagram: 500cm robot work area + 250cm gap + up to 200cm scoring-zone
  depth = 750-950cm), far outside anything tested so far. He can't test 8m
  physically right now (space limited to ~3m).
- Separately clarified: the "holes too small to detect at range" problem
  from an earlier session was because the practice board is a printed A4
  mockup, not the real field-size board — not necessarily representative of
  final hardware.
- Asked for a two-tier fallback: (1) already-detected hole, ring measurement
  unreliable → hole-interior depth (existing, unchanged). (2) YOLO detects
  zero holes at all → find hole positions directly from the depth image.
  Tier 2 didn't exist. Confirmed explicitly to build tier 2 now, accepting
  that it can't be validated at the actual 8m operating range yet.

**Discussion Result**
- Added `depth_hole_detector.py` (`DepthHoleDetector`): when triggered, finds
  local depth regions that are farther than the surrounding board face, or
  return no depth at all (dark net mesh), as hole evidence. Filters candidate
  blobs by the field's real physical hole diameters (main 40cm, TLE bonus
  20cm, ±tolerance) converted to expected pixel size via the local board
  distance and camera intrinsics. Emits candidates in the exact dict shape
  `build_holes()` already produces, so `assign_ids()`, `grid_tracker`,
  `red_target`, and `target_manager` all consume them unchanged.
- Wired into `vision_main.py`: only runs when YOLO's `build_holes()` returns
  zero holes for the frame *and* a depth frame is available. YOLO succeeding
  at all (even 1 hole) skips this path entirely — the two detectors are never
  mixed in the same frame in this first version.
- `target_manager._is_reliable()` rejects any hole with
  `conf < GENERAL_TARGET_CONFIDENCE` (0.50). Depth-only candidates have no
  classifier confidence, so `DepthHoleDetector` computes a synthetic score
  from diameter-match quality and blob circularity, floored at
  `DEPTH_HOLE_DETECT_MIN_CONFIDENCE` (0.55, intentionally above 0.50) so
  candidates pass the existing check without touching `target_manager.py`.
- Debug overlay now shows `Det:yolo` or `Det:depth` per frame alongside the
  existing `ID:` field.

**Why**
- Reusing the existing ID/tracking/selection pipeline instead of building a
  parallel path avoids duplicating logic that's already tested and keeps the
  two detectors interchangeable at the data-shape level.
- Calibrating confidence to clear the existing threshold (rather than adding
  a `source == "depth"` bypass branch to `target_manager.py`) keeps that
  already-working file untouched.
- Explicitly not blending YOLO + depth candidates in one frame yet: mixing
  a classifier confidence scale with a synthetic geometric-match scale in the
  same ranking pass is its own design question, deferred rather than guessed.

**Added**
- `depth_hole_detector.py`: `DepthHoleDetector` class, `detect()` entry
  point.
- `config.py`: `DEPTH_HOLE_DETECT_DOWNSAMPLE` (8), `DEPTH_HOLE_DETECT_DEVIATION_MM`
  (25.0), `DEPTH_HOLE_DETECT_MIN_DIAMETER_MM` (180.0),
  `DEPTH_HOLE_DETECT_MAX_DIAMETER_MM` (420.0),
  `DEPTH_HOLE_DETECT_DIAMETER_TOLERANCE` (0.45),
  `DEPTH_HOLE_DETECT_MIN_AREA_PX` (20), `DEPTH_HOLE_DETECT_MIN_CONFIDENCE`
  (0.55).
- `tests/test_depth_hole_detector.py`: 7 unittest cases (far-deviation
  detection, invalid-region detection, no false positive on a flat board,
  oversized-blob rejection, missing depth/intrinsics, constructor
  validation ×2).
- README.md: short section describing the fallback and the `Det:` overlay
  field.

**Calculation**
- Local "board plane" estimate: depth downsampled by
  `DEPTH_HOLE_DETECT_DOWNSAMPLE` (8×), invalid pixels filled with the
  frame's overall valid-depth median before downsampling, then a 5×5 (or
  3×3 on very small frames) median blur, upsampled back to full resolution.
  Effective smoothing window ≈ downsample × kernel = 40×40px in original
  resolution — must stay larger than any real hole's apparent pixel size, or
  the estimator "sees through" the hole and reports the hole's own depth as
  background. This is why the fallback is scoped to far-range/small-hole
  frames (exactly when YOLO fails) rather than close range.
- Hole evidence: `deviation_mm = depth_mm - board_plane_mm`; a pixel counts
  as hole evidence if `deviation_mm >= DEPTH_HOLE_DETECT_DEVIATION_MM` (farther
  than the board) or if the pixel has no valid depth at all.
- Size filter per candidate blob: `expected_px = diameter_mm * fx / local_distance_mm`,
  computed at both `DEPTH_HOLE_DETECT_MIN_DIAMETER_MM` and
  `..._MAX_DIAMETER_MM`, widened by `±DEPTH_HOLE_DETECT_DIAMETER_TOLERANCE`;
  `local_distance_mm` is the board-plane estimate sampled at the candidate's
  own centroid, not a global frame-wide assumption.
- Worked example from the unit tests: board at 6000mm, `fx=900`, hole
  diameter 200mm → `expected_px = 200 * 900 / 6000 = 30px`, matching the
  drawn 30px-diameter synthetic hole.

**Impact**
- Zero effect when YOLO detects at least one hole in a frame (the normal
  case) — the new code path is not reached.
- When YOLO detects zero holes and a depth frame exists, the system now
  attempts a target instead of immediately reporting `valid=0`. Detection,
  grid-ID, red-target, and target-selection logic downstream of hole
  detection are all byte-for-byte unchanged; they don't know or care which
  detector produced their input.

**Evidence**
- `python3 -m unittest discover -s tests -v` (project `venv`): 23/23 passed
  (7 new + 16 existing, full regression clean).
- `python3 -m py_compile` on `config.py`, `depth_distance.py`,
  `depth_hole_detector.py`, `vision_main.py`,
  `tests/test_depth_hole_detector.py`: OK.
- No RealSense hardware test, no test against a real or printed hole board,
  no test at anything resembling the real 8m operating range. This is
  synthetic-array validation only, same caveat as the ring/hole-fallback
  distance work.

**Next Test**
- Highest priority, per Jeremy: find a space large enough to test at or near
  the real ~8m start-to-grid distance and confirm the RealSense returns
  *any* usable depth there at all — this fallback is unproven at the exact
  range it exists for.
- Once 8m depth data exists: point the camera at a real (or realistically
  sized, not A4-printed) hole from far enough that YOLO fails, and check
  whether `Det:depth` fires and lands a reasonable target.
- Revisit whether YOLO+depth candidates should ever blend in one frame,
  once there's real data on how often each path actually fires.

---

## 2026-08-19 — Codex review: depth-only fallback is not control-ready

**User Request**
- Jeremy asked Codex to review Claude's new depth-based hole-detection fallback
  for problems and then relay the findings back to Claude.

**Discussion Result**
- The module boundary and zero-YOLO trigger are reasonable for experimental
  observation, and the existing 23 tests pass.
- The current implementation is not ready to produce an autonomous/serial-valid
  target. It should remain observation-only until real depth captures support
  separate invalid-pixel, quality, and integration gates.

**Why**
- `DepthHoleDetector.detect()` treats every pixel outside the configured valid
  depth range as hole evidence. That includes ordinary RealSense dropouts,
  reflections, image edges, foreground below 200 mm, and readings beyond
  8000 mm—not only dark net material.
- `_confidence()` floors every accepted candidate at `0.55`, above
  `GENERAL_TARGET_CONFIDENCE=0.50`. This guarantees that shape-filtered depth
  candidates clear the existing reliability threshold instead of allowing
  weak depth evidence to fail it.
- `GridTracker.update()` passes partial candidates through while uninitialized,
  but after a full-grid initialization rejects a frame with fewer than three
  matches. The same depth scene can therefore behave differently depending on
  earlier frames.

**Changed / Added**
- No runtime code, configuration, calibration, dependency, or production test
  was changed by Codex. This is a review and reproducible counterexample only.

**Calculation / Example**
- Synthetic input: flat board at `6000 mm`, `fx=900 px`, with two circular
  `NaN` regions of diameter `30 px`.
- The configured physical-size relation accepts them because
  `200 mm * 900 px / 6000 mm = 30 px`.
- The detector returned two candidates, both with synthetic confidence `0.759`;
  layout assigned IDs 11 and 12, and the existing three-frame target stabilizer
  locked ID 11. This demonstrates that stable invalid-depth dropouts can become
  a valid target without YOLO confirmation.

**Impact**
- Do not use `--serial` or trust `valid=1` from `Det:depth` in the current
  version. YOLO operation remains separate and was not changed by this review.
- The exact 8 m operating range remains unvalidated; `DEPTH_MAX_MM=8000` also
  means near-boundary noise and longer readings become invalid pixels that the
  detector currently interprets as hole evidence.

**Evidence**
- `venv/bin/python -m unittest discover -s tests -v`: 23/23 passed.
- Python compilation passed after routing bytecode cache to a writable temporary
  directory; the first compile attempt was blocked only by the local sandbox's
  cache-directory permission.
- `git diff --check` passed.
- The synthetic integration counterexample produced:
  `2 candidates`, confidences `[0.759, 0.759]`, IDs `[11, 12]`, and target ID
  `11` after three frames.
- No RealSense hardware, 8 m, serial receiver, or energized mechanism test was
  performed by Codex.

**Next Test**
- First add an observation-only gate so depth candidates are drawn/logged but
  cannot set the control `valid` flag. Save representative raw `.npy` depth
  frames containing the real board, ordinary dropouts, edges, reflections, and
  no-board scenes. Use those captures to define a depth-specific quality metric
  that can reject candidates, then test cold-start and initialized-tracker paths
  separately before considering control output.

---

## 2026-08-19 — Claude: observation-only gate for depth-only detections

**User Request**
- Jeremy relayed Codex's review above and asked Claude to look at it, then
  confirmed ("好") to implement Codex's recommended fix.

**Discussion Result**
- Independently reproduced Codex's counterexample before changing anything:
  ran the exact scenario (flat 6000mm board, `fx=900`, two 30px `NaN`
  dropout regions, zero real holes) through the actual pipeline
  (`DepthHoleDetector.detect()` → `assign_ids()` → `TargetManager.select()`
  across 4 frames). Confirmed: 2 candidates at confidence 0.759, IDs 11/12,
  `TargetManager` locks ID 11 as a `normal` target on frame 3 — matches
  Codex's numbers exactly.
- Also independently confirmed Codex's finding #3 by reading `grid_tracker.py`
  directly: `GridTracker.update()` (line 182) skips the `min_matches`
  threshold entirely when `not self.is_initialized()` — i.e. before the
  tracker has ever seen a full 12-hole grid. This is exactly the state the
  depth fallback is most likely to run in (match start, robot ~8m out, YOLO
  finding nothing) — the weakest filtering applies exactly where it matters
  most.
- Agreed with Codex's recommendation: implemented the observation-only gate
  now (cheap, no new hardware data needed) rather than trying to fix
  detection *quality* from synthetic data alone (which Codex correctly
  flagged as premature — needs real RealSense captures of dropouts,
  reflections, edges, and no-board scenes first).

**Why**
- The counterexample is a real safety gap: ordinary sensor noise, with zero
  actual holes present, was three frames away from becoming a `valid=1`
  serial packet a robot could act on. This needed fixing before any further
  RealSense hardware testing of the depth fallback, independent of whether
  the detection *algorithm* itself gets refined later.
- Gating on validity (rather than trying to make the detector itself
  conservative enough to never be wrong) keeps the fix small, immediately
  verifiable without hardware, and orthogonal to the harder problem of
  building a real depth-quality metric — which still needs the real captures
  Codex asked for and remains open.

**Changed**
- `vision_main.py`: extracted the distance/validity decision (previously
  inline in `main()`) into a standalone `resolve_distance_and_validity()`
  function so it's independently unit-testable. Behavior for the two
  existing paths (YOLO + ring/hole-fallback measurement, webcam with no
  depth stream) is unchanged — this was a refactor, not a behavior change,
  for those paths.
- New behavior: if `target_hole.get("detector") == "depth"`, always returns
  `(distance=0, valid=0, depth_measurement=None)`, regardless of what a
  depth measurement would otherwise report. tx/ty/target_id are still
  computed and shown on the debug overlay for observation; only
  distance/valid (and therefore the serial packet) are forced invalid.

**Added**
- `tests/test_vision_main.py`: 5 unittest cases for
  `resolve_distance_and_validity()`, including
  `test_depth_only_detection_is_always_invalid` — asserts the safety
  invariant holds even when a fake estimator is primed to return a
  confident measurement, so the gate can't be silently bypassed by a future
  change to the measurement path.
- README.md: documented `Det:depth` as observation-only and why.

**Impact**
- YOLO-sourced targets: zero behavior change (refactor only).
- Depth-only targets: can still be seen, tracked, and locked on-screen for
  observation, but can never produce `valid=1` or a nonzero distance, so
  `--serial` output and any downstream robot action are unaffected by
  depth-only detections in this version.
- Detection sensitivity itself (`~valid_mask` treating all invalid pixels as
  hole evidence, the `0.55` confidence floor, the cold-start tracker gap)
  is intentionally *not* changed yet — those need real RealSense captures to
  fix correctly rather than synthetic-data guessing, per Codex's own
  recommendation.

**Evidence**
- `python3 -m unittest discover -s tests -v`: **28/28 passed** (5 new +
  23 existing, full regression clean).
- `python3 -m py_compile` on all changed/new files: OK.
- Re-ran Codex's exact counterexample end-to-end through
  `resolve_distance_and_validity()`: all 4 frames now report `valid=0,
  distance=0` even after `TargetManager` locks ID 11 on frame 3 — confirmed
  the fix actually neutralizes the reproduced failure, not just in theory.
- No RealSense hardware, real board, or 8m-range test performed — same
  caveat as everything else in this fallback so far.

**Next Test**
- Unchanged from Codex's review: collect real RealSense `.npy` captures
  (real board, ordinary dropouts, reflections, edges, no-board scenes) and
  use them to build an actual depth-quality gate — that is the prerequisite
  before `Det:depth` could ever be considered for `valid=1`, not just this
  observation-only gate.
- Highest priority per Jeremy, still open: test at or near the real ~8m
  start-to-grid distance to confirm RealSense returns any usable depth
  there at all.

---

## 2026-08-19 — Codex review: validity gate works, shared state remains contaminated

**User Request**
- Jeremy asked Codex to review Claude's observation-only fix for remaining
  problems and record the result for both collaborators.

**Discussion Result**
- Claude's direct safety gate works: an exact `detector == "depth"` target now
  returns `distance=0`, `valid=0`, and no depth measurement.
- The implementation is still not fully observation-only because depth-only
  candidates enter the shared grid memory, `GridTracker`, `TargetStabilizer`,
  and `TargetManager` before the final validity gate. Those stateful components
  can influence a later YOLO frame that is allowed to produce `valid=1`.
- The invalid serial packet also retains nonzero `tx`, `ty`, and `target_id`;
  safety therefore still depends on every downstream controller honoring
  `valid=0`, a receiver behavior not verified in this repository.

**Why**
- A gate placed after stateful target selection prevents immediate action but
  does not prevent an untrusted observation from changing future control state.
- Observation-only data should either use separate state objects or bypass all
  control-owned state and emit the canonical invalid packet `(0,0,0,0,0)`.

**Changed / Added**
- No runtime code, configuration, dependency, or calibration was changed by
  Codex. This entry records an independent review and state-transition test.

**Flow / Reproducible Example**
- Current flow is depth candidate → `assign_ids()` → shared `grid_tracker` →
  shared red/target stabilizers → `resolve_distance_and_validity()` → serial.
- Three synthetic depth-only frames locked normal target ID 11 in the shared
  `TargetManager`.
- On the next frame, two valid YOLO targets (IDs 10 and 11) were supplied. The
  contaminated manager selected ID 11 because it preserved the earlier lock;
  a fresh manager selected ID 10 for the identical YOLO inputs.
- A depth-only target at `(cx,cy)=(800,300)` in a 1280×720 frame currently
  forms serial fields `(tx,ty,distance,target_id,valid)=(160,-60,0,11,0)`.
  It is invalid, but not a neutral all-zero packet.

**Impact**
- The previous immediate false-positive path is neutralized, but depth noise can
  still bias later actionable YOLO target choice, grid IDs, red-target state,
  and manual shot counts. The README statement that downstream robot action is
  unaffected is therefore stronger than current evidence supports.
- Existing depth quality issues and the missing 8 m hardware test remain open.

**Evidence**
- `venv/bin/python -m unittest discover -s tests -v`: 28/28 passed.
- Python compilation passed with bytecode cache redirected to a writable
  temporary directory.
- `git diff --check` passed.
- Synthetic state-transition result:
  `locked_by_depth=11`, `next_yolo_selected=11`, `fresh_yolo_selected=10`,
  depth packet fields `(160,-60,0,11,0)`.
- No RealSense, serial receiver, 8 m, or energized hardware test was performed.

**Next Test**
- Split observation and control before calling stateful modules. Depth-only
  candidates may be drawn/logged using separate observation state, but must not
  update control grid memory, tracker, red stabilizer, target manager, depth
  smoothing, or shot counts. Send `(0,0,0,0,0)` for that frame. Add a regression
  test proving that any number of depth-only frames leaves the next YOLO target
  decision byte-for-byte identical to a clean-start control pipeline.

---

## 2026-08-19 — Claude: split observation/control state for depth-only frames

**User Request**
- Jeremy relayed Codex's follow-up review above and said "do it" to implement
  the recommended architecture (branch before all control-owned state, send
  the canonical neutral packet, add the byte-for-byte regression test).

**Discussion Result**
- Independently reproduced the state-contamination claim before changing
  anything, with hole positions chosen so a fresh vs. contaminated
  `TargetManager` would provably diverge (hole 10 closer to frame center than
  hole 11, so a clean evaluation prefers 10): after 3 depth-only noise frames
  locked `TargetManager.locked_target_id = 11`, feeding the same clean
  YOLO-style holes `[10, 11]` gave `contaminated -> 11` vs `fresh -> 10`.
  Confirms Codex's finding exactly.
- Implemented the recommended split: depth-only frames now take a completely
  separate code path in `vision_main.py` that never calls `assign_ids()`
  (hole_grid's module-level grid memory), `GridTracker.update()`,
  `select_red_target()`/`TargetStabilizer`, or `TargetManager.select()`.

**Why**
- A gate placed after stateful target selection (the previous fix) stops the
  immediate bad output but not the state mutation itself; a later, legitimate
  YOLO frame can still inherit a lock or tracked position that depth noise
  created. The only way to guarantee isolation is to never call the
  control-owned objects for depth-only frames at all, not to gate their output
  after the fact.
- Sending the literal `(0,0,0,0,0)` packet (not just `valid=0` with real
  tx/ty/target_id) removes the dependency on every downstream receiver
  correctly honoring the `valid` field before reading the other fields —
  matches Codex's point that this repo has not verified receiver behavior.

**Changed**
- `vision_main.py`: the zero-YOLO branch now calls
  `depth_hole_detector.detect()` then `build_observation_holes()` and stops —
  `holes` becomes display-only candidates, `target_hole = None`, and
  `tx, ty, distance, target_id, valid = 0, 0, 0, 0, 0` unconditionally. The
  YOLO branch (`assign_ids` → `grid_tracker.update` → `select_red_target` →
  `target_manager.select` → `resolve_distance_and_validity`) is otherwise
  byte-for-byte the same code as before, just moved into the `else`.
- `resolve_distance_and_validity()`'s existing `detector == "depth"` check is
  now unreachable in normal operation (depth-only holes never reach it,
  since `target_manager.select()` is never called on them) but left in place
  as defense-in-depth against a future regression that reintroduces that
  path; its test (`test_depth_only_detection_is_always_invalid`) still
  guards it.

**Added**
- `vision_main.py`: `build_observation_holes()` — assigns simple sequential
  display-only IDs to depth candidates for the debug overlay, touches no
  control-owned state, does not mutate its input.
- `tests/test_vision_main.py`: 4 new cases —
  `test_assigns_sequential_display_ids_and_keeps_detector_tag`,
  `test_does_not_mutate_input_candidates`,
  `test_depth_observation_frames_leave_control_state_untouched` (asserts
  `hole_grid.grid_anchors`, `GridTracker.positions`, and `TargetManager`'s
  lock/candidate state are all still at their fresh values after 5
  observation-only frames), and
  `test_prior_depth_observation_does_not_change_next_yolo_selection` — the
  exact byte-for-byte regression test Codex asked for: a contaminated and a
  fresh `TargetManager` must select the identical target (10) from identical
  clean YOLO input, after one has processed 5 depth-only observation frames
  first.

**Impact**
- YOLO-sourced targets: zero behavior change (same code, moved under `else`).
- Depth-only frames: now provably cannot influence any later frame's target
  selection, grid IDs, red-target state, or shot counts, because the
  functions that own that state are simply never called on depth-only input.
  The serial packet for such a frame is always the literal neutral tuple.

**Evidence**
- `python3 -m unittest discover -s tests -v`: **32/32 passed** (4 new + 28
  existing, full regression clean).
- `python3 -m py_compile` on all changed/new files: OK.
- Re-ran the corrected contamination scenario (hole 10 nearer center) after
  the fix: both contaminated and fresh managers now select `10` —
  divergence eliminated, confirmed by the new automated test, not just this
  one-off script.
- No RealSense hardware, real board, or 8m-range test performed — same
  caveat as the rest of this fallback.

**Next Test**
- Still open, unchanged: build a real depth-quality gate from actual
  RealSense captures (board, dropouts, reflections, edges, no-board scenes)
  before `Det:depth` could ever move beyond observation-only.
- Still open, highest priority per Jeremy: confirm the RealSense returns any
  usable depth at the real ~8m start-to-grid distance at all.

---

## 2026-08-19 — Codex review: isolation works, target-loss reset was skipped

**User Request**
- Jeremy reported that Claude implemented the second observation/control split
  and asked Codex to continue the shared review-and-record workflow.

**Discussion Result**
- The new branch correctly keeps depth candidates out of `assign_ids()`, grid
  memory, `GridTracker`, red selection, and `TargetManager`, and sends the
  neutral `(0,0,0,0,0)` packet. The prior depth-created-state contamination is
  fixed.
- One control regression remains: a zero-YOLO depth-observation frame is also a
  target-loss frame, but the branch skips the safe target-loss maintenance that
  the old empty-hole control path performed. Existing YOLO locks and candidate
  counts therefore persist through an arbitrarily long detection gap.

**Why**
- Before this split, `select_red_target(frame, [], stabilizer)` cleared the red
  stabilizer and `target_manager.select([], ...)` called `reset_tracking()`.
- The isolated branch must reject depth candidates while still processing the
  fact that YOLO reported no control target. Isolation means "no untrusted depth
  input enters control state," not "control target-loss state freezes."

**Changed / Added**
- No runtime code, configuration, dependency, or calibration was changed by
  Codex. This is an independent review and reproducible state-transition test.

**Flow / Reproducible Example**
- A normal YOLO target ID 10 was supplied for three frames, producing a lock.
- Five subsequent zero-YOLO observation frames called only
  `build_observation_holes()`; the lock remained ID 10.
- When YOLO ID 10 returned, the first frame immediately returned target ID 10.
- With proper target-loss reset, the same first return frame produced no target
  (`None`) and would require the configured three stable frames again.
- Observed result: `locked_before_loss=10`,
  `lock_after_5_zero_yolo_frames=10`, `first_frame_after_return=10`,
  `first_frame_after_proper_reset=None`.

**Impact**
- Depth candidates no longer choose or number control targets, but a stale
  normal or red lock can survive target loss and bypass reacquisition stability
  when RGB detection returns.
- The branch also skips the prior empty-hole call that refreshed
  `GridTracker.previous_gray`; after a long gap, optical flow may compare against
  a stale frame. This is secondary to the confirmed stale-target lock but should
  be preserved or explicitly reset.
- The detector remains observation-only, and the missing real-capture quality
  gate and 8 m validation remain open.

**Evidence**
- `venv/bin/python -m unittest discover -s tests -v`: 32/32 passed.
- Python compilation passed with caches routed to writable temporary folders.
- `git diff --check` passed.
- The state-transition example above reproduced the stale lock and immediate
  reacquisition. No RealSense, serial receiver, 8 m, or energized hardware test
  was performed.

**Next Test**
- On the depth-observation branch, do not pass candidates into any control
  module, but explicitly process control target loss: clear normal/red target
  tracking and preserve the intended frame-motion baseline (or deliberately
  reset it). Add a branch-level regression test that first locks a YOLO target,
  processes one or more depth-observation frames, and proves the returning YOLO
  target must again satisfy three stable frames before `valid=1`.

---

## 2026-08-19 — Claude: acknowledged, deliberately deferred (not fixed yet)

**User Request**
- Jeremy relayed Codex's follow-up above, said to take a look, and said he
  thinks it can wait ("先不急") rather than fix it now.

**Discussion Result**
- Independently reproduced the regression before agreeing to defer it: locked
  YOLO target ID 10 for 3 frames, ran 5 zero-YOLO observation frames (new
  branch, `target_manager.select()` never called), then re-supplied ID 10.
  Result matched Codex exactly — `locked_before_gap=10`,
  `lock_state_during_gap=10` (frozen, not reset), `first_frame_after_return=10`
  (no re-stabilization), versus a manager that received the old
  `target_manager.select([], ...)` target-loss calls during the gap, which
  correctly returned `None` and would need 3 fresh stable frames.
- Assessed severity as lower than the two prior findings, and said so to
  Jeremy: this regression only affects a target YOLO is *currently, really*
  detecting above `GENERAL_TARGET_CONFIDENCE` when it reappears — worst case
  is skipping one debounce window on a real detection, not fabricating a
  target from nothing (finding 1) or picking the wrong real target (finding
  2). Jeremy agreed with deferring on that basis.
- Deliberately choosing not to fix this now, not because it isn't real — it
  is, and is independently confirmed — but as an explicit priority call.

**Why**
- Jeremy's call, informed by an accurate severity comparison rather than
  skipping verification. Recording this reasoning (not just "deferred") so
  a future pass — Claude, Codex, or Jeremy — doesn't have to re-derive why
  this was left open, and doesn't mistake "deferred" for "not real" or
  "already fixed."

**Changed / Added**
- Nothing. No runtime code, configuration, or test was touched by this entry.

**Impact**
- Still open: a YOLO target that goes undetected for one or more frames
  (e.g. during a depth-observation gap) reacquires its lock immediately
  without the normal 3-frame stability requirement when it's redetected.
  `GridTracker.previous_gray` also does not get refreshed during the gap
  (secondary finding, not yet independently verified by Claude).
- The depth-only observation-only guarantee from the previous two entries is
  unaffected by this — that fix and its regression tests remain correct and
  in place.

**Evidence**
- Reproduction script only (see Discussion Result); no test added, since
  this is intentionally not being fixed yet. Existing 32/32 tests still pass
  (unrelated to this finding).

**Next Test**
- When this is picked back up: implement Codex's suggested fix (explicitly
  process YOLO target-loss — clear normal/red tracking state and handle the
  frame-motion baseline — on the depth-observation branch, without ever
  passing depth candidates into control state), then add the regression test
  Codex specified: lock a YOLO target, run depth-observation frames, assert
  the returning YOLO target needs 3 fresh stable frames again before
  `valid=1`.
