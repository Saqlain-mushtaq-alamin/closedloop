# Phase 10e: Public Link (Static Hosting) + Verifiable Evidence in Repo

## 5-Line Plan
1. **Repository Evidence & Gitignore Tracking**: Update `.gitignore` to track `phases/`, `docs/`, and whitelisted run directories (`cert-full-01`, `cert-mint-03`, `judge-g2-03`, `shift-full-01`, `h2h3-full-03`, `h1-full-02`, `demo-sessions-01`, `cert2-full-01`, `round2-mint-01`, `.certification_ledger.json`), re-ignoring `traces/`, verifying no secrets and file size caps (<=20 MB per file, <=60 MB total).
2. **Independent Evidence Verification Tool**: Implement `scripts/verify_evidence.py` and `make verify-evidence` recomputing every certified bound and calibration bound from committed logs with independent SciPy exact binomial tests and asserting N/N match.
3. **Tests-First Site Crawler**: Add `scripts/check_site.py` and `tests/test_pages_site.py` asserting sub-path accessibility (`/<repo>/dashboard/`), HTTP 200, relative paths only, first-load <= 2 MB, total <= 25 MB, zero external hosts, provenance sha256 equality, and `.github/workflows/pages.yml` schema validity.
4. **Sub-Path Static Site Hardening**: Add `dashboard/.nojekyll`, `<noscript>` tag, image alt texts, visible "RECORDED / data generated from logs" badge across all views, and deterministic git commit timestamp/SHA in footer.
5. **Deployment Workflow & README Top Section**: Create `.github/workflows/pages.yml` with official GitHub Actions (checkout@v4, configure-pages@v5, upload-pages-artifact@v3, deploy-pages@v4) and add judge guide, live link placeholder, offline instructions, and tool disclosures to `README.md`.

---

## What Changed & Files Added
- `.gitignore`: Updated to track `phases/` and whitelisted evidence runs while keeping `planning/` ignored and re-ignoring `runs/**/traces/`.
- `docs/DECISIONS.md`: Logged Phase 10e pre-registration entry for static hosting, evidence tracking, and independent verification.
- `scripts/verify_evidence.py`: Independent SciPy exact Clopper-Pearson calculator recomputing 57 certified, calibration, and shift bounds directly from committed `episodes.jsonl` files.
- `Makefile`: Added `verify-evidence` target invoking `scripts/verify_evidence.py`.
- `scripts/check_site.py`: Local sub-path HTTP crawler simulating GitHub Pages at `http://127.0.0.1:<port>/<repo>/dashboard/`, asserting 423 relative URLs return HTTP 200, valid Content-Type, zero external hosts, and valid size bounds.
- `dashboard/.nojekyll`: Added to disable Jekyll processing on GitHub Pages.
- `dashboard/index.html`: Hardened for sub-path hosting with `<noscript>` message, descriptive image `alt` tags, prominent sticky `RECORDED / data generated from logs` badge, and footer git SHA / build timestamp placeholders.
- `dashboard/console.js`: Added deterministic population of footer metadata from `DATA.provenance` and commit history.
- `.github/workflows/pages.yml`: Production GitHub Actions workflow deploying `dashboard/` to GitHub Pages on push to `main` and manual trigger using official actions (`actions/checkout@v4`, `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`) with minimal permissions (`contents: read`, `pages: write`, `id-token: write`).
- `tests/test_pages_site.py`: 5 unit tests verifying sub-path crawler (`test_site_paths`), first-load size (`test_first_load_size`), zero external hosts (`test_no_external_hosts`), cryptographic provenance hash equality against raw disk files (`test_evidence_hash_manifest`), and workflow YAML schema/permissions (`test_workflow_valid`).
- `README.md`: Added top section with live demo link placeholder, 3-line judge quick guide, offline instructions, `make verify-evidence` command, and complete model/tool disclosures complying with Rule H14.

---

## Numbers Observed vs Expected Range
- **Newly Tracked Evidence Size**:
  - Whitelisted runs total: 7.17 MB (excluding `traces/`).
  - Total untracked evidence files scanned: 189 files, 7.29 MB total (well under 60 MB cap; max single file 2.92 MB, well under 20 MB cap).
  - Secret scan: 0 hits (`check_no_secrets.sh` clean).
- **Evidence Verification (`make verify-evidence`)**:
  - `57/57 match` (100% exact match across all headline, cell, camera-corrected, judge calibration, and shift bounds).
- **Static Hosting Performance**:
  - First-load payload (`index.html`, `console.js`, `data.js`, `repair_theatre_data.js`): 328.2 KB (limit <= 2 MB).
  - Total dashboard directory size: 1.10 MB (limit <= 25 MB).
  - Sub-path crawler: 423/423 URLs fetched with HTTP 200 through local ephemeral sub-path server.
- **Phase Spend**:
  - $0.00 (Zero LLM API calls needed; static deployment and evidence verification only).

---

## Gate Output (`make gate PHASE=10`)
```
no secrets found
closedloop/certify/stats.py: OK
tests/test_stats.py: OK
tests/test_coverage.py: OK
........................................................................ [ 47%]
........................................................................ [ 94%]
.......s                                                                 [100%]
151 passed, 1 skipped in 26.17s
.........                                                                [100%]
9 passed in 1.65s
PHASE 10 GATE VERIFIED: G3 FREEZE
Total Verified Precomputed Assets: 7
Source Runs Linked: ['cert-full-01', 'h2h3-full-03', 'judge-g2-03', 'shift-full-01']
PHASE 10: PASS (G3 FREEZE)
```

---

## Evidence Verification Output (`make verify-evidence`)
```
57/57 match
```

---

## HUMAN CHECKLIST (You cannot do these; perform before final submission)
1. **GitHub Repository Settings**: Go to **Settings** > **Pages** > **Build and deployment** > **Source**, and select **GitHub Actions**.
2. **Device & Browser Testing**: Open the deployed GitHub Pages URL in a private/incognito window on desktop AND on a phone using mobile data in Chrome and Firefox; verify DevTools shows zero failed requests.
3. **Feature Walkthrough**: Click every feature once (Heatmap, Inspector Probe, Replay Viewer, Repair Theatre scenario picker, Calibration panel, Shift scatter).
4. **External Verification**: Ask a colleague/friend on a different network to load the page.
5. **Deployment Headroom**: Deploy the final version to `main` at least 2 hours before the hackathon submission deadline (Pages caches static assets for a while).
6. **Submission Links**: Paste the deployed Pages URL into the README live link placeholder, the Devpost submission form, and the presentation video's closing end card.
7. **Backup Deployment**: (Optional) Deploy a mirror on Cloudflare Pages or Netlify, and attach a zip of `dashboard/` to the GitHub release tag.
