# Phase 10b: Judge Console Execution Log

## 5-Line Plan
1. **Audit & Authorisation**: Audit all static numbers/schematics in `dashboard/index.html` and `closedloop/report/generate_assets.py`; record human authorisation in `docs/DECISIONS.md`.
2. **Data Builder (`closedloop/report/build_ui_data.py`)**: Extract run manifests, episodes, cell bounds, calibration data, shift data, program sources/diff, and SciPy-verified Clopper-Pearson self-check table into deterministic `dashboard/data.js` and `dashboard/data.json`.
3. **Deterministic Replay Generator (`closedloop/report/render_replays.py`)**: Replay verified episodes in simulation with headless PyBullet camera to produce real PNG frame sequences with metadata and SAM 3.1 overlays under `dashboard/replays/<id>/`.
4. **Interactive Console UI (`dashboard/index.html`)**: Build vanilla HTML/CSS/JS Judge Console featuring Hero Operating-Limit Probe, live Clopper-Pearson controls, Replay Theatre, dynamic Calibration Panel, Shift Scatter View, and Hash-linked ODD Certificate JSON export.
5. **Validation & Gate G3 Preservation**: Verify all Phase 10b unit tests pass (`test_ui_paths`, `test_no_hand_typed_numbers`, `test_data_from_logs`, `test_replays_match_logs`, `test_selfcheck_table`, `test_offline`, `test_size_cap`), confirm `make gate PHASE=10` passes, and verify offline operation in browser.

---

## Step 0: Presentation Audit Table

| Item | Found in Previous Dashboard / Asset Generator | True Value from Logs | Action Taken |
|---|---|---|---|
| **1. Price Plot SVG Curve** | `cam_curve_points = [(100, 0.0), ..., (600, area_cam)]` hardcoded points and static `(50.0%)` labels in `generate_price_plot_svg`. | Dynamic calibration subsampling from `runs/judge-g2-03/episodes.jsonl` (300 successes, 400 failures across 4 buckets). | Replaced with dynamic client-side subsampling in F4 and data-driven SVG generation from real calibration records. |
| **2. Schematic Filmstrip & Rollout** | Fixed vector shapes with hardcoded coordinates, mock centroid `(156, 150)`, and artificial bezier curve `M 150 210 C...` in `generate_rollout_clip_svg`. | Real simulation rollouts and real SAM 3.1 mask coordinates from `runs/judge-g2-03/inspection/inspect_frame_00.json`. | Replaced with real frame sequences captured via deterministic PyBullet replay hook into `dashboard/replays/`. |
| **3. Hand-typed Texts & Quotes** | Fabricated quote attributed to "Muse Spark 1.3 Falsifier Output"; claims of "Gripper Force 80 N -> 120 N (adaptive ramp)" and "trapezoidal acceleration". | Falsifier is Optuna CMA-ES (not Spark). Initial gripper force was 10 N, final gripper force is 100 N (`env.close_gripper(100)`). | Removed all fabricated quotes. Display actual program sources and `difflib` unified diff directly. |
| **4. In-Distribution D Pooled Total** | Stated `68.7% (1,648/2,400)`, which was merely 103/150 scaled up by 16. | `runs/cert-full-01/cert_summary.json` cell totals: 8x150 + 134 + 130 + 127 + 129 + 0 = 1,720 / 2,400 (71.67%). | Display exact pooled pass rate 1,720 / 2,400 (71.67%) computed directly from logs. |
| **5. High-Mass Cell Performance** | Stated `Mass 6.2 to 11.5 kg: 0.0% to 38.0%`. | Cells 08–11 (6.25–8.88 kg) have 127–134 / 150 passes (84.7%–89.3%); cells 12–15 (8.88–11.50 kg) have 0 / 150 passes (0.0%). | Replaced with exact per-cell breakdown from `cert_summary.json`. |
| **6. Repair Arm Comparison & Mint Provenance** | Stated `Arm B3 80% vs B1 55% (Fisher p = 0.046)`. | `runs/h2h3-full-03/repair_results.json`: B1 70.0% (14/20), B2 95.0% (19/20), B3 100.0% (20/20). Minted program `bec73dec45a88431` was produced by Arm B2 in `runs/cert-mint-03` (`configs/mint.yaml`). | Replaced with exact repair metrics from `repair_results.json` and explicit provenance noting Arm B2 origin. |
| **7. Final Program Description vs Source** | Stated `120 N` grasp force (slip threshold 10.19 kg). | `runs/cert-mint-03/program_final.py` commands `env.close_gripper(100)` (slip threshold 8.495 kg, explaining slip failure at > 8.88 kg). | Display exact program source code and physical slip threshold explanation. |
| **8. Relative Asset Paths** | `src="../assets/..."` in `dashboard/index.html` broke when `dashboard/` is the document root. | Assets must resolve relative to `dashboard/`. | Re-routed all UI dependencies to reside inside `dashboard/` with relative paths (`data.js`, `replays/`, local SVGs). |

---

## Step 2: Real Replay Verification & Accounting

- **Replays Planned**: 12 clips
  - `min_ce_initial`: Minimal counterexample on initial program (fail, seed 770006, margin -0.2199)
  - `min_ce_final`: Minimal counterexample on final program (pass, seed 780000, margin +0.0050)
  - `cert_bin0_pass`: Mass bin 0 certified pass (cell_00, seed 2000000, margin +0.0050)
  - `cert_bin1_pass`: Mass bin 1 certified pass (cell_04, seed 2000600, margin +0.0050)
  - `cert_bin2_pass`: Mass bin 2 near-threshold pass (cell_08, seed 2001200, margin +0.0050)
  - `cert_bin2_fail`: Mass bin 2 near-threshold fail (cell_08, seed 2001210, margin -0.2337)
  - `cert_bin3_fail`: Mass bin 3 slip limit fail (cell_12, seed 2001800, margin -0.3453)
  - `shift_d_pass`: Reference distribution D pass (seed 2030001, margin +0.0050)
  - `shift_dp_pass`: Shifted distribution D' pass (seed 2030154, margin +0.0050)
  - `shift_dp_fail`: Shifted distribution D' fail (seed 2030150, margin -0.0579)
  - `sam_inspect_success`: Ground truth SAM 3.1 inspection frame (seed 1000100, on pad)
  - `sam_inspect_failure`: Ground truth SAM 3.1 inspection frame (seed 1000101, off pad)
- **Replays Re-run in Simulation & Verified**: 12 / 12
- **Replays Kept**: 12
- **Replays Dropped**: 0 (100% agreement with logged `truth_success` and `margin`)
- **Total Directory Size**:
  - `dashboard/replays/`: 0.51 MB
  - Total `dashboard/`: 0.85 MB (Strictly below the 15.00 MB size cap)

---

## Gate Verification Output (`make gate PHASE=10`)

```text
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
........................................................................ [ 53%]
..............................................................s          [100%]
134 passed, 1 skipped in 21.12s
.........                                                                [100%]
9 passed in 1.80s
PHASE 10 GATE VERIFIED: G3 FREEZE
Total Verified Precomputed Assets: 7
Source Runs Linked: ['cert-full-01', 'h2h3-full-03', 'judge-g2-03', 'shift-full-01']
PHASE 10: PASS (G3 FREEZE)
```

---

## Human Verification Checklist
1. Open `dashboard/index.html` from `file://` in Chrome / Firefox:
   - Header self-check badge verifies `32/32 Bounds Match Python (SciPy Exact CI)`.
   - Browser console logs 0 errors, 0 failed network requests.
2. Hero Operating-Limit Probe:
   - Dragging Mass and Friction sliders dynamically highlights corresponding cells in the 4x4 heatmap and updates recomputed Clopper-Pearson bounds in real time.
   - Nearest logged episodes list displays relevant scenarios with instant "View Replay" linking.
3. Replay Theatre:
   - Play/pause and frame scrubber advance frames smoothly.
   - Program diff viewer shows `difflib` unified diff between initial and final policies.
4. Camera-Judge Panel:
   - Calibration ledger reflects Gate G2 sample counts.
   - Dynamic calibration curve generates live from client-side subsampling without static coordinates.
5. Distribution Shift:
   - Scatter plot displays all 300 D and D' episodes with empirical boundary line at ~8.5 kg.
   - Certificate refusal badge displays prominently on shifted regime.
6. Certificate Export:
   - "Download ODD Certificate (JSON)" button downloads hash-linked ODD certificate JSON containing program SHA-256, source run links, per-cell bounds, and body SHA-256 hash.

---

## Adversarial Review Summary (Wonder / Opus on Diff)
- **Scope Compliance**: Diff strictly touches `dashboard/`, `closedloop/report/`, `tests/test_dashboard.py`, and `docs/`. Zero edits to `runs/`, `configs/`, `closedloop/certify/`, `closedloop/sim/`, locked files, or `experiments/`.
- **Honesty & Wording (Rule H14)**: Static HTML text contains zero hand-typed metrics or forbidden hype words. Dynamic injection loads numbers strictly from verified run manifests and append-only episode records. "Rendered camera footage" and "certified in simulation under distribution D" are maintained throughout.
- **Offline Self-Sufficiency**: Dashboard requires zero CDNs, web fonts, build tools, or live API connections, running 100% locally from both `file://` and local web servers.
