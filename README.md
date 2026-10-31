# ClosedLoop: Falsify, Repair, Certify

**Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026) • Indie Track ("Push the Frontier")**  
*All code, experiments, and evidence were developed during the hackathon window. No prior code was reused.*

---

### 🌐 Live Interactive Judge Console
👉 **[Launch Live Demo (GitHub Pages)](https://<user>.github.io/<repo>/dashboard/)** *(Deployed via GitHub Actions from `dashboard/`)*

#### Quick Judge Tour (3-Line "What to Click" Guide):
1. **Explore the 4x4 Heatmap (F1/F2):** Click cells in the operational envelope (mass <= 6.25 kg) to inspect simulator margins, confidence intervals, and live Clopper-Pearson calculator checks.
2. **Launch Repair Theatre (F7):** Select any of the 8 recorded repair sessions to step through the failure timeline: minimal counterexample -> prompt -> synthesized controller -> verified replay.
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

### 🤖 Model & Tooling Disclosures
- **Policy Synthesis & Repair:** Meta Model API (`https://api.meta.ai/v1`) using `muse-spark-1.3` (temperature 0.2, top-p 0.95).
- **Vision Judge:** Meta Model API SAM 3.1 (`sam-3.1`) segmentor paired with `muse-spark-1.3` evaluator for rendered camera footage.
- **Simulation Environment:** PyBullet 3.2.5 physics engine (sandboxed subprocess execution with 120s timeout and 1024 MB memory limits).
- **Agent Assistance:** Code developed with AI-agent assistance (Muse Code session, `muse-spark-1.3`).
- **Statistical Guarantee:** Certified in simulation under distribution D with exact one-sided Clopper-Pearson confidence intervals. No claim of real-world transfer or camera alone is made.

---

### 📊 Method Overview
ClosedLoop takes robot programs written by an LLM (`muse-spark-1.3`) and rigorously tests: how reliable is the program, really?
1. **Falsification:** Search for failing physical scenarios using CMA-ES and coordinate minimization on the repair stream.
2. **Repair:** Synthesize targeted code fixes from minimal counterexamples using text and filmstrip feedback (Arms B1/B3).
3. **Certification:** Quantify reliability bounds across operational regions ("success probability at least p, with 95% confidence, certified in simulation under distribution D"), corrected for noisy rendered camera footage evaluation.

Results are produced strictly by `make report` from append-only logs and are never typed by hand. To my knowledge, I did not find this exact combination (falsifier-driven repair + certificate corrected for a rendered-footage judge) elsewhere.
