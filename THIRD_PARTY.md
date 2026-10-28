# Third-party assets and dependencies

Permissive licences only (MIT, BSD, Apache-2.0, PSF). No copyrighted media.
Licences below verified against each package's PyPI metadata, not guessed.

| Asset | Licence | Source | Purpose in this repo |
|---|---|---|---|
| Python 3.11 (stdlib) | PSF | https://www.python.org/ | Project interpreter (AGENTS.md) |
| numpy 2.4.2 | BSD-3-Clause (plus bundled 0BSD/MIT/Zlib/CC0-1.0 parts, per its SPDX expression) | https://pypi.org/project/numpy/2.4.2/ | RNG + array math in `certify/stats.py` (ceiling simulation); scenario sampling later |
| scipy 1.17.1 | BSD-3-Clause (PyPI: OSI Approved BSD License; text in package) | https://pypi.org/project/scipy/1.17.1/ | Exact beta CIs (`scipy.stats.beta`) backing `cp_lower`/`cp_upper` |
| PyYAML 6.0.3 | MIT | https://pypi.org/project/PyYAML/6.0.3/ | Reading `configs/*.yaml` (error budget, run manifests) |
| pytest 9.2.0 (+ iniconfig, packaging, pluggy, pygments) | MIT / Apache-2.0-or-BSD-2-Clause / MIT / BSD-2-Clause | https://pypi.org/project/pytest/9.2.0/ | Test runner and its shipped dependencies |
| Meta Model API (`muse-spark-1.3`, SAM 3.1) — remote service, not vendored | Commercial API terms [VERIFY] | https://api.meta.ai/v1 | Code/repair generation, vision judge |

No URDF, mesh, texture, font, or dataset assets vendored yet (Phase 02 will add
PyBullet + robot models here with licence and URL).
