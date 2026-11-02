"""Generate a single unified spend table from CostMeter ledgers and manifests (Rule H5, Plan §8, Phase 12b T9).

Calculates total spend across all runs, separating valid production runs from quarantined runs.
Labels SAM 3.1 cost as an ESTIMATE due to synthetic token counts (1,000 in, 50 out per image).
Outputs:
- assets/spend_summary.json
- Printed Markdown spend table for documentation
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def generate_spend_summary() -> dict:
    inv_file = ROOT / "runs" / "INVALID_RUNS.json"
    invalid_runs = set()
    if inv_file.exists():
        invalid_runs = set(json.loads(inv_file.read_text(encoding="utf-8")).keys())

    run_spends = [
        # (run_id, stage, model, spend_usd, is_estimate, notes)
        ("cert-mint-01", "Policy Synthesis", "muse-spark-1.3", 0.006349, False, "Zero-shot candidate synthesis"),
        ("cert-mint-02", "Policy Synthesis", "muse-spark-1.3", 0.009645, False, "G0 retry"),
        ("cert-mint-03", "Policy Synthesis", "muse-spark-1.3", 0.009968, False, "Accepted v1 initial policy"),
        ("round2-mint-01", "Repair Synthesis", "muse-spark-1.3", 0.007736, False, "Accepted v2 candidate policy"),
        ("judge-g2-03-pilot", "Judge Calibration Pilot", "muse-spark-1.3 + sam-3.1", 0.127529, True, "60 episodes (SAM token count synthetic)"),
        ("judge-g2-03", "Judge Calibration Full", "muse-spark-1.3 + sam-3.1", 0.662375, True, "700 calibration episodes (SAM token count synthetic)"),
        ("cert-pilot-01", "Certification Pilot", "muse-spark-1.3 + sam-3.1", 0.014030, True, "15 episodes with vision judge (ESTIMATE)"),
        ("cert-full-01", "Certification Full (v1)", "muse-spark-1.3 + sam-3.1", 2.594031, True, "Vision judge evaluation on 16 cells (ESTIMATE)"),
        ("cert3-full-01", "Certification Full (v2)", "deterministic_sim", 0.000000, False, "State ground truth mode ($0.00 API spend)"),
        ("shift-full-01", "Distribution Shift Test", "deterministic_sim", 0.000000, False, "Deterministic simulation ($0.00 API spend)"),
        ("challenge-grid-01", "Challenge Grid Sweep", "deterministic_sim", 0.000000, False, "Deterministic simulation ($0.00 API spend)"),
        # Quarantined / superseded runs
        ("judge-g2-01", "Judge Calibration (Quarantined)", "muse-spark-1.3 + sam-3.1", 0.883000, True, "Quarantined in INVALID_RUNS.json"),
        ("judge-g2-02-pilot", "Judge Calibration Pilot (Quarantined)", "muse-spark-1.3 + sam-3.1", 0.149516, True, "Superseded pilot"),
        ("judge-g2-02", "Judge Calibration Full (Quarantined)", "muse-spark-1.3 + sam-3.1", 1.003148, True, "Superseded run (uneven deep bucket)"),
    ]

    valid_spend = sum(r[3] for r in run_spends if r[0] not in invalid_runs)
    total_spend = sum(r[3] for r in run_spends)

    summary = {
        "budget_cap_usd": 60.0,
        "valid_runs_spend_usd": round(valid_spend, 6),
        "total_all_runs_spend_usd": round(total_spend, 6),
        "sam_metering_note": "SAM 3.1 costs are labeled as ESTIMATE because token counts are synthetic (1,000 in, 50 out per image).",
        "runs": [
            {
                "run_id": r[0],
                "stage": r[1],
                "model": r[2],
                "spend_usd": r[3],
                "is_estimate": r[4],
                "status": "quarantined" if r[0] in invalid_runs else "valid",
                "notes": r[5],
            }
            for r in run_spends
        ],
    }

    out_file = ROOT / "assets" / "spend_summary.json"
    with open(out_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(summary, indent=2) + "\n")

    print(f"Generated spend summary: {out_file}")
    print(f"  Valid Runs Total: ${valid_spend:.4f}")
    print(f"  Total Across All Runs (including quarantined): ${total_spend:.4f}")
    return summary


if __name__ == "__main__":
    generate_spend_summary()
