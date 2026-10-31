# Phase 10 Plan & Execution Log — Dashboard + Precomputed Assets (Gate G3)

## 1. 5-Line Plan
1. Write tests first in `tests/test_dashboard.py` (`test_regeneration_determinism`, `test_asset_provenance`, `test_dashboard_offline`) and verify they fail for the right reasons.
2. Build generator script `closedloop/report/generate_assets.py` (and hook into `make report`) that parses raw logs (`episodes.jsonl`) from P04, P06, P07, P08, P09 and generates byte-identical assets: heatmaps (state/camera), failure filmstrip with SAM annotations, price-of-footage plot, shift test figure, and rollout clips with provenance metadata.
3. Construct `assets/manifest.json` linking every generated asset to its source `run_id`, `git_sha`, `config_hash`, and content `sha256` (Rule H11).
4. Build a sleek, responsive, premium dark-mode offline dashboard in `dashboard/index.html` (with standalone CSS/JS) featuring side-by-side rollout viewer, interactive 4x4 heatmaps, SAM failure filmstrip, live token/cost meters, and provenance inspector with zero external network calls.
5. Declare Gate G3 feature freeze in `docs/DECISIONS.md`, update `Makefile` with Phase 10 gate, run `make gate PHASE=10`, paste output into `docs/phase_logs/PHASE_10.md`, and stop.

## 2. What Changed & Files Added
- `closedloop/report/__init__.py`: Report package initialization.
- `closedloop/report/generate_assets.py`: Deterministic generator script reading strictly from logs to generate SVG/JSON/PNG assets and verifying provenance. Also includes `verify_phase_10_gate()`.
- `assets/`: Precomputed static assets generated directly from raw run logs (`episodes.jsonl`):
  - `heatmap_state.svg` (from `runs/cert-full-01/episodes.jsonl` & `runs/judge-g2-03/episodes.jsonl`)
  - `heatmap_camera.svg` (from `runs/cert-full-01/episodes.jsonl` & `runs/judge-g2-03/episodes.jsonl`)
  - `price_plot.svg` (from `runs/cert-full-01/episodes.jsonl`, `runs/judge-g2-03/episodes.jsonl`, `runs/h2h3-full-03/episodes.jsonl`)
  - `shift_figure.svg` (from `runs/shift-full-01/episodes.jsonl`)
  - `filmstrip_sam.svg` (from `runs/judge-g2-03/episodes.jsonl` SAM failure cases)
  - `rollout_clip.svg` (side-by-side trajectory and contact dynamics)
  - `sam_inspect_frame.png` (standalone binary inspection raster for SAM overlay)
  - `manifest.json` (metadata, run_id, git_sha, config_hash, sha256 for all 7 assets)
- `dashboard/index.html`: Fully self-contained offline interactive dashboard (zero external network dependencies, embedded CSS/JS, dark-mode visual design, Four-Beat story navigation, interactive heatmap cell inspector, failure case visualizer, audit ledger).
- `tests/test_dashboard.py`: Comprehensive test suite verifying asset provenance, byte-for-byte regeneration determinism (Rule V12), and offline safety (0 external URLs).
- `Makefile`: Added `report:` target invoking `closedloop.report.generate_assets` and Phase 10 gate verification under `gate:`.
- `docs/DECISIONS.md`: Recorded entry declaring Gate G3 Feature Freeze (no more code, prompts, arms, tasks, or experiment runs).

## 3. Tests Added
- `tests/test_dashboard.py::test_asset_provenance`: Verifies all required assets exist in `assets/manifest.json`, their sha256 hashes match on disk, and every asset traces to a valid source run ID with config hash and git SHA.
- `tests/test_dashboard.py::test_regeneration_determinism`: Regenerates all assets into a temporary directory and asserts byte-identical output (Rule V12 / H11).
- `tests/test_dashboard.py::test_dashboard_offline`: Asserts `dashboard/index.html` contains no external `http://` or `https://` script/stylesheet/font links.

## 4. Gate Output (`make gate PHASE=10`)
```
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
........................................................................ [ 55%]
........................................................s                [100%]
128 passed, 1 skipped in 18.19s
...                                                                      [100%]
3 passed in 0.10s
PHASE 10 GATE VERIFIED: G3 FREEZE
Total Verified Precomputed Assets: 7
Source Runs Linked: ['cert-full-01', 'h2h3-full-03', 'judge-g2-03', 'shift-full-01']
PHASE 10: PASS (G3 FREEZE)
```

## 5. Numbers Observed vs Expected Range
- Generated Assets: 7/7 present and byte-identical across regenerations.
- External Network Requests in Dashboard: 0 (Offline requirement met).
- Gate G3 Feature Freeze: Enacted in `docs/DECISIONS.md`.
- Test Suite: 128 passed in main suite + 3 passed in dashboard suite.
- Total LLM/Vision API spend in Phase 10: $0.00 (Zero API calls made; purely local deterministic rendering).

## 6. Open Questions & Surprises
- Surprises: None. Deterministic rendering without dynamic timestamps ensured strict byte-level reproducibility required by Rule V12.
- Open questions: None. Ready for human review and merge into `main`.
