# ClosedLoop: Technical Report

**Meta Global AI Developer Hackathon • Indie Developer Track ("Push the Frontier")**  
**Build Window:** October 26 – November 4, 2026  
**Author:** Solo Developer (Indie Track)  
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
| **State Headline Bound ($p_L$)** | **0.9623** | `runs/cert-full-01/` | Config hash `1fb5d0f62dca9718` |
| **Camera Corrected Bound ($p_L$)** | **0.9563** | `runs/cert-full-01/` | Corrected via `runs/judge-g2-03/` |
| **Certified Cell Fraction** | **8/16 cells (50.0%)** | `runs/cert-full-01/` | Certified at cell target $p \ge 0.90$ |
| **Operational Envelope** | **Mass $\le 6.25$ kg** | `runs/cert-full-01/` | Friction $\in [0.10, 1.00]$ |
| **Shift Test Reference D Bound** | **0.6186** | `runs/shift-full-01/` | Reference mass $[1.0, 11.5]$ kg |
| **Shift Test Shifted D' Bound** | **0.2017** | `runs/shift-full-01/` | Shifted mass $[6.0, 14.0]$ kg |
| **Shift Refusal Bound Drop** | **0.4169** | `runs/shift-full-01/` | Refuses certification at $p \ge 0.90$ |
| **Vision Judge TPR ($a$)** | **1.0000** ($a_U = 0.9825$) | `runs/judge-g2-03/` | 300 success calibration episodes |
| **Vision Judge FPR ($b$)** | **0.0050** ($b_U = 0.1048$) | `runs/judge-g2-03/` | 400 failure calibration episodes |
| **Vision Judge Ceiling Target** | **0.9435** | `runs/judge-g2-03/` | Gate G2 calibrated threshold |
| **Repair Arm B1 Acceptance Rate** | **0.25** | `runs/h2h3-full-03/` | Random failure feedback |
| **Repair Arm B2 Acceptance Rate** | **0.65** | `runs/h2h3-full-03/` | Minimal counterexample feedback |
| **Repair Arm B3 Acceptance Rate** | **0.80** | `runs/h2h3-full-03/` | Minimal CE + SAM filmstrip |
| **Damage Rate Across All Arms** | **0.00%** | `runs/h2h3-full-03/` | Zero regressions admitted |

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

## 5. Model IDs, Tooling, and Sample API Log

### 5.1 Meta Model Tooling
- **LLM Reasoning & Patch Synthesis:** Meta Model API (`https://api.meta.ai/v1`) using model `muse-spark-1.3`.
- **Vision Grounding & Segmentation:** Meta Model API SAM 3.1 (`sam-3.1`) generating bounding boxes and binary segmentation masks for rendered camera footage.
- **Budget Governance:** Enforced by local `CostMeter` with a hard $60.00 budget cap. Total project spend remained under $18.50 across all phases.

### 5.2 Sample Model API Log
```json
{
  "timestamp": "2026-10-29T18:42:11.204Z",
  "endpoint": "https://api.meta.ai/v1/chat/completions",
  "model": "muse-spark-1.3",
  "request": {
    "temperature": 0.2,
    "top_p": 0.95,
    "max_output_tokens": 2048,
    "messages": [
      {"role": "system", "content": "You are an expert robot controller synthesis engineer..."},
      {"role": "user", "content": "The controller dropped the payload under minimal failure: mass=3.40kg, friction=0.22..."}
    ]
  },
  "response": {
    "id": "chatcmpl-spark-992a8f",
    "prompt_tokens": 842,
    "completion_tokens": 318,
    "total_tokens": 1160,
    "prompt_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "cost_usd": 0.000785
  }
}
```

---

## 6. Limitations (Plan §16)

### 6.1 Simulation-to-Reality Gap
All experiments and certificates were conducted using the PyBullet 3.2.5 physics engine. Contact physics, friction models, and simulated rendering represent approximations of physical reality. Real-world physical robots introduce mechanical wear, sensor noise, calibration drift, and unmodeled compliance. Consequently, certificates generated by ClosedLoop describe the simulator's distribution D and serve as pre-deployment screening, not proof of real-world physical transfer.

### 6.2 Judge Error and Non-Differential Assumption
The camera judge corrected bound assumes that the vision judge error rates ($a_U, b_U$) measured during the calibration phase remain statistically invariant during certification rollouts. In practice, visual error rates can drift if lighting, camera angles, or controller trajectories diverge from calibration rollouts. We mitigate this using bucketed margin-stratified FPR calculations, including final repaired controllers in calibration, freezing judge weights, and reporting gaps if calibration distributions drift.

### 6.3 Distribution-Specific Guarantee
Statistical certificates hold strictly under the defined scenario distribution D. When the operational distribution shifts (as demonstrated in our Hypothesis H4 shift experiment where object mass and friction were perturbed), the certificate from distribution D ceases to apply, and recertification on D' drops the bound and honestly refuses certification.

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
