# Phase 02 — Simulator, task T1, sampler

## Goal
Build the deterministic PyBullet T1 environment, primitives, dual predicates + margin, and the three-stream sampler. Why it matters: every control (V1–V4, V8) lives here; a flaw here invalidates all experiments.

## Inputs
- Plan §6, §9; P00 repo; P01 stats (not yet needed at runtime).

## Deliverables
- `closedloop/sim/env.py`, `closedloop/sim/primitives.py`, `closedloop/sim/predicates.py`, `closedloop/data/sampler.py`, `configs/tasks.yaml`, benchmark note in phase log

## Tasks
1. (90m) Sampler first (tests below): streams repair 0–999999, calibration 1M–1999999, certification 2M–2999999; `LeakageError` on cross-stream/certification misuse. Done when: V4 tests pass.
2. (90m) PyBullet DIRECT env + primitives (`move_to`, gripper, `get_object_pose`) + scenario (x,y,yaw,mass,friction). Done when: scripted episode runs headless.
3. (90m) Two predicates + margin; success = both agree. Done when: V8 logging works on scripted episodes.
4. (60m) Determinism + speed benchmark; 4-hour time-box on grasp stability — if grasp unstable at hour 4, simplify (larger cube/pad, slower primitives) and log in DECISIONS.md. Done when: episodes/sec recorded.

## Tests (write first)
| test name | what it asserts | expected result | which bug it catches |
|---|---|---|---|
| `test_determinism` (V1) | same (program, scenario, seed) twice | identical result hash | hidden RNG/wall-clock |
| `test_negative_control` (V2) | do-nothing; random actions | 0%; ≈0% | predicate always-true |
| `test_stream_disjoint` (V4) | seed sets disjoint; cert only via certify/ | PASS; LeakageError raised | data leakage (H9) |
| `test_predicate_agreement` (V8) | disagreement rate logged | ≤2% on nominal set | predicate gaming |
| `test_margin_sign` | margin <0 ⇔ fail | agrees with predicates | falsifier optimises wrong way |

## Validity checks
- V1 hash equal; V2 0%; V4 disjoint + LeakageError; V8 ≤2% (else fix predicates, not threshold). V3 deferred to P04 with tuned difficulty.

## Expected numbers
Speed: record eps/s on 12 cores; need ≥ pilot throughput for P08 (2400+ cert episodes). Grasp: hand script lifts cube at nominal. Outside: if margin noisy across identical seeds, STOP (V1 fail).

## Gate
Run: `make gate PHASE=02`. Pass: tests pass, prints `PHASE 02: PASS`. STOP if: determinism fails after 3 fixes.

## Fallback / cut
T1 only. Drop distractors/noise (Tier 3) first; never drop dual predicates or seed streams.

## Budget and time-box
0 API $; sim episodes test-only (<500); agent ≤ $4. Oct 28–29 (1 day). Tag `eod-1029` with P03.

## Compliance
H8, H9, H13, H16. Interfaces follow plan §6 Protocols.

## Human review (15 min)
Run `make gate PHASE=02`; inspect sampler seed ranges; watch one rendered episode. Wrong: any `default_rng` without seed, certification seed reachable outside certify/.

## Agent run prompt
Read AGENTS.md, plan §6/§9, and this phase file. Run Phase 02 only: tests first (V1/V2/V4/V8), 4-hour grasp time-box, `make gate PHASE=02`, stop.
