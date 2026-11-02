# UI Audit (Phase U0)

Audit date: Nov 2, 2026.
Audit target: `dashboard/index.html` (Gate G3 release).
Reviewer: Antigravity Pair Programmer.

## 1. Interactive Elements Inventory

| Location | Element ID | Type | Visible Label / Role | Current Functionality | Decision |
|---|---|---|---|---|---|
| Header | `theme-toggle` | button | Dark mode | Toggles light/dark theme | KEEP (Owner Decision D) |
| Header | `btn-recompute` | button | Recompute Live | Recomputes Clopper-Pearson bounds in browser | MOVE TO Evidence (Safe-zone map) |
| Header | `btn-download-cert` | button | Download ODD Certificate (JSON) | Downloads `data.json` / ODD cert | MOVE TO Overview & Evidence |
| Nav | n/a | buttons (8) | 0 to 7 tab buttons | Switches between 8 tabs | REPLACE with 4 top-level pages |
| Tab 0 (Stage 1) | `tt-btn-prog-v1` | button | Initial Controller | Switches code view | MOVE to Playground |
| Tab 0 (Stage 1) | `tt-btn-prog-v2` | button | Repaired Controller | Switches code view | MOVE to Playground |
| Tab 0 (Stage 1) | `tt-nominal-play-btn` | button | Play | Plays nominal filmstrip | MOVE to Evidence (Replays) |
| Tab 0 (Stage 1) | `tt-nominal-scrubber` | range | Scrubber | Scrubs nominal frames | MOVE to Evidence (Replays) |
| Tab 0 (Stage 2) | `tt-slots-bar` slots (5) | buttons (5) | Slot 1 to 5 | Selects manual test slot | KEEP in Evidence (Spot-checks) |
| Tab 0 (Stage 2) | `tt-slider-mass` | range | Mass (kg) slider | Adjusts scenario mass | KEEP in Evidence (Spot-checks) |
| Tab 0 (Stage 2) | `tt-slider-friction` | range | Friction slider | Adjusts scenario friction | KEEP in Evidence (Spot-checks) |
| Tab 0 (Stage 2) | `tt-select-pose` | select | Object Pose | Selects initial pose | KEEP in Evidence (Spot-checks) |
| Tab 0 (Stage 2) | `tt-btn-run-test` | button | Run Scenario Simulation | Runs spot test, updates slots | KEEP in Evidence (Spot-checks) |
| Tab 0 (Stage 3) | n/a | button | Open Repair Theatre → | Jumps to tab 3 | MOVE to Evidence (Replays) |
| Tab 0 (Stage 4) | n/a | button | View Certified Heatmap → | Jumps to tab 1 | MOVE to Evidence (Safe-zone map) |
| Tab 0 (Stage 5) | n/a | button | Explore Regional Probe → | Jumps to tab 1 | MOVE to Evidence (Safe-zone map) |
| Tab 0 (Stage 6) | n/a | buttons | Yes / No, Likert 1-5 | Feedback form buttons | REMOVE (Owner Decision A) |
| Tab 0 (Stage 6) | `tt-link-feedback` | a | Submit Feedback via GitHub | Opens issue / discussion | MOVE to footer link |
| Tab 1 | `btn-mode-state` | button | State Ground Truth | Switches heatmap mode | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `btn-mode-camera` | button | Camera Judge | Switches heatmap mode | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `btn-mode-v2` | button | Repaired (v2) | Switches heatmap to v2 | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `btn-mode-compare` | button | Compare v1 vs v2 | Comparison mode | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `target-p-slider` | range | Target Success (p*) | Adjusts certification target | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `delta-slider` | range | Confidence Error (δ) | Adjusts Clopper-Pearson δ | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `probe-mass-slider` | range | Mass slider | Selects mass in probe | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `probe-mass-input` | number | Mass number input | Direct mass input | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `probe-fric-slider` | range | Friction slider | Selects friction in probe | KEEP in Evidence (Safe-zone map) |
| Tab 1 | `probe-fric-input` | number | Friction number input | Direct friction input | KEEP in Evidence (Safe-zone map) |
| Tab 2 | `replay-clip-select` | select | Clip selector | Loads replay clip | KEEP in Evidence (Replays) |
| Tab 2 | `replay-play-btn` | button | Play ▸ | Plays replay video/frames | KEEP in Evidence (Replays) |
| Tab 2 | `replay-scrubber` | range | Scrubber | Scrubs frames | KEEP in Evidence (Replays) |
| Tab 3 | `theatre-play-btn` | button | Play ▸ | Plays repair animation | KEEP in Evidence (Replays) |
| Tab 3 | `theatre-scrubber` | range | Scrubber | Scrubs repair steps | KEEP in Evidence (Replays) |
| Tab 7 | template buttons (4) | buttons | Certified High-Force, etc. | Sets code template | KEEP in Playground |
| Tab 7 | `pg-code-editor` | textarea | Controller code | Edits controller python | KEEP in Playground |
| Tab 7 | `pg-robot-preset` | select | Robot Hardware Preset | Selects gripper preset | KEEP in Playground |
| Tab 7 | `pg-task-preset` | select | Task Operating Space | Selects weight range | KEEP in Playground |
| Tab 7 | `pg-budget-preset` | select | Budget | Selects episode budget | KEEP in Playground |
| Tab 7 | `pg-replay-cert` | checkbox | Replay certified | Certified scenario toggle | MOVE to Advanced in Playground |
| Tab 7 | `pg-run-btn` | button | Run Simulation | Runs live/recorded sim | KEEP in Playground |
| Tab 7 | `pg-load-repair-btn` | button | Load Recorded Repair | Loads Muse Spark repair | KEEP in Playground |
| Tab 7 | `pg-run-gates-btn` | button | Run Acceptance Gates | Runs 4 acceptance gates | KEEP in Playground |

## 2. Identified Technical and UX Defects
1. **Broken classes and undefined variables in Playground:** 16 classes undefined (`mb-24`, `uppercase`, `font-bold`, etc.) and 2 CSS vars (`--card-bg`, `--border-color`). *Resolved via `ui-fixes.css`*.
2. **Unreadable hardware warning in light mode:** `#pg-hardware-warning` had hardcoded `#fca5a5` on pale background. *Resolved via `ui-fixes.css`*.
3. **Information Overload:** 8 tabs, 14 badges in header/hero, paper-like headings ("Operational Envelope Probe & Certificate Controls").
4. **Duplication:** Tab 0 duplicated parts of Playground, Heatmap, and Theatre.
5. **No Dead Buttons:** All kept buttons have active event handlers in `console.js` and `playground.js`.

## 3. Approved Owner Decisions
- **Decision A:** Remove the "Your verdict" feedback form. Replace with a clean "Give feedback" link in the footer.
- **Decision B:** Remove the pooled 71.7% card from the Overview hero; display it as a caption on Evidence / Safe-zone map.
- **Decision C:** Keep template labels as "Certified High-Force", "Certified Grasp", "Initial Flawed", "Custom Policy" per owner preference.
- **Decision D:** Keep the Dark mode toggle at the far right of the header.
