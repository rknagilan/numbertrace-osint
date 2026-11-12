# Architecture

```
            ┌──────────── numbertrace/cli.py (Typer+Rich) ────────────┐
 user ──►   │                                                         │
            └──── numbertrace/api.py (FastAPI) + web/static (UI) ─────┘
                                   │
                      core/investigate.py  Investigator (DI: providers, http)
                     ┌─────────────┼───────────────────────────────┐
              core/phone.py   providers/search.py          providers/reputation.py
              (phonenumbers,  Brave · GoogleCSE(legacy) ·  LocalDataset (JSON)
               variants)      Demo(synthetic) · manual links
                                   │
                          net/safe_http.py (HTTPS-only, allowlist, SSRF guard,
                                            timeouts, retries, concurrency cap)
                                   │
                    core/evidence.py: dedupe → categorise → risk → summary
                                   │
                    reporting/: HTML (escaped, printable) + JSON
```

## Flow
1. **Validate input**: one number, at most 32 characters, at most 17 digits, no lists, only allowed characters.
2. **Normalize** offline with `phonenumbers`: E.164, formats, validity, region, carrier, line type, variants (capped).
3. **Query plan**: exact quoted variants plus spam/business context queries, capped by `MAX_QUERIES`
   and split across the configured providers.
4. **Run providers concurrently**. Each has its own timeout. Errors and timeouts become a status,
   and partial results are kept.
5. **Evidence**: canonical-URL de-duplication; people-search and data-broker domains are hidden;
   each result is categorised as business / complaint / social mention / other; everything stays
   `public_reference_unverified`.
6. **Risk + summary**: weighted reasons, uncertainty text, observed / unknown / conflicts / next steps.
7. **Output**: CLI, JSON, HTML, or an NDJSON stream for the dashboard (progress and cancellation).

## Cancellation
The dashboard reads `POST /api/v1/investigate/stream` with an `AbortController`. When you click
Cancel, the connection closes, the server sees the disconnect, and the async generator cancels
the running provider tasks.
