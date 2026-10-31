# Phase 08 — Certification

## Goal
Certify the final program on fresh i.i.d. certification samples and produce state/camera heatmaps plus the price-of-footage plot. Why it matters: headline result; any seed reuse or wrong delta split silently fabricates it.

## Inputs
- Plan §11 (delta=0.05; K=16, B=4, M frozen pre-run); P01 stats, P06 final program, P07 frozen judge + bounds (if G2 PASS). Certification seeds 2M–2999999, each once/program, loaded only by `closedloop/certify/`.

## Deliverables
- `closedloop/certify/certify.py`, `configs/cert.yaml` (frozen: M, runs/cell from ceiling script), headline certificate, 4×4 heatmaps (mass×friction), certified-area-vs-labels plot data

## Tasks
1. (60m) Freeze cert config: decide M, runs/cell via P01 ceiling. **Targets (decided Oct 28): heatmap cells p≥0.90 state (55 zero-failure/cell) / p≥0.85 camera; headline single certificate p≥0.95 (59 zero-failure, delta=0.05 undivided).** Default n=150/cell. Done when: config hash frozen before any cert episode (V11).
2. (90m) Pilot (V15, 1 cell, ~10%) + independent recomputation + **cost pre-flight** (camera mode: projected 16-cell judge cost from pilot metering vs remaining cap; caps assume Contributor tier + SAM video mode [VERIFY]; block launch if estimate ≥ headroom). Done when: recomputed bound matches and pre-flight passes.
3. (90m×2 max) Full: headline certificate (p≥0.95) + heatmaps (cells p≥0.90 state / p≥0.85 camera, camera only if G2 PASS). Done when: certificates + price plot generated solely from logs.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_cert_seed_once` (V4) | each cert seed once/program | PASS; reuse raises | double-counted evidence |
| `test_error_budget_sum` | allocations sum to delta=0.05 | exact (M as frozen) | overconfident bounds |
| `test_cert_recompute` | independent SciPy recompute = reported | agree 1e-9 | wrong-stream bound |
| `test_price_plot_data` | area vs labels from logs only | PASS (H11) | hand-typed headline |
| `test_cost_preflight` | projected full cert cost vs remaining cap (as P07) | launch blocked if ≥ headroom | mid-run cap abort invalidating certificates |

## Validity checks
- V4, V11, V12-ready logs; judge freeze hash re-verified. Refusal (bound 0 / below target) is a valid outcome — report, never add episodes post-hoc (H12).

## Expected numbers
State certified area >0 expected if P04–P06 succeeded; camera ≤ state. At 0.90/cell, n=150: a truly 98% cell certifies ~92% of the time (0.95/cell would give ~5% at n=150, ~24% at n=200 — why cells are not 0.95). Camera area > state area → STOP (judge/bound bug). Runs/cell outside frozen config → invalid run (H12).

## Gate
Run: `make gate PHASE=08`. Pass: tests pass, certificates recompute, prints `PHASE 08: PASS`. STOP on any cert-seed reuse.

## Fallback / cut
If time short: headline certificate + state heatmap only; camera heatmap from pilot cells labelled as pilot (never mixed). Pitch B → state only.

## Budget and time-box
Sim-heavy: 16 cells × frozen runs/cell; camera API ≤ $15 **only on Contributor tier + SAM video mode [VERIFY]** — otherwise pre-flight estimate governs. State mode ≈ $0 API. Agent ≤ $5. Nov 1–2 (AM Nov 2 last). Tag `eod-1102` (freeze) — no cert changes after.

## Compliance
H6 (stats untouched), H9, H11, H12, H13. Wording: "certified in simulation under distribution D" only (H14).

## Human review (15 min)
Recompute one cell bound by hand (SciPy); check M/K/B in README draft vs config; confirm each seed once. Wrong: camera target claimed without G2 PASS.

## Agent run prompt
Read AGENTS.md, plan §11, and this phase file. Run Phase 08 only: freeze config first, pilot one cell, full certification, independent recompute, `make gate PHASE=08`, stop.
