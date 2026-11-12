# HTTP API

Start the server: `numbertrace serve` (binds **127.0.0.1:8765**). Interactive docs: `http://127.0.0.1:8765/docs`.

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/health` | – | `{"status":"ok","version":"0.1.0"}` |
| GET | `/api/v1/providers` | – | Adapters, configured?, requirements |
| POST | `/api/v1/normalize` | `{"number": "...", "country": "LK"}` | Offline normalization |
| POST | `/api/v1/investigate` | `{"number": "...", "country": "LK", "online": true}` | Full investigation (JSON) |
| POST | `/api/v1/investigate/stream` | same | NDJSON events: `normalized`, `provider`, `result`, `error` |
| POST | `/api/v1/report/html` / `/json` | an Investigation | Returns a downloadable report |
| GET/DELETE | `/api/v1/history` | – | Only when `NUMBERTRACE_HISTORY=1`; DELETE always allowed |

Limits: 4 KB request body (512 KB for report export), `NUMBERTRACE_API_RATE_LIMIT_PER_MINUTE`
per client (HTTP 429 with `Retry-After`), Host header must be localhost.

Errors never echo the number:
```json
{"error": "invalid_number", "detail": "Only one number per investigation is allowed (no lists)."}
```

Example:
```bash
curl -s -X POST http://127.0.0.1:8765/api/v1/normalize -H 'content-type: application/json' -d '{"number":"0771234567","country":"LK"}'
```
