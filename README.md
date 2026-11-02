# ClosedLoop: Falsify, Repair, Certify

**Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026) • Indie Developer Track ("Push the Frontier")**  
*Built during the event (Oct 28 to Nov 4, 2026) by a solo developer; early commits used the placeholder git identity closedloop-dev. No prior code was reused.*



---

### 🌐 Live Interactive Judge Console
👉 **[Launch Live Demo (GitHub Pages)](https://<user>.github.io/<repo>/dashboard/)** *(Deployed via GitHub Actions from `dashboard/`)*

#### Quick Judge Tour (3-Line "What to Click" Guide):
1. **Explore the 4x4 Heatmap (F1/F2):** Click cells in the operational envelope (mass <= 6.25 kg) to inspect simulator margins, confidence intervals, and live Clopper-Pearson calculator checks.
2. **Launch Repair Theatre (F7):** Select any of the recorded repair sessions to step through the failure timeline: minimal counterexample -> prompt -> synthesized controller -> verified replay.
3. **Verify Guarantee Honesty under Shift (F5):** View the distribution shift panel (D -> D') to inspect certificate refusal when tested on heavy/slippery out-of-distribution payloads.

---

### 🔍 Offline Inspection & Reproducibility
The dashboard is 100% offline-compatible with zero runtime external API or network dependencies:
```bash
python -m http.server 8000
# Open http://localhost:8000/dashboard/
```

### 🛡️ One-Command Cryptographic Evidence Verification
Recompute every certified bound (1 - delta = 0.95, 1 - d_cell = 0.996875), camera judge correction, calibration bound, and shift bound directly from the committed append-only logs (`episodes.jsonl`) using an independent SciPy path:
```bash
make verify-evidence
# Output: 57/57 match
```

---

### 🎮 Tab 7: ClosedLoop Playground (Live Lab & Interactive Execution)
The dashboard includes an interactive simulation and cryptographic verification lab:
- **Tier 2 Live Simulator & Tier L Local Runner**: Run live physics episodes via FastAPI + PyBullet (`make playground-local`), streaming per-episode telemetry and camera frames over Server-Sent Events (SSE).
- **4-Tuple Cryptographic Badge Evaluation**: Instantaneously verifies whether the in-browser controller matches the frozen certified program (`5f74f776...` / `bec73dec...`), robot hardware preset, task space distribution, and simulation engine hash. Any code edit or parameter deviation voids the certificate in real time.
- **Hardware Preset Clamps**: Standard (100 N) and Heavy-Duty (200 N) gripper clamps prevent impossible software repairs on heavy physical payloads.
- **4-Stage Acceptance Gate Pipeline**: Evaluates candidate patches against Stage I (Minimal Counterexample), Stage II (Severe Counterexample), Stage III (Regression Suite), and Stage IV (Falsifier Rerun).
- **Tier 0 Hash Lab (Offline Fallback)**: Full client-side SHA-256 certificate evaluation runs 100% offline in pure JavaScript with zero backend dependencies.

To launch the interactive playground locally:
```bash
make playground-local
# Open http://127.0.0.1:8000/dashboard/index.html -> Click Tab 7 (Playground: Live Lab)
```
See [`docs/PLAYGROUND_WALKTHROUGH.md`](file:///d:/canvas/closedloop/docs/PLAYGROUND_WALKTHROUGH.md) for the complete step-by-step evaluator guide and video walkthrough.

---

### 🤖 Model & Tooling Disclosures
- **Policy Synthesis & Repair:** Meta Model API (`https://api.meta.ai/v1`) using `muse-spark-1.3` (temperature 0.2, top-p 0.95, max_output_tokens 2048).
- **Vision Judge:** Meta Model API SAM 3.1 (`sam-3.1`) segmentor paired with `muse-spark-1.3` evaluator for rendered camera footage.
- **Simulation Environment:** PyBullet 3.2.5 physics engine (isolated subprocess execution with 120s timeout and 1024 MB memory limits).
- **AI-Assistance Disclosure:** Code and documentation developed with AI-agent assistance (Muse Code session, `muse-spark-1.3`) under developer oversight.
- **Statistical Guarantee:** Certified in simulation under distribution D with exact one-sided Clopper-Pearson confidence intervals. No claim of real-world transfer is made.

---

### 📐 Error Budget Allocation
The statistical guarantee uses overall significance level $\delta = 0.05$ (95% confidence), structured across $K = 16$ heatmap cells, $B = 4$ calibration margin buckets, and $M = 1$ candidate program evaluated:
- **State Ground Truth Mode:** Per-cell budget $\delta / (K \cdot M) = 0.05 / 16 = 0.003125$.
- **Camera Judge Mode (Rendered Camera Footage):**
  - TPR upper bound ($a_U$): $0.1 \cdot \delta = 0.005$.
  - FPR upper bound ($b_U$): per margin bucket $0.1 \cdot \delta / B = 0.00125$.
  - Corrected per-cell bound ($q_L$): $0.8 \cdot \delta / (K \cdot M) = 0.0025$.
  - Conservation check: $0.005 + 4 \times 0.00125 + 16 \times 0.0025 = 0.050 = \delta$.

---

### 📊 Verified Headline Results (Generated Strictly from Logs)
All numbers below are produced directly by `make report` from append-only logs (`runs/*/episodes.jsonl`) and verified against `assets/report_summary.json` (Rule H11):
- **Headline State Bound:** $p_L = 0.9623$ (certified in simulation under distribution D at cell level target $p \ge 0.90$).
- **Headline Camera Corrected Bound:** $p_L = 0.9563$ (corrected for vision judge false-positive and false-negative error bounds from rendered camera footage).
- **Certified Cell Fraction:** 8/16 cells certified (50.0% of operational space; payload mass $\le 6.25$ kg).
- **Autonomous Repair vs Generation Alone (H1):** Supported (+0.1875 gap, 95% CI [0.10, 0.2875] for B1 over B0) for one starting program.
- **Minimal Counterexamples (H2):** Negative (acceptance B2 = 0.10 vs B1 = 0.25, difference -0.15) for one starting program.
- **Visual Filmstrips (H3):** Null (acceptance B3 = 0.05 vs B2 = 0.10, difference -0.05) for one starting program.
- **Distribution Shift Refusal (H4):** On reference distribution D, bound is 0.6186; on shifted distribution D' (heavier payloads / lower friction), bound drops to 0.2017 (drop of 0.4169), honestly refusing certification at target $p \ge 0.90$.
- **Vision Judge Calibration:** True positive rate 1.0 (lower bound 0.9825), false positive rate 0.005 (worst-bucket upper bound 0.1048), certifiable ceiling target 0.9435.

---

### ⚠️ Limitations (Plan §16)
1. **Simulation Only:** All evaluations and certificates are established strictly within the PyBullet 3.2.5 simulation environment. A non-zero sim-to-real gap exists due to contact compliance, sensor noise, and actuator latency; no claim of real-world transfer or physical safety is made.
2. **Judge Error Assumption & Frame Reuse:** The camera judge bound correction relies on the assumption that vision judge errors are non-differential across the evaluation envelope. The calibration and certification pipeline reuses fixed 5-frame event boundaries, which may miss transient mid-trajectory slips.
3. **Distribution-Specific Certificate:** Guarantees apply strictly to test scenarios drawn i.i.d. from distribution D. Under distribution shift (as demonstrated in Hypothesis H4), guarantees void and the pipeline refuses certification.
4. **H2 Negative and H3 Null:** For the starting program evaluated, minimal counterexample feedback (Arm B2, acceptance rate 0.10) underperformed random failure feedback (Arm B1, acceptance rate 0.25, difference -0.15; negative result), and SAM 3.1 visual filmstrip feedback (Arm B3, acceptance rate 0.05, difference -0.05; null result) yielded no measurable benefit over minimal counterexamples alone.
5. **Single Starting Program:** Hypotheses H1–H3 were evaluated on one initial synthesized controller program (`bec73dec...`). Results reflect this program family and may vary across alternative architectures.
6. **Friction Insensitivity:** Grasp slip failures in the hero task were governed predominantly by payload mass relative to commanded normal force; friction variation across $[0.10, 1.00]$ exhibited no measurable effect on slip boundaries.
7. **Partial Envelope Certified:** For program v1, only 8 of 16 operational cells (50.0%) certified under target $p \ge 0.90$; payloads with mass $8.5 \le m \le 11.5$ kg consistently failed standard clamping forces and remained uncertified.

---

### 🔬 Method Overview
ClosedLoop takes robot programs written by an LLM (`muse-spark-1.3`) and answers: how reliable is the program, really?
1. **Falsification:** Search for failing physical scenarios using CMA-ES and coordinate minimization on the repair stream.
2. **Repair:** Synthesize targeted controller fixes from minimal counterexamples using text and filmstrip feedback (Arms B1/B3).
3. **Certification:** Quantify reliability bounds across operational regions ("success probability at least p, with 95% confidence, certified in simulation under distribution D"), corrected for noisy rendered camera footage evaluation.

To my knowledge, I did not find this exact combination (falsifier-driven repair + certificate corrected for a rendered camera footage judge) elsewhere in published benchmarks.

