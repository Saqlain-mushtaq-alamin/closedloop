#!/usr/bin/env python3
"""Print the median certifiable bound for given judge quality (G2 sizing).

Usage: ceiling.py [--a TPR] [--b FPR] [--n-succ N] [--n-fail N]
                  [--n-cell N] [--K cells] [--B buckets] [--p true-p]
Reads defaults matching the plan; reads delta from configs/base.yaml (H12).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from closedloop.certify.stats import ceiling  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=float, default=0.95)
    ap.add_argument("--b", type=float, default=0.02)
    ap.add_argument("--n-succ", type=int, default=300)
    ap.add_argument("--n-fail", type=int, default=300)
    ap.add_argument("--n-cell", type=int, default=150)
    ap.add_argument("--K", type=int, default=16)
    ap.add_argument("--B", type=int, default=4)
    ap.add_argument("--p", type=float, default=1.0)
    args = ap.parse_args()
    with open("configs/base.yaml") as f:
        delta = float(yaml.safe_load(f)["confidence_delta"])
    print(
        f"{ceiling(args.a, args.b, args.n_succ, args.n_fail, args.n_cell, args.K, delta, args.p, args.B)}"
    )


if __name__ == "__main__":
    main()
