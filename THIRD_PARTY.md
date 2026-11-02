# Third-Party Assets and Dependencies

Permissive licences only (MIT, BSD, Apache-2.0, PSF, zlib). No copyrighted media.
Licences verified against each package's PyPI metadata and distribution licence files.

## Python Dependencies (from `requirements.lock` and `playground/requirements-linux.txt`)

| Package / Asset | Version | Licence | Source URL | Purpose in Repository |
|---|---|---|---|---|
| Python (stdlib) | 3.11 | PSF-2.0 | https://www.python.org/ | Project execution runtime |
| alembic | 1.20.1 | MIT | https://pypi.org/project/alembic/1.20.1/ | Database migration dependency for Optuna |
| cmaes | 0.13.1 | MIT | https://pypi.org/project/cmaes/0.13.1/ | CMA-ES algorithm implementation for Optuna falsification |
| colorama | 0.4.6 | BSD-3-Clause | https://pypi.org/project/colorama/0.4.6/ | Cross-platform colored terminal text support |
| colorlog | 6.12.0 | MIT | https://pypi.org/project/colorlog/6.12.0/ | Formatted logging dependency for Optuna |
| fastapi | >=0.110.0 | MIT | https://pypi.org/project/fastapi/ | Interactive playground service API endpoint |
| httpx | >=0.27.0 | BSD-3-Clause | https://pypi.org/project/httpx/ | Async HTTP client for playground test fixtures |
| iniconfig | 2.3.1 | MIT | https://pypi.org/project/iniconfig/2.3.1/ | Pytest configuration parser |
| Mako | 1.4.3 | MIT | https://pypi.org/project/Mako/1.4.3/ | Templating dependency for Alembic |
| MarkupSafe | 3.0.4 | BSD-3-Clause | https://pypi.org/project/MarkupSafe/3.0.4/ | Fast string escape dependency for Mako |
| numpy | 2.4.2 | BSD-3-Clause | https://pypi.org/project/numpy/2.4.2/ | Numerical calculations, RNG streams, statistical arrays |
| optuna | 5.0.0 | MIT | https://pypi.org/project/optuna/5.0.0/ | Black-box parameter falsification search framework |
| packaging | 26.3 | Apache-2.0 or BSD-2-Clause | https://pypi.org/project/packaging/26.3/ | Core packaging utilities for pytest |
| pluggy | 1.7.0 | MIT | https://pypi.org/project/pluggy/1.7.0/ | Plugin manager for pytest |
| pybullet | 3.2.7 | zlib/libpng | https://pypi.org/project/pybullet/3.2.7/ | Physics simulation environment for task evaluation |
| pydantic | >=2.6.0 | MIT | https://pypi.org/project/pydantic/ | Request/response data validation in playground server |
| Pygments | 2.21.0 | BSD-2-Clause | https://pypi.org/project/Pygments/2.21.0/ | Syntax highlighter dependency for pytest |
| pytest | 9.2.0 | MIT | https://pypi.org/project/pytest/9.2.0/ | Test suite execution runner |
| pytest-asyncio | >=1.4.0 | Apache-2.0 | https://pypi.org/project/pytest-asyncio/ | Async test support plugin for playground endpoints |
| python-dotenv | >=1.0.0 | BSD-3-Clause | https://pypi.org/project/python-dotenv/ | Safe local environment variable loading |
| PyYAML | 6.0.3 | MIT | https://pypi.org/project/PyYAML/6.0.3/ | Configuration file parsing (`configs/*.yaml`) |
| scipy | 1.17.1 | BSD-3-Clause | https://pypi.org/project/scipy/1.17.1/ | Exact Clopper-Pearson beta distribution quantile bounds |
| SQLAlchemy | 2.1.6 | MIT | https://pypi.org/project/SQLAlchemy/2.1.6/ | Relational database abstraction for Optuna storage |
| sse-starlette | >=2.0.0 | BSD-3-Clause | https://pypi.org/project/sse-starlette/ | Server-Sent Events streaming in playground service |
| tqdm | 4.70.1 | MIT / MPL-2.0 | https://pypi.org/project/tqdm/4.70.1/ | Progress bar visualization for long-running routines |
| typing_extensions | 4.16.0 | PSF-2.0 | https://pypi.org/project/typing-extensions/4.16.0/ | Backported typing hints for Python standard library |
| uvicorn | >=0.28.0 | BSD-3-Clause | https://pypi.org/project/uvicorn/ | ASGI web server running local playground endpoints |

## Remote AI Provider APIs (Not Vendored)

| API Service | Provider | Terms / Licence | Purpose |
|---|---|---|---|
| Meta Model API (`muse-spark-1.3`, SAM 3.1) | Meta AI | Meta Model Terms / Developer Hackathon License | Policy code synthesis, targeted repair, visual segmentation |

## Asset Licensing & Simulation Geometry
- **No external URDFs, meshes, textures, or datasets are vendored.**
- All simulation objects (gripper fingers, payload cube, placement receptacle pad) are procedurally generated in PyBullet using standard primitive geometric shapes (`createCollisionShape`, `createMultiBody`).
- All 1,277 tracked frame images and diagnostic SVGs were synthesized and rendered directly by ClosedLoop simulation and dashboard tooling during the event. Zero copyrighted media is included.
