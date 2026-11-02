# ClosedLoop Demo Video Script & Recording Checklist

**Total Duration: 2:45** (165 seconds)  
**Strict Upper Limit:** ≤ 3:00 (180 seconds)  
**Track:** Indie Developer ("Push the Frontier")  
**Execution Mode:** 100% Precomputed Assets Only • Zero Live API Calls • Completely Offline  

---

## Part 1: Four-Beat Timed Video Script

### Beat 1: Fail and Diagnose (0:00 – 0:40 | 40 seconds)
- **Visual:** Open Dashboard Tab 1 (Hero Rollout) and Tab 2 (Failure Analysis). Show initial controller attempting to lift a 3.4 kg cube under friction 0.22. Robot fingers slip; the cube drops to the floor. The dashboard displays the Optuna/CMA-ES minimizer isolating the minimal failing scenario alongside the 5-frame SAM 3.1 filmstrip overlaying object centroids and slip boundaries.
- **On-Screen Text:** *Minimal Failing Counterexample: Mass = 3.40 kg, Friction = 0.22, Gripper Slip at t=1.84s*
- **Narration:**
  > Narration: When an LLM generates a robot controller, a single successful test tells us almost nothing about reliability. ClosedLoop actively searches for failure. Here, our CMA-ES falsifier finds a drop failure under low friction. The coordinate minimizer shrinks the failure to its minimal form: a 3.4-kilogram payload at friction 0.22. A SAM 3.1 vision filmstrip tracks the slip boundary, producing an exact diagnostic trace without human intervention.

---

### Beat 2: Fix & Regression Verification (0:40 – 1:20 | 40 seconds)
- **Visual:** Switch to Dashboard Tab 3 (Repair Theatre). Show session `h2h3-full-03` repair diff: prompt with minimal failure trace sent to Meta's `muse-spark-1.3`, which diagnoses velocity-slip mismatch and generates an adaptive slip-compensation grasp primitive. Show the animated replay: under the exact same scenario, the gripper now maintains grip and securely places the cube. The regression suite displays all green checkmarks.
- **On-Screen Text:** *Repair Synthesized via muse-spark-1.3 • Stage I: Pass • Stage II: Pass • Stage III: 0 Regressions*
- **Narration:**
  > Narration: Instead of vague feedback, we feed the model the minimal failing scenario and diagnostic frames. Using Meta's muse-spark-1.3, ClosedLoop generates a targeted repair that adjusts grip force dynamically. We re-test the repaired controller on the exact counterexample—it passes. It then survives the full regression suite of past failures, confirming the fix without introducing regressions.

---

### Beat 3: Heatmap Certification (1:20 – 2:00 | 40 seconds)
- **Visual:** Switch to Dashboard Tab 4 (Interactive 4x4 Heatmap). Show the 4x4 operational grid (mass vs friction). The 16 cells run on fresh i.i.d. scenarios from distribution D (seeds 2,000,000–2,999,999). Cells light up green where the exact one-sided Clopper-Pearson bound certifies $p \ge 0.90$. The headline overall certificate displays $p_L = 0.9634$ at 95% confidence ($\delta = 0.05$).
- **On-Screen Text:** *Fresh i.i.d. Certification Stream (Seeds 2M+) • State Ground Truth: p_L = 0.9634 (95% Conf)*
- **Narration:**
  > Narration: Now we certify reliability. ClosedLoop evaluates the repaired controller on fresh random scenarios from distribution D that repair never saw. Each cell in this four-by-four grid represents a slice of the operational envelope. Eight cells certify with success probability at least 0.90, yielding a headline certificate of p_L = 0.9634 at ninety-five percent confidence under simulator ground truth.

---

### Beat 4: Footage-price & Camera Shrinkage (2:00 – 2:45 | 45 seconds)
- **Visual:** Switch to Dashboard Tab 5 (Camera Judge & Price of Footage) and Tab 6 (Distribution Shift). Show the corrected heatmap when evaluated via rendered camera footage using SAM 3.1 and Spark vision judge (calibrated false-positive and false-negative error bounds). Show certified area drop from 50% to 37.5%—the measurable price of missing ground truth. Finally, show the distribution shift panel: when tested outside distribution D (heavier mass, lower friction), the certificate honestly refuses.
- **On-Screen Text:** *Camera Judge Corrected Bound: p_L = 0.8842 • Distribution Shift: Bound Drops to 0.0000 (Refused)*
- **Narration:**
  > Narration: In reality, ground-truth simulator states are absent. When we replace simulator truth with a vision judge inspecting rendered camera footage, the certificate corrects for false-positive and false-negative error rates. The certified bound adjusts to 0.8842, quantifying the exact price of relying on camera footage. When tested outside distribution D on extreme payloads, the certificate drops to zero and refuses. It certifies only what it can guarantee.

---

## Part 2: Narration Timed Summary & Pacing
- **Beat 1 (0:00–0:40):** 68 words (~102 wpm)
- **Beat 2 (0:40–1:20):** 66 words (~99 wpm)
- **Beat 3 (1:20–2:00):** 68 words (~102 wpm)
- **Beat 4 (2:00–2:45):** 75 words (~100 wpm)
- **Total Spoken Word Count:** 277 words (easily delivered in 2:45 at a steady, natural cadence of 100–110 words per minute).

---

## Part 3: Recording & Backup Checklist

### Pre-Recording Setup (Offline Environment)
- [x] Ensure local HTTP server is running (`python -m http.server 8000` or `make playground-local`).
- [x] Verify browser window is at 1920x1080 resolution, 100% zoom, dark mode active.
- [x] Zero external network requests: test dashboard in offline mode (airplane mode / disconnected network).
- [x] Ensure browser bookmarks, extensions, and OS taskbar notifications are hidden.
- [x] Microphone check: noise floor < -45 dB, steady gain, pop filter in place.

### Recording Workflow (Two Takes + Backup)
- [x] **Rehearsal:** Run through full 2:45 cue transitions with a digital stopwatch. Confirm transitions occur on schedule at 0:40, 1:20, and 2:00.
- [x] **Take 1 (Master Take):**
  - Record complete unedited video and voice track in single continuous pass.
  - Review timestamp: confirm video duration is between 2:30 and 2:45.
  - Save master recording as `demo/recordings/take_01_master.mp4`.
- [x] **Take 2 (Safety Alternate):**
  - Perform second complete recording pass with alternative pacing/intonation.
  - Verify smooth mouse hovering across heatmap cells and timeline scrubber.
  - Save as `demo/recordings/take_02_alternate.mp4`.
- [x] **Backup Verification:**
  - Verify container integrity with `ffprobe` / media player.
  - Export lossless WebM backup copy to `demo/recordings/backup_lossless.webm`.
  - Confirm video file playback without requiring any cloud login or proprietary codec.
  - Hard limit verification: total duration strictly ≤ 3:00 (180 seconds).
