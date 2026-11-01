# ClosedLoop Playground Feasibility Report (Phase PA0 Spike)

**Date**: 2026-11-01  
**Status**: COMPLETE (Gate D1 Recommendation Provided)  
**Authors**: Antigravity AI / ClosedLoop Team  

---

## 1. Executive Summary & Gate D1 Recommendation

- **Reproduction Benchmark**: **PASS (20/20 truth match, 20/20 margin match <= 1e-6, exact 0.00e+00 difference)** on 20 certified episodes from `runs/cert-full-01/episodes.jsonl`.
- **Simulation Throughput**:
  - **1 Worker**: **117.46 episodes / second** (Target: $\ge 3$ eps/sec).
  - **2 Workers**: **85.53 episodes / second** (Target: $\ge 3$ eps/sec).
- **Frame Render Latency (192x144)**: **6.93 ms average** (144.4 fps capacity, p95 = 7.24 ms).
- **Cloud Host Evaluation**:
  - **Owner Constraint**: Card issues; budget for hosting is at most \$0–\$10; cannot maintain pre-authorization holds or guaranteed credit card billing.
  - **Verification Finding**: **Zero cloud providers** provide $\ge 2$ vCPU continuous compute running from Nov 4 to Nov 10 without a valid credit card.
  - **D1 Decision**: **RECOMMEND FALLBACK LADDER: Ship Tier 0 (Hash Lab) + Tier L (Local Run) + Bundled Recorded Mode**.
  - **Tier L Delivery**: Delivered one-command local runner (`make playground-local` or `python -m playground.server`), clean `playground/requirements-linux.txt`, and production `playground/Dockerfile`.

---

## 2. Cloud Hosting Feasibility Matrix (Evaluated from Official Documentation)

All terms verified on 2026-11-01 from official platform documentation:

| Provider | Docker? | SSE (Unbuffered)? | Compute Provided | Card Required? | Free / Sleep Behavior | Feasible for Nov 4–10 with Card Issues? |
|---|---|---|---|---|---|---|
| **Hugging Face Spaces** | Yes | Yes | 2 vCPU, 16 GB | **YES** | Creating compute Docker spaces requires a paid plan (PRO \$9/mo) or CPU upgrade (\$0.03/hr). | **NO** (Requires card) |
| **Railway** | Yes | Yes (unbuffered, 15m timeout) | 2 vCPU, 1 GB | **NO (Trial)** / **YES (Past \$5)** | \$5 trial credit (30 days) runs out in ~3.0 days of continuous 2 vCPU compute (\$1.67/day). Hobby plan requires card. | **NO** (Exhausts before Nov 10) |
| **Render** | Yes | Yes | 0.1 vCPU, 512 MB | **NO (Free)** / **YES (Paid)** | Free tier auto-sleeps after 15 min inactivity; cold start ~1 min; only 0.1 vCPU (violates $\ge 2$ vCPU). Upgrades require card. | **NO** (Inadequate CPU + sleeps) |
| **Fly.io** | Yes | Yes | Shared CPU | **YES** | Free trial limited to 2 total VM hours. Running beyond trial requires active credit card with pre-auth hold. | **NO** (Requires card) |
| **Modal** | Yes | Yes | Serverless CPU | **YES** | Documentation explicitly states: *"You must have a payment method on file in order to use Modal"*. | **NO** (Requires card) |
| **Koyeb** | Yes | Yes | 0.1 vCPU, 512 MB | **YES** | Requires card with a **\$29 temporary pre-authorization hold**. Free tier auto-sleeps after 1 hr. | **NO** (Requires card + hold) |
| **Google Cloud Run** | Yes | Yes | Configurable | **YES** | Requires active Google Cloud Billing account linked to a valid credit/debit card. | **NO** (Requires card) |

### Host Feasibility Verdict
Because every cloud provider offering $\ge 2$ vCPU continuous compute requires an active payment card (or exhausts free credits within 3 days), **attempting a fragile public cloud deploy risks service suspension during the judging window (Nov 4–10)**.

In accordance with Section 12 and Section 15 of the Implementation Plan:
> *"If no host is verified and deployed by Nov 2, 12:00 Dhaka: NO-GO (D1). Ship Tier 0 + Tier L + recorded mode."*

---

## 3. Measured Simulator Benchmarks

Tested on CPython 3.11 with `pybullet==3.2.7`:

### 3.1 20-Episode Reproduction Check
Tested on certified start program `bec73dec45a88431` using scenarios and seeds directly from `runs/cert-full-01/episodes.jsonl`:
- **Episodes tested**: 20
- **Truth success matches**: **20 / 20 (100.0%)** (Gate requirement: 20/20)
- **Margin matches ($\le 10^{-6}$)**: **20 / 20 (100.0%)** (Gate requirement: $\ge$ 19/20)
- **Maximum margin discrepancy**: **0.00000000e+00** (Bit-for-bit identical)

### 3.2 Throughput
- **1 Worker**: 20 episodes completed in 0.170s $\rightarrow$ **117.46 episodes / second**
- **2 Workers**: 40 episodes completed in 0.468s $\rightarrow$ **85.53 episodes / second**
- Target from Plan §11: $\ge 3$ episodes/sec $\rightarrow$ **Exceeded by >28x**.

### 3.3 Frame Rendering Latency (192 x 144)
Camera configuration matching Gate G2 setup:
- **Average frame render time**: **6.93 ms**
- **p95 frame render time**: **7.24 ms**
- **Throughput capacity**: **144.4 frames per second**

---

## 4. Deliverables Created in PA0

1. **Clean Linux Requirements File**: `playground/requirements-linux.txt` (only pybullet 3.2.7, numpy, scipy, fastapi, uvicorn, pydantic, httpx; excludes unused packages).
2. **Docker Container Definition**: `playground/Dockerfile` (non-root `appuser`, headless pybullet, port 8000, zero hardcoded secrets).
3. **Local Runner Service**: `playground/server.py` (FastAPI app implementing `/health`, `/selftest`, and static dashboard hosting).
4. **Tier L Makefile Command**: `make playground-local` (one command runs the full playground server locally on port 8000).
5. **Automated Unit Tests**: `tests/test_playground_pa0.py` (5 tests verifying `/health`, `/selftest`, throughput $\ge 3$ eps/s, requirements cleanliness, and Dockerfile non-root security).
