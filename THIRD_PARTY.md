# Third-party assets and dependencies

Permissive licences only (MIT, BSD, Apache-2.0, PSF). No copyrighted media.
Licences below verified against each package's PyPI metadata, not guessed.

| Asset | Licence | Source | Purpose in this repo |
|---|---|---|---|
| Python 3.11 (stdlib) | PSF | https://www.python.org/ | Project interpreter (AGENTS.md) |
| numpy 2.4.2 | BSD-3-Clause (plus bundled 0BSD/MIT/Zlib/CC0-1.0 parts, per its SPDX expression) | https://pypi.org/project/numpy/2.4.2/ | RNG + array math in `certify/stats.py` (ceiling simulation); scenario sampling later |
| scipy 1.17.1 | BSD-3-Clause (PyPI: OSI Approved BSD License; text in package) | https://pypi.org/project/scipy/1.17.1/ | Exact beta CIs (`scipy.stats.beta`) backing `cp_lower`/`cp_upper` |
| PyYAML 6.0.3 | MIT | https://pypi.org/project/PyYAML/6.0.3/ | Reading `configs/*.yaml` (error budget, run manifests) |
| pybullet 3.2.7 | zlib/libpng | https://pypi.org/project/pybullet/3.2.7/ | Headless physics for T1 (Linux wheels cp36–cp311 only; Windows builds the sdist from source) |
| pytest 9.2.0 (+ iniconfig, packaging, pluggy, pygments) | MIT / Apache-2.0-or-BSD-2-Clause / MIT / BSD-2-Clause | https://pypi.org/project/pytest/9.2.0/ | Test runner and its shipped dependencies |
| Meta Model API (`muse-spark-1.3`, SAM 3.1) — remote service, not vendored | Commercial API terms [VERIFY] | https://api.meta.ai/v1 | Code/repair generation, vision judge |
| optuna 5.0.0 | MIT | https://pypi.org/project/optuna/5.0.0/ | Black-box optimization framework for falsification search |
| cmaes 0.13.1 | MIT | https://pypi.org/project/cmaes/0.13.1/ | CMA-ES sampler implementation for Optuna |
| alembic 1.20.1 | MIT | https://pypi.org/project/alembic/1.20.1/ | Optuna storage migration dependency |
| sqlalchemy 2.1.6 | MIT | https://pypi.org/project/SQLAlchemy/2.1.6/ | Optuna storage dependency |
| colorlog 6.12.0 | MIT | https://pypi.org/project/colorlog/6.12.0/ | Optuna logging dependency |
| tqdm 4.70.1 | MIT / MPL-2.0 | https://pypi.org/project/tqdm/4.70.1/ | Optuna progress bar dependency |
| Mako 1.4.3 | MIT | https://pypi.org/project/Mako/1.4.3/ | Alembic template dependency |
| MarkupSafe 3.0.4 | BSD-3-Clause | https://pypi.org/project/MarkupSafe/3.0.4/ | Mako dependency |
| typing-extensions 4.16.0 | PSF-2.0 | https://pypi.org/project/typing-extensions/4.16.0/ | Typing extensions dependency |

No URDF, mesh, texture, font, or dataset assets vendored yet (Phase 02 will add
PyBullet + robot models here with licence and URL).

