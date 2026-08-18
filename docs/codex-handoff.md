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
