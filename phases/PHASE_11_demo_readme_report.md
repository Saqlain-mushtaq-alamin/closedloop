# Phase 11 — Demo, README, technical report

## Goal
Produce the 2:45 demo, README, and short report using generated numbers only. Why it matters: Demo + Impact are judged here; one hand-typed number voids trust in all results.

## Inputs
- Plan §13–§16; P10 assets; P08/P09 figures. Script re-timed to 2:45 (plan beats sum 3:00 — trim Fix/Heatmap).

## Deliverables
- `demo/SCRIPT.md` (0:00 Fail/diagnose, Fix, Heatmap, Footage-price; total 2:45), backup recording, `README.md` (final), `docs/REPORT.md`

## Tasks
1. (90m) Script + recording checklist (precomputed assets only, no live API; two takes + backup). Done when: timed read ≤2:45, video ≤3:00.
2. (90m) README/report from `make report` outputs: model IDs + sample API log, error budget (K/B/M), limitations (§16 all), AI-assistance disclosure, built-during note. Done when: V12/V13 pass.
3. (45m) Human checks: commissioning citation [VERIFY or delete], wording pass. Done when: checklist signed in phase log.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_readme_numbers_from_logs` (V12) | each README number in report output | PASS | H11 hand-typed results |
| `test_wording_scan` (V13/H14) | no unqualified first/novel/proven/safe/camera alone | PASS | overclaim |
| `test_report_limitations` | §16 limitations all present | PASS | hidden caveats |

## Validity checks
- V12, V13. Claims read "certified in simulation under distribution D", "rendered camera footage", "to my knowledge, I did not find…".

## Expected numbers
Video 2:30–3:00 (aim 2:45). Longer → re-cut, never speed past captions. Any number without log source → delete it.

## Gate
Run: `make gate PHASE=11`. Pass prints `PHASE 11: PASS`. STOP if a headline number cannot be regenerated.

## Fallback / cut
Fewer dashboard views in video (keep 4 beats); report shrinks before demo does. Optional 45 s clip only after submission (P12).

## Budget and time-box
API $0 (recording offline); agent ≤ $4. Nov 3 AM. Tag in P12.

## Compliance
H11, H14. Hackathon: demo ≤3 min, in-event work only, Meta IDs + disclosure.

## Human review (15 min)
Watch full video once (links open logged-out?); grep README numbers against report; read limitations. Wrong: "safe/proven" anywhere, even in narration.

## Agent run prompt
Read AGENTS.md, plan §13–§16, and this phase file. Run Phase 11 only: script, generated README/report, `make gate PHASE=11`, stop. Do not submit.
