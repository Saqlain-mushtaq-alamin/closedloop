# ClosedLoop: Technical Report

**Meta Global AI Developer Hackathon • Indie Developer Track ("Push the Frontier")**  
**Build Window:** October 26 – November 4, 2026 (initial commit 2026-10-28, latest commit 2026-11-03, within the hackathon event period)  
**Author:** Saqlain Mushtaq Alamin (Indie Track solo participant; early commits used placeholder identity closedloop-dev)  
*All code, models, experiments, and evidence were built during the hackathon window. No prior code was reused.*

---

## 1. Executive Summary

When a large language model writes code to control a robot, conventional evaluation loops stop after observing a single successful rollout. A single success in simulation yields almost zero statistical confidence regarding real-world execution.

ClosedLoop provides an end-to-end reliability assurance framework:
1. **Falsify:** Actively search the parameter space using CMA-ES and coordinate minimization to isolate the minimal failing scenario.
2. **Repair:** Supply the minimal counterexample and diagnostic visual filmstrips to Meta's `muse-spark-1.3` to synthesize targeted patches that survive a regression suite.
3. **Certify:** Evaluate the final program on fresh, unseen random scenarios from distribution D, computing exact one-sided Clopper-Pearson confidence bounds.
4. **Camera Judge Correction:** When ground-truth simulator states are unavailable, evaluate rendered camera footage using SAM 3.1 and `muse-spark-1.3`, adjusting the certificate to rigorously account for vision judge false-positive and false-negative error bounds.

To my knowledge, I did not find this exact combination (falsifier-driven repair + certificate corrected for a rendered camera footage judge) elsewhere in published benchmarks.

---

## 2. System Architecture & Methodology

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ClosedLoop Architecture                         │
│                                                                        │
│   [Repair Stream: Seeds 0 - 999,999]                                   │
│   Controller ──► CMA-ES Falsifier ──► Minimal Counterexample           │
│                         │                                              │
│                         ▼                                              │
│   Meta muse-spark-1.3 + SAM 3.1 Filmstrip ──► Targeted Repair Patch    │
│                         │                                              │
│                         ▼                                              │
│   4-Stage Gate: Stage I (CE) ──► Stage II (Severe) ──► Regression      │
│                                                                        │
│   [Calibration Stream: Seeds 1,000,000 - 1,999,999]                   │
│   Rendered Camera Footage ──► SAM 3.1 + Spark ──► TPR / Bucketed FPR   │
│                                                                        │
│   [Certification Stream: Seeds 2,000,000 - 2,999,999] (Fresh i.i.d.)   │
│   Repaired Controller ──► Distribution D ──► Clopper-Pearson / Corrected│
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Falsification and Minimization
Using an Optuna CMA-ES sampler, ClosedLoop optimizes over task parameters (object mass, surface friction, initial coordinates, and yaw) targeting negative task margin. Once a failure occurs, a greedy coordinate minimizer shrinks each parameter toward nominal, isolating the minimal set of conditions triggering failure.

### 2.2 Model-Driven Repair
Repairs are synthesized using Meta's `muse-spark-1.3` (temperature 0.2, top-p 0.95). In Arm B3, the prompt provides:
- Controller source code
- Minimal failing scenario parameters
- Execution trace summary
- 5-frame SAM 3.1 visual filmstrip showing object centroids and contact masks.

The candidate controller must pass a 4-stage acceptance pipeline before replacement:
- **Stage I:** Must pass the minimal counterexample.
- **Stage II:** Must pass the severe original counterexample.
- **Stage III:** Must achieve 0 regressions on all historical counterexamples.
- **Stage IV:** Must survive a localized falsifier rerun.

### 2.3 Statistical Certification
Evaluated strictly on fresh i.i.d. samples from distribution D:
- **State Ground Truth Mode:** One-sided Clopper-Pearson lower bound at significance $\delta_{cell} = \delta / (K \cdot M)$.
- **Camera Judge Mode:** Corrected bound accounting for calibrated true positive rate ($a_U$) and bucketed false positive rate ($b_U$):
  $$p_L = \frac{q_L - b_U}{a_U - b_U}$$

---

## 3. Quantitative Results & Generated Numbers

All metrics below are generated strictly by `make report` from committed, append-only logs (`runs/*/episodes.jsonl`) and verified against `assets/report_summary.json` (Rule H11 / V12):

| Metric | Measured Value | Data Source | Provenance Link |
|---|---|---|---|
| **V1 Headline State Bound ($p_L$)** | **0.4778** (uncertified at target $p \ge 0.90$) | `runs/cert-full-01/` | Config hash `04073afb3e1d4af2` |
| **V1 Headline Camera Bound ($p_L$)** | **0.4090** (uncertified at target $p \ge 0.85$) | `runs/cert-full-01/` | Corrected via `runs/judge-g2-03/` |
| **V1 Best Cell State Bound (Cell 00)** | **0.9623** (certified at cell target $p \ge 0.90$) | `runs/cert-full-01/` | Mass $\le 3.625$ kg, Friction $\in [0.10, 0.325]$ |
| **V1 Best Cell Camera Bound (Cell 00)** | **0.9563** (corrected for judge error) | `runs/cert-full-01/` | Corrected via `runs/judge-g2-03/` |
| **V2 Repaired Policy State Bound ($p_L$)** | **0.9505** (certified across full envelope) | `runs/cert3-full-01/` | 16/16 cells certified (100% area) |
| **Certified Cell Fraction (V1)** | **8/16 cells (50.0%)** | `runs/cert-full-01/` | Certified at cell target $p \ge 0.90$ |
| **Certified Cell Fraction (V2)** | **16/16 cells (100.0%)** | `runs/cert3-full-01/` | Upgraded to 300N clamp + dwell |
| **Operational Envelope (V1 Certified)** | **Mass $\le 6.25$ kg** | `runs/cert-full-01/` | Friction $\in [0.10, 1.00]$ |
| **Shift Test Reference D Bound** | **0.6186** | `runs/shift-full-01/` | Reference mass $[1.0, 11.5]$ kg |
| **Shift Test Shifted D' Bound** | **0.2017** | `runs/shift-full-01/` | Shifted mass $[6.0, 14.0]$ kg |
| **Shift Refusal Bound Drop** | **0.4169** | `runs/shift-full-01/` | Refuses certification at $p \ge 0.90$ |
| **Vision Judge TPR ($a$)** | **1.0000** ($a_U = 0.9825$) | `runs/judge-g2-03/` | 300 success calibration episodes |
| **Vision Judge FPR ($b$)** | **0.0050** ($b_U = 0.1048$) | `runs/judge-g2-03/` | 400 failure calibration episodes |
| **Vision Judge Ceiling Target** | **0.9435** | `runs/judge-g2-03/` | Gate G2 calibrated threshold |
| **Repair Arm B1 Acceptance Rate** | **0.25** | `runs/h2h3-full-03/` | Random failure feedback (for one starting program) |
| **Repair Arm B2 Acceptance Rate** | **0.10** | `runs/h2h3-full-03/` | Minimal counterexample feedback (for one starting program) |
| **Repair Arm B3 Acceptance Rate** | **0.05** | `runs/h2h3-full-03/` | Minimal CE + SAM filmstrip (for one starting program) |
| **Damage Rate B2** | **0.05** | `runs/h2h3-full-03/` | 1 regression in 20 trajectories (B1: 0.00, B3: 0.00) |

### 3.1 Hypothesis Evaluation Summary (H1 – H4)
- **Hypothesis H1 (Autonomous Repair vs Generation Alone): Supported.** Held-out test performance improved from B0 mean 0.7375 to B1 mean 0.8125, an empirical gain of +0.0750 (+7.5 percentage points; 95% paired bootstrap CI [0.0125, 0.1625]) for one starting program. (B1's internal loop-minus-held-out gap was +0.1875, 95% CI [0.10, 0.2875], reflecting loop fitting). Autonomous repair with execution feedback significantly improved task reliability over zero-shot generation alone.
- **Hypothesis H2 (Minimal Counterexample B2 vs Random Failure B1): Negative (acceptance rate B2 = 0.10 vs B1 = 0.25, difference -0.15, 95% CI [-0.2125, 0.0]) for one starting program.** Counter-intuitively, presenting a tightly minimized counterexample led the LLM to synthesize brittle patches that passed the isolated counterexample but failed broader rerun scenarios or caused localized regressions (damage rate 0.05 in B2 vs 0.00 in B1).
- **Hypothesis H3 (Visual Filmstrip B3 vs Minimal Counterexample B2): Null (acceptance rate B3 = 0.05 vs B2 = 0.10, difference -0.05, 95% CI [-0.125, +0.0625]) for one starting program.** Adding a 5-frame SAM 3.1 visual filmstrip with segmentation overlays did not yield a statistically significant improvement in patch acceptance over minimal counterexample text alone.
- **Hypothesis H4 (Distribution Shift Refusal): Supported (bound drop 0.6186 -> 0.2017, difference 0.4169).** When evaluated outside the operational distribution D, statistical bounds dropped sharply below the 0.90 target threshold, triggering automatic and honest refusal.

---

## 4. Error Budget Allocation (Plan §11)

The overall error rate is bounded by $\delta = 0.05$ (95% confidence level), allocated across $K = 16$ operational cells, $B = 4$ margin buckets, and $M = 1$ candidate program certified:

- **State Ground Truth Allocation:**
  $$\delta_{cell} = \frac{\delta}{K \cdot M} = \frac{0.05}{16 \times 1} = 0.003125$$
- **Camera Judge Allocation (Rendered Camera Footage):**
  - TPR upper bound: $0.1 \cdot \delta = 0.005$
  - FPR upper bound: $0.1 \cdot \delta / B = 0.005 / 4 = 0.00125$ per bucket
  - Cell empirical bound: $0.8 \cdot \delta / (K \cdot M) = 0.04 / 16 = 0.0025$ per cell
  - Conservation identity:
    $$0.1\delta + B\left(\frac{0.1\delta}{B}\right) + (K \cdot M)\left(\frac{0.8\delta}{K \cdot M}\right) = 0.005 + 0.005 + 0.040 = 0.050 = \delta$$

---

## 5. Model IDs, Tooling, and Verified Log Entry

### 5.1 Meta Model Tooling
- **LLM Reasoning & Patch Synthesis:** Meta Model API (`https://api.meta.ai/v1`) using model `muse-spark-1.3`.
- **Vision Grounding & Segmentation:** Meta Model API SAM 3.1 (`sam-3.1`) generating bounding boxes and binary segmentation masks for rendered camera footage.
- **Budget Governance:** Enforced by local `CostMeter` with a hard $60.00 budget cap. Total project spend was $5.12 across valid production runs ($6.00 total across all runs including quarantined runs; see `assets/spend_summary.json`), well within the $60.00 hard budget cap. (Note: in `cert-full-01`, `cost_usd` is stamped as a run total of $2.594031 across episodes with SAM token counts as synthetic estimates; it is not a per-episode charge).

### 5.2 Real Model API Cache Entry (Source: `runs/judge-g2-03/llm_cache.json`)
The following is an authentic entry copied directly from `runs/judge-g2-03/llm_cache.json` (prompt hash `00f88acec02cf524211b6be4`), recording live Meta Model API invocation for SAM 3.1 visual grounding and `muse-spark-1.3` reasoning:

```json
{
  "source_file": "runs/judge-g2-03/llm_cache.json",
  "prompt_hash": "00f88acec02cf524211b6be4",
  "model": "muse-spark-1.3",
  "vision_model": "sam-3.1",
  "tokens_in": 2247,
  "tokens_out": 364,
  "cost_usd": 0.003531,
  "cube_box": [178, 159, 204, 189],
  "cube_centroid": [191.0, 174.0],
  "pad_box": [123, 136, 188, 184],
  "geometric_pass": false,
  "spark_pass": false,
  "pass_verdict": false,
  "confidence": 0.95,
  "reason": "red cube is beside green pad on table, not resting on top of pad"
}
```

---

## 6. Limitations (Plan §16)

1. **Simulation-to-Reality Gap:** All experiments and certificates were conducted using the PyBullet 3.2.7 physics engine. Contact physics, friction models, and simulated rendering represent approximations of physical reality. Real-world physical robots introduce mechanical wear, sensor noise, calibration drift, and unmodeled compliance. Consequently, certificates generated by ClosedLoop describe the simulator's distribution D and serve as pre-deployment screening, not proof of real-world physical transfer or safety.
2. **Judge Error Assumption and Frame Reuse:** The camera judge corrected bound assumes that the vision judge error rates ($a_U, b_U$) measured during the calibration phase remain statistically invariant during certification rollouts. In practice, visual error rates can drift if lighting, camera angles, or controller trajectories diverge from calibration rollouts. The pipeline reuses fixed 5-frame event boundaries, which may miss transient mid-trajectory slips.
3. **Distribution-Specific Certificate:** Statistical certificates hold strictly under the defined scenario distribution D. When the operational distribution shifts (as demonstrated in our Hypothesis H4 shift experiment where object mass and friction were perturbed), the certificate from distribution D ceases to apply, and recertification on D' drops the bound and honestly refuses certification.
4. **H2 Negative and H3 Null Results:** For the starting program evaluated, minimal counterexample feedback (Arm B2, acceptance rate 0.10) underperformed random failure feedback (Arm B1, acceptance rate 0.25; negative result), and SAM 3.1 visual filmstrip feedback (Arm B3, acceptance rate 0.05; null result) yielded no measurable benefit over minimal counterexamples alone.
5. **Single Starting Program:** Hypotheses H1–H3 were evaluated on one initial synthesized controller program (`bec73dec...`). Results reflect this program family and may vary across alternative architectures.
6. **Friction Insensitivity:** Grasp slip failures in the hero task were governed predominantly by payload mass relative to commanded normal force; friction variation across $[0.10, 1.00]$ exhibited no measurable effect on slip boundaries.
7. **Partial Envelope Certified:** For program v1, only 8 of 16 operational cells (50.0%) certified under target $p \ge 0.90$; payloads with mass $8.5 \le m \le 11.5$ kg consistently failed standard clamping forces and remained uncertified.


---

## 7. Future Work (Plan §16.4)

1. **Physical Robot Calibration:** Calibrate scenario distribution D from real robot teleoperation logs and sensor traces to tighten the sim-to-real transfer boundary.
2. **Hardware Validation:** Deploy synthesized controllers to physical 6-DoF and 7-DoF manipulators to empirically measure real-world reliability gaps.
3. **Sequential Testing:** Implement sequential probability ratio tests (SPRT) and betting martingales to terminate simulation runs early, reducing the required simulation episodes by an estimated 40–60%.
4. **Prediction-Powered Inference (PPI):** Explore semi-supervised prediction-powered inference to reduce the number of expensive human and vision labels required for judge calibration.
5. **Broader Domain Applications:** Extend the falsify-repair-certify framework to autonomous software agents, game-playing bots, and high-stakes autonomous vehicle control.
6. **Open Benchmark Suite:** Release the full PyBullet manipulation benchmark, minimal counterexample suite, and cryptographically verifiable evaluation logs as an open research resource.

---

## 8. Compliance & Ethical Disclosures

- **Hackathon Window Compliance:** All code, simulations, models, and assets were developed exclusively during the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026).
- **AI-Assistance Disclosure:** Code, tests, and documentation were created with AI-agent assistance (Muse Code session, `muse-spark-1.3`) under developer oversight.
- **Licensing & Dependencies:** All dependencies are permissively licensed (MIT, BSD, Apache-2.0, PSF) as cataloged in `THIRD_PARTY.md`.
- **Wording Standard (Rule H14):** All statistical reliability statements specify that bounds are certified in simulation under distribution D and evaluated on rendered camera footage.
