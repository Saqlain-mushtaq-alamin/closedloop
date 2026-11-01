# ClosedLoop Playground: Evaluator Walkthrough & Architecture Guide

**Phase PA6 • Live Lab & Cryptographic Badge Verification**  
*Certified in simulation under distribution D with exact one-sided Clopper-Pearson confidence bounds.*

---

## 1. Overview & Core Capabilities

The **ClosedLoop Playground (Tab 7: Live Lab)** allows evaluators to interactively inspect, execute, modify, and verify robot manipulation policies live in simulation:

1. **4-Tuple Cryptographic Badge Evaluation**:
   The certificate status is bound to the exact 4-tuple:
   $$\text{Tuple} = \langle \text{Program SHA-256}, \text{Robot Preset}, \text{Task Operating Space}, \text{Simulation Code SHA-256} \rangle$$
   Modifying any statement or constant in the code editor, or switching to clamped hardware or shifted operating distributions, immediately invalidates the certificate in real time (`PLAYGROUND, NOT CERTIFIED` / `VOID`).

2. **Live SSE Simulation Streaming**:
   Streams per-episode physical simulation telemetry and rendered camera frames from the PyBullet physics engine over Server-Sent Events (SSE) with per-step hardware force clamp accounting.

3. **Hardware Constraint Enforcement**:
   Enforces physical robot actuator limits (e.g. Standard Gripper 100 N clamp). Heavy payloads (up to 11.5 kg) physically slip under clamped grip forces, demonstrating that software modifications alone cannot bypass hardware physics limits.

4. **Live Four-Stage Acceptance Gate Pipeline**:
   Tests candidate repairs across:
   - **Stage I (Minimal Counterexample)**: Verifies survival on the exact falsified corner-case scenario.
   - **Stage II (Severe Counterexample)**: Verifies robustness under extreme friction and mass stress.
   - **Stage III (Regression Set)**: Replays previously passed calibration scenarios to prevent behavioral regression.
   - **Stage IV (Falsifier Rerun)**: Runs adversarial search to ensure no adjacent failure modes were introduced.

---

## 2. Three-Tier Execution Fallback Ladder

To guarantee uninterrupted evaluation regardless of server or network conditions, the Playground implements a three-tier execution ladder:

| Tier | Name | Command / URL | Capabilities |
| :--- | :--- | :--- | :--- |
| **Tier 2** | Live Cloud / Server Backend | `http://127.0.0.1:8000/dashboard/` | Full FastAPI SSE streaming, PyBullet physics execution, dynamic camera rendering, live acceptance gate evaluation. |
| **Tier L** | Local One-Command Runner | `make playground-local` | Runs the identical FastAPI backend locally on port 8000 using the pinned virtual environment. |
| **Tier 0** | Offline Hash Lab | Static browser open (`index.html`) | 100% client-side pure JavaScript SHA-256 engine; verifies certificate bindings, displays recorded diffs, and computes badges with zero backend calls. |

---

## 3. Step-by-Step Evaluator Walkthrough

### Step 1: Launch the Playground
Run the local Tier L runner from the repository root:
```bash
make playground-local
```
Open `http://127.0.0.1:8000/dashboard/index.html` in your browser and click on **Tab 7: Playground (Live Lab)**.

### Step 2: Inspect Initial Certified Baseline
- **Observed State**: The top certificate pill displays green **`CERTIFIED`**.
- **Metadata**: Program hash matches `5f74f7762ee1f378...` (Certified High-Force v2 policy).
- **Editor Mode Badge**: Shows `CERTIFIED`.
- **Simulation Config Badge**: Shows `CERTIFIED CONFIG`.

### Step 3: Test Real-Time Certificate Invalidation
1. In the **Python Policy Source** editor, modify line 27:
   ```python
   # Change gripper close force from 300 to 250
   env.close_gripper(250)
   ```
2. **Observed Result**:
   - The Program Hash recalculates instantly in the browser.
   - The certificate badge transitions immediately to amber **`PLAYGROUND, NOT CERTIFIED`** with message: *"Program hash does not match certified record."*
   - Editor badge updates to `PLAYGROUND, NOT CERTIFIED`.
3. Click the **Certified High-Force** template button above the editor to restore the certified code. The badge instantly restores to green **`CERTIFIED`**.

### Step 4: Verify Hardware Clamp Refusal
1. In the **Simulation Presets & Budget** card, click the **Robot Hardware Preset** selector and choose:
   `Standard Gripper (100 N Clamp)`
2. **Observed Result**:
   - An alert banner appears: *"Hardware Preset Clamped: Grip force limit is active. Objects exceeding payload cannot be lifted by software modification alone."*
   - Simulation preset badge transitions to **`HARDWARE CLAMPED`**.
   - Certificate status transitions to `PLAYGROUND, NOT CERTIFIED`.
3. Switch back to **`Certified Default (Pass-through)`**.

### Step 5: Execute Live PyBullet Simulation
1. Set Budget to `5 Episodes (Quick Probe)`.
2. Click **Run Simulation**.
3. **Observed Result**:
   - The button shows `Simulating...` and progress bar advances in real time.
   - Metric cards update dynamically: Passed: 5, Tested: 5, Success Rate: 100.0%, Force Clamps: 0.
   - The **Camera View** renders the PyBullet simulated camera frame live upon episode completion.
   - The **Live Episode Trace Log** appends rows in real time containing per-episode seed, physical mass, friction coefficient, clearance margin, step count, and clamp diagnostics.

### Step 6: Test Repair & Acceptance Gates
1. Scroll to the **Repair & Acceptance Gates** section.
2. Click **Load Recorded Repair**:
   - The policy editor loads the repaired controller.
   - The unified patch diff displays:
     ```diff
     --- a/baseline_v1.py
     +++ b/repaired_v2.py
     @@ -8,3 +8,3 @@
     -    env.close_gripper(100)
     +    env.close_gripper(300)
     ```
   - Engineering rationale displays explanation of physical friction-to-weight ratio across full operating envelope.
3. Click **Run Acceptance Gates**:
   - Evaluates the candidate policy against the 4 acceptance stages.
   - **Stage I (Minimal CE)**: `PASS` (+0.0050 margin).
   - **Stage II (Severe CE)**: `PASS` (+0.0050 margin).
   - **Stage III (Regression Set)**: `PASS`.
   - **Stage IV (Falsifier Rerun)**: `PASS`.

---

## 4. Video Walkthrough Artifact

An interactive browser session recording demonstrating this complete evaluation walkthrough has been captured and preserved:
- **Recording File**: `playground_walkthrough_1793571022785.webp`
- **Resolution**: 1280x900 viewport
- **Demonstrated Flows**: Certificate binding verification, live AST mutation, hardware clamp banner activation, live PyBullet SSE episode execution, camera render updates, and 4-stage acceptance gate execution.
