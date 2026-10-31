# Traceability — requirement → phase → test

Test names are the contract; phases write tests before code. `V#` = validity control (named test in that phase).

## Hypotheses (≥20 trajectories/arm/task; paired bootstrap 95% CI, 10k resamples)

| Req | Phase | Test / evidence |
|---|---|---|
| H1 generalization gap | P04 | `test_h1_gap_report` — B0 loop-scenario vs held-out success, gap + CI |
| H2 falsifier > random repair | P06 | `test_h2_paired_diff` — B2 vs B1 paired diff CI, equal budget (V6) |
| H3 frames help repair | P06 | `test_h3_paired_diff` — B3 vs B2 paired diff CI |
| H4 certificate refuses outside D | P09 | `test_h4_shift_refusal` — bound on D′ drops/refuses vs D |

## Hard rules AGENTS.md H1–H17

| Rule | Phase(s) | Test / check |
|---|---|---|
| H1 built in event, no history rewrite | P00, P12 | git log audit (P12 checklist); no force-push |
| H2 secrets | P00, all | `test_no_secrets` / `scripts/check_no_secrets.sh` (V13) |
| H3 licences/assets | P00, P12 | THIRD_PARTY.md completeness check (V13) |
| H4 Meta models only via client.py | P00, P03+ | `test_llm_client_only` — grep for other providers |
| H5 budget/CostMeter | P00, all | V14 `test_cost_meter_cap` |
| H6 locked files | P01, all | `scripts/check_locked.sh` in every gate |
| H7 tests sacred | all | gate fails if test files loosened (diff review P12) |
| H8 no fakes in experiment paths | P03+ | `test_no_fake_imports` — Fake* only under tests/ |
| H9 data separation | P02, P07, P08 | V4 leakage tests; cert seeds only in certify/ |
| H10 append-only JSONL | P03+ | `test_jsonl_append_only` |
| H11 numbers generated | P10–P12 | V12 regeneration check |
| H12 frozen plan | P04+ | V11 manifest hash test |
| H13 crash accounting | P03+ | V7 crash-count test |
| H14 wording | P11, P12 | V13 wording scan |
| H15 safe execution | P03 | `test_sandbox_*` (timeout/memory/no-network) |
| H16 scope/one phase | all | phase gate scope check (human review) |
| H17 no guessing | P00, P07 | API probes → docs/API_NOTES.md |

## Hackathon rules (all also → V13 scan in P12 unless noted)

| Rule | Phase | Check |
|---|---|---|
| Eligibility 18+, one track (Indie), team rep [VERIFY] | P00, P12 | human confirms in Official Rules; recorded P12 |
| IP owned; organisers' royalty-free licence; nothing confidential | P00, P12 | licence file + THIRD_PARTY.md (V13) |
| Submission: public repo, demo link no-login, contributors, built-during note [VERIFY fields] | P11, P12 | open submit page, draft form (P12) |
| Demo shows only in-event work | P11 | recording checklist |
| Meta models used; README model IDs + sample API log | P00, P11 | API_NOTES + README log excerpt |
| Billing: alerts don't stop billing → in-code cap mandatory | P00 | V14 |
| Judging weights Impact 30 / Tooling 25 / Demo 25 / Depth 20 [VERIFY] | P11 | confirm Official Rules (P12 human check) |
| Finals live Nov 9; stable precomputed version; opt. 45 s clip | P10, P12 | precomputed assets (P10) |
| Disclose AI-agent assistance + tools | P11 | README disclosure line (V13) |

## [LOCKED] decisions (plan §17; never change)

| Decision | Phase |
|---|---|
| Indie track, Push the Frontier | P00, P12 |
| PyBullet, Python, muse-spark-1.3, SAM 3.1 | P00, P02, P07 |
| Optuna/CMA-ES falsifier + shrinking step | P05 |
| Certification on fresh i.i.d. samples, separate streams | P02, P08 |
| Error-budget allocation §11 (K=16, B=4, M frozen pre-run) | P01, P08 |
| One hero task, 4×4 heatmap (mass×friction) | P02, P08 |
| Four-beat demo (re-timed 2:45 in P11) | P11 |
| Dropped: Muse Image, open-weights arm, separate conformal gate | all (absence checked P12) |

## [VERIFY] items — probe or human check

| Item | Where resolved |
|---|---|
| Model IDs, base URL, image input, per-call cost; Spark/SAM prices | P00 API probe → docs/API_NOTES.md |
| Corrected bound in literature? | P01 lit note (claim stays "derived for this project") |
| Commissioning $5–15k citation | P11 human check before use in README [VERIFY] |
| Video-frame vs image pricing; full heatmap $25–50 est. | P00 probe + P07 pilot metering |
| Rubric weights; eligibility; exact submit-form fields | P12 human opens Official Rules + submit page |
| Prediction-powered inference (future work) | P11 cite-or-drop check |
| Contributor model variants terms; Muse use | P12 human reads terms |
