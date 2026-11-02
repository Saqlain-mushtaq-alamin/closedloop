# ClosedLoop: Hackathon Submission Package & Finals Prep

**Event:** Meta Global AI Developer Hackathon (October 26 – November 4, 2026)  
**Track:** Indie Developer Track  
**Theme:** Push the Frontier  
**Submission Tag:** `submission-v1`  
**Target Submission Date:** November 3, 2026  

---

## 1. Submission Form Fields

### Project Name
**ClosedLoop: Falsify, Repair, Certify**

### Elevator Pitch (Short Description — 150 words)
When an LLM writes code to control a robot, conventional pipelines celebrate after a single passing rollout. But in the physical world, one success says almost nothing about reliability. ClosedLoop actively searches for failure using CMA-ES falsification, shrinks drops and slips to their minimal failing counterexample, and prompts Meta's `muse-spark-1.3` to synthesize targeted patches that pass a 4-stage regression gate. Finally, ClosedLoop evaluates the controller on fresh i.i.d. scenarios under distribution D, computing exact Clopper-Pearson statistical bounds ($p_L = 0.9623$). When ground truth state is unavailable, ClosedLoop inspects rendered camera footage with SAM 3.1 and Spark vision judge, mathematically correcting the certificate for false-positive and false-negative error bounds ($p_L = 0.9563$). Tested on shifted out-of-distribution payloads, the certificate drops to 0.2017 and honestly refuses.

### Track & Theme Selection
- **Track:** Indie Developer Track (`[LOCKED]`)
- **Theme:** Push the Frontier (`[LOCKED]`)

### Meta AI Models & Tooling Used
- **Reasoning, Policy Synthesis & Code Repair:** Meta Model API (`https://api.meta.ai/v1`) using `muse-spark-1.3` (temperature 0.2, top-p 0.95, max_output_tokens 2048).
- **Vision Segmentation & Visual Grounding:** Meta Model API SAM 3.1 (`sam-3.1`) generating bounding boxes and binary segmentation masks from rendered camera footage.
- **Vision Judge Evaluation:** `muse-spark-1.3` multi-modal evaluator combining SAM 3.1 masks with camera imagery to judge task success/failure.
- **AI-Agent Assistance Disclosure:** Software implementation, tests, and documentation were created with AI-agent assistance (Muse Code session, `muse-spark-1.3`) under human developer oversight.

### URLs & Public Access
- **Public Git Repository:** `https://github.com/<user>/closedloop` (Publicly accessible, opens without login).
- **Interactive Live Judge Console:** `https://<user>.github.io/<repo>/dashboard/` (Deployed via GitHub Pages, 100% client-side, zero runtime external API requirements).
- **Demo Video Link:** `https://<video-host-url>/closedloop-demo-2m45s.mp4` (Total duration 2:45, strictly ≤ 3:00, publicly viewable without requiring an account or login).

### Contributor List
- **Solo Developer:** Indie Track submission by a single participant. All contributions and git commits originated during the hackathon window.

---

## 2. Key Statistical Results (Generated Strictly from Logs)

All results below are produced by `make report` from append-only logs (`runs/*/episodes.jsonl`) and verified against `assets/report_summary.json` (Rule H11 / V12):

| Evaluation Dimension | Bound / Metric | Verification Standard | Source Run ID |
|---|---|---|---|
| **Simulator Ground Truth Bound ($p_L$)** | **0.9623** | 95% Clopper-Pearson CI ($\delta_{cell} = 0.003125$) | `runs/cert-full-01` |
| **Rendered Camera Footage Bound ($p_L$)** | **0.9563** | Corrected for SAM 3.1 + Spark error rates | `runs/cert-full-01` + `judge-g2-03` |
| **Operational Envelope Coverage** | **8/16 cells (50.0%)** | Certified at cell target $p \ge 0.90$ (Mass $\le 6.25$ kg) | `runs/cert-full-01` |
| **Distribution Shift Reference D** | **0.6186** | Empirical pass rate 68.7% ($n=150$) | `runs/shift-full-01` |
| **Distribution Shift Shifted D'** | **0.2017** | Empirical pass rate 26.0% ($n=150$) | `runs/shift-full-01` |
| **Shift Refusal Drop** | **0.4169** | Bound drop triggers honest certificate refusal | `runs/shift-full-01` |
| **Vision Judge True Positive Rate ($a$)** | **1.0000** ($a_U = 0.9825$) | 300 success calibration episodes | `runs/judge-g2-03` |
| **Vision Judge False Positive Rate ($b$)** | **0.0050** ($b_U = 0.1048$) | 400 failure calibration episodes | `runs/judge-g2-03` |
| **Repair Acceptance: Arm B1 (Random)** | **0.25** | 20 trajectories, equal episode/token budget | `runs/h2h3-full-03` |
| **Repair Acceptance: Arm B2 (Minimal CE)**| **0.65** | 20 trajectories, coordinate minimization | `runs/h2h3-full-03` |
| **Repair Acceptance: Arm B3 (CE + SAM)**  | **0.80** | 20 trajectories, 5-frame SAM 3.1 filmstrip | `runs/h2h3-full-03` |
| **Damage Rate Across Arms** | **0.00%** | Zero regressions admitted by 4-stage gate | `runs/h2h3-full-03` |

---

## 3. Evaluator Reproduction & Verification Quickstart

Evaluators can verify every claim and number locally in under 2 minutes:

```bash
# 1. Clone repository
git clone https://github.com/<user>/closedloop.git
cd closedloop

# 2. Check out the verified submission tag
git checkout submission-v1

# 3. Verify all 57 statistical certificates independently using SciPy
make verify-evidence
# Output: 57/57 match

# 4. Run complete compliance and test suite (221+ passing tests)
make gate PHASE=12
# Output: PHASE 12: PASS

# 5. Launch offline interactive judge console locally (0 external network requests)
python -m http.server 8000
# Open http://localhost:8000/dashboard/
```

---

## 4. Limitations & Scientific Boundaries (Plan §16)

1. **Simulation-to-Reality Gap:** All certificates evaluate the PyBullet 3.2.5 physics simulator. Contact physics and sensor noise are approximations. The certificate provides pre-deployment screening under distribution D, not proof of real-world physical safety.
2. **Judge Error Non-Differential Assumption:** Corrected bounds assume vision judge error rates measured on calibration rollouts reflect certification rollouts. Mitigated by margin-stratified bucketed FPR, frozen judge weights, and drift monitoring.
3. **Distribution-Specific Scope:** Guarantees apply strictly to scenario distribution D. When tested outside distribution D, the certificate drops and honestly refuses certification.

---

## 5. Finals (Nov 9) Presentation Fallback Plan

In the event of network disruption, conference Wi-Fi outages, or API rate limits during live finals judging:
1. **Stable Offline Console:** The interactive Judge Console (`dashboard/index.html`) is 100% offline-compatible. It embeds all necessary CSS, JavaScript, and precomputed telemetry (`data.js`). Evaluators can interact with the live 4x4 heatmap, toggle state vs camera correction, inspect SAM failure filmstrips, and run the client-side cryptographic certificate hash lab with zero internet connection.
2. **Precomputed Rollout Telemetry:** All 2,459 certification episodes, 700 calibration episodes, and 2,320 repair trajectories are committed as append-only logs (`episodes.jsonl`), enabling instantaneous replay and SciPy recomputation.
3. **Backup Master Recording:** Lossless video recording (`demo/recordings/take_01_master.mp4`) timed to 2:45 is archived and ready for immediate screen-share fallback.
