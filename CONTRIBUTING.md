# Contributing

Thanks for helping! Beginners are welcome.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pre-commit install
```

## Checks (CI runs the same ones)
```bash
ruff check numbertrace tests && ruff format --check numbertrace tests
mypy
pytest --cov=numbertrace
```

## Rules for new providers
1. Use only a **documented API** whose terms allow this use. Link the terms in `docs/PROVIDERS.md`.
2. Subclass `SearchProvider` or `ReputationProvider` (`numbertrace/providers/base.py`).
3. Declare `allowed_hosts`, and make every HTTP call through `SafeHTTPClient`.
4. Keep the provider **off unless configured** (its key comes from `.env`).
5. Mock all HTTP in tests with `httpx.MockTransport`. CI must never call live services.
6. Results must stay `public_reference_unverified`. Never add identity or ownership claims.

## Never commit
Real people's phone numbers, API keys, `.env` files, or screenshots of real investigations.
Use `+1 415 555 01xx` (fictional) or `phonenumbers` example numbers in tests.
