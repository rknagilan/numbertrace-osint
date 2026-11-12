# Manual smoke test on Kali (about 5 minutes)

Run each line. Tick it when the result matches.

| # | Command | Expected |
|---|---|---|
| 1 | `uname -m && python3 --version` | arch shown, Python ≥ 3.12 |
| 2 | `bash scripts/install_kali.sh --web` | ends with `==> Done.` |
| 3 | `source .venv/bin/activate && numbertrace doctor` | `All required checks passed.` |
| 4 | `numbertrace --help` | lists normalize, inspect, search, demo, doctor, serve |
| 5 | `numbertrace normalize 0771234567 --country LK` | E.164 `+94771234567`, LK, mobile |
| 6 | `numbertrace normalize 'abc'` | friendly `Error:` message, exit code 2, no traceback |
| 7 | `numbertrace normalize '+94771234567,+94771234568'` | `Only one number per investigation` |
| 8 | `numbertrace inspect --number '+14155550100' --offline` | metadata + manual links |
| 9 | `numbertrace demo` | `DEMO MODE`, SYNTHETIC labels, risk with reasons |
| 10 | `numbertrace search -n '+94771234567' --offline --export` | two files in `reports/` |
| 11 | `xdg-open reports/*.html` | report opens; "unverified" notices visible |
| 12 | `numbertrace serve --demo` then open http://127.0.0.1:8765 | dashboard; investigate `+14155550100`; Cancel works |
| 13 | `numbertrace serve --host 0.0.0.0` | refused |
| 14 | `NUMBERTRACE_HISTORY=1 numbertrace search -n '+94771234567' --offline` then `numbertrace history show` | masked `+94*******67` |
| 15 | `numbertrace history clear` | `History deleted.` |
| 16 | `pip install -e '.[dev]' && pytest` | all tests pass |
