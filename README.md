# ClosedLoop: Falsify, Repair, Certify

**Built during the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026), Indie track, theme "Push the Frontier".** All code in this repository was written during the event. No prior code was reused.

ClosedLoop takes a robot program written by an LLM (Muse Spark, `muse-spark-1.3`,
via the Meta Model API at `https://api.meta.ai/v1`) and answers: how reliable is
it, really? It falsifies (searches for failing scenarios), repairs (from minimal
counterexamples), and certifies ("success probability at least p, with 95%
confidence, certified in simulation under distribution D").

Results, when present, are produced by `make report` from append-only logs and
are never typed by hand. To my knowledge, I did not find this exact combination
(falsifier-driven repair + certificate corrected for a rendered-footage judge)
elsewhere; see the plan for related work.

Code in this repo was written with AI-agent assistance (Muse Code, Muse Spark
1.3). Status: Phase 00 scaffolding; no experimental results yet.
