# Test results (actual runs)

Run on 2026-11-12 in a Linux x86_64 cloud container (not real Kali hardware).

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` | passed |
| `mypy` (strict) | no issues in 23 files |
| `pytest` on Python 3.12.3 | **128 passed**, coverage **92%** |
| `pytest` on Python 3.13 | **128 passed** |
| `scripts/install_kali.sh` (light) as a **non-root** user, Python 3.13 | installed into `.venv`; `doctor --offline` passed; `.env` created with mode 600 |
| API smoke test (`numbertrace serve --demo` + curl) | `/health`, `/api/v1/normalize`, `/api/v1/providers` OK; foreign Host header → 400 |
| UI smoke test (headless Chromium via Playwright) | investigation completes, provider status updates live, HTML report downloads, bulk input shows an error, no console errors, no horizontal scroll at 375 px; screenshots in `docs/screenshots/` |

## Not executed
- Real Kali hardware and ARM (aarch64) Chromebook. The CI workflow includes a `kalilinux/kali-rolling`
  container job and an `ubuntu-24.04-arm` runner, but they run only after you push to GitHub.
- Windows 11 / macOS: covered by the CI matrix, not run locally.
- Docker image build: the Docker daemon was unavailable in the build sandbox.
- Live Brave/Google API calls: never run in tests by design (all HTTP is mocked). Try them yourself with your own key.

## Raw output
```text
$ ruff check numbertrace tests
All checks passed!
$ ruff format --check numbertrace tests
33 files already formatted
$ mypy
Success: no issues found in 23 source files
$ pytest --cov=numbertrace --cov-report=term
tests/test_reports.py ..                                                 [ 82%]
tests/test_safe_http.py ......................                           [100%]
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.12.3-final-0 ________________
Name                                   Stmts   Miss  Cover
----------------------------------------------------------
numbertrace/__init__.py                    1      0   100%
numbertrace/__main__.py                    2      2     0%
numbertrace/api.py                       113      3    97%
numbertrace/cli.py                       210     32    85%
numbertrace/config.py                     65     10    85%
numbertrace/core/__init__.py               0      0   100%
numbertrace/core/evidence.py             129      3    98%
numbertrace/core/investigate.py          161     10    94%
numbertrace/core/phone.py                 83      3    96%
numbertrace/core/ratelimit.py             29      3    90%
numbertrace/doctor.py                     58     16    72%
numbertrace/history.py                    43      9    79%
numbertrace/models.py                    109      0   100%
numbertrace/net/__init__.py                0      0   100%
numbertrace/net/safe_http.py              82     11    87%
numbertrace/providers/__init__.py          0      0   100%
numbertrace/providers/base.py             28      0   100%
numbertrace/providers/reputation.py       51      5    90%
numbertrace/providers/search.py          106      4    96%
numbertrace/redact.py                     46      1    98%
numbertrace/reporting/__init__.py          3      0   100%
numbertrace/reporting/html_report.py      58      5    91%
numbertrace/reporting/json_report.py      21      0   100%
----------------------------------------------------------
TOTAL                                   1398    117    92%
======================= 128 passed in 133.39s (0:02:13) ========================
```
