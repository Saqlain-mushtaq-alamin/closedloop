# ClosedLoop Demo Video Script & Recording Checklist

**Total Duration: 2:45** (165 seconds)  
**Strict Upper Limit:** ≤ 3:00 (180 seconds)  
**Track:** Indie Developer ("Push the Frontier")  
**Execution Mode:** 100% Precomputed Assets Only • Zero Live API Calls • Completely Offline  
**Note:** Numbers-free script (all quantitative metrics rendered dynamically by dashboard from logs).

---

## Part 1: Four-Beat Timed Video Script (Numbers-Free)

### Beat 1: Fail and Diagnose (0:00 – 0:40 | 40 seconds)
- **Visual:** Open Dashboard Tab 1 (Hero Rollout) and Tab 2 (Failure Analysis). Show initial controller attempting to lift the payload. The gripper slips and drops the object. Display the CMA-ES falsifier isolating the minimal failing scenario alongside the event-boundary filmstrip showing segmentation overlays.
- **On-Screen Text:** *Minimal Failing Counterexample Isolated • Diagnostic Filmstrip Overlay*
- **Narration:**
  > Narration: When an LLM generates a robot controller, a single successful test tells us almost nothing about reliability. ClosedLoop actively searches for failure. Here, our falsifier identifies an edge-of-envelope drop failure. The coordinate minimizer shrinks the scenario to its minimal form, while a diagnostic vision filmstrip tracks the slip boundary, producing an exact diagnostic trace without human intervention.

---

### Beat 2: Fix & Regression Verification (0:40 – 1:20 | 40 seconds)
- **Visual:** Switch to Dashboard Tab 3 (Repair Theatre). Show session repair diff: prompt with minimal failure trace sent to Meta's `muse-spark-1.3`, which synthesizes a targeted repair patch. Show animated replay: under the identical scenario, the gripper now maintains grasp and completes placement. Green checkmarks highlight survival through the regression pipeline.
- **On-Screen Text:** *Targeted Repair Synthesized via muse-spark-1.3 • Multi-Stage Regression Gate Survived*
- **Narration:**
  > Narration: Instead of vague feedback, ClosedLoop supplies the model with the minimal failing scenario and diagnostic frames. Using Meta's muse-spark-1.3, the system generates a targeted patch. We evaluate the candidate across our multi-stage gate: it passes the minimal counterexample and survives regressions on past failures, confirming the repair without admitting regressions.

---

### Beat 3: Heatmap Certification (1:20 – 2:00 | 40 seconds)
- **Visual:** Switch to Dashboard Tab 4 (Interactive Operational Heatmap). Show the 4x4 operational grid across physical parameters. The cells light up green where the exact one-sided Clopper-Pearson bound certifies reliability on fresh scenarios from distribution D that repair never saw.
- **On-Screen Text:** *Fresh Certification Stream • Exact One-Sided Clopper-Pearson Bounds (95% Confidence)*
- **Narration:**
  > Narration: Now we certify reliability. ClosedLoop evaluates the controller on fresh random scenarios from distribution D held out from repair. Each cell in this grid represents an operational envelope slice. Cells certify only when the exact statistical lower bound exceeds the target threshold at ninety-five percent confidence, delineating exactly where the controller is certified.

---

### Beat 4: Price of Footage & Camera Shrinkage (2:00 – 2:45 | 45 seconds)
- **Visual:** Switch to Dashboard Tab 5 (Camera Judge Correction) and Tab 6 (Distribution Shift). Show the corrected heatmap when evaluated via rendered camera footage using SAM 3.1 and Spark vision judge (accounting for calibrated false-positive and false-negative error bounds). Show the distribution shift panel: when tested outside distribution D, the certificate automatically drops and refuses.
- **On-Screen Text:** *Rendered Camera Footage Evaluation • Error-Calibrated Bound • Shift Refusal Outside Distribution D*
- **Narration:**
  > Narration: In real operations, ground-truth simulator states are absent. When evaluated via rendered camera footage, our vision judge corrects the statistical certificate for false-positive and false-negative rates, demonstrating price of footage shrinkage. Finally, under distribution shift outside envelope D, the certificate drops and honestly refuses certification. It certifies only what the evidence can guarantee.

---

## Part 2: Narration Timed Summary & Pacing
- **Beat 1 (0:00–0:40):** ~65 words (~98 wpm)
- **Beat 2 (0:40–1:20):** ~60 words (~90 wpm)
- **Beat 3 (1:20–2:00):** ~65 words (~98 wpm)
- **Beat 4 (2:00–2:45):** ~70 words (~95 wpm)
- **Total Spoken Word Count:** ~260 words (natural, clear delivery within 2:45).

---

## Part 3: Recording & Backup Checklist

### Pre-Recording Setup (Offline Environment)
- [x] Local HTTP server running (`make playground-local` or static server).
- [x] Browser window at 1920x1080 resolution, 100% zoom, dark mode active.
- [x] Fully offline mode verified: zero runtime external network requests.
- [x] Browser bookmarks, extensions, and OS taskbar notifications hidden.
- [x] Microphone noise floor checked; audio level normalized.

### Recording Protocol (Two Takes + Backup)
- [ ] **Take 1 (Full Run-Through):** Execute complete 2:45 walkthrough following the 4-beat script.
- [ ] **Take 2 (Safety Alternate):** Execute full run-through with alternate pacing and clear pauses between beats.
- [ ] **Backup Archival:** Export lossless video file as `closedloop-demo-2m45s.mp4`, verify playback without audio drift or clipping, and save to offline backup directory.
