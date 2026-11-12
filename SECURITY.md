# Security Policy

## Reporting a vulnerability
Please **do not** open a public issue for security problems. Use GitHub's
"Report a vulnerability" (private security advisory) on this repository.
Include steps to reproduce, impact, and affected version. We aim to reply within 7 days.

## Scope
In scope: SSRF bypasses, XSS in the dashboard or HTML reports, leaking phone numbers into
logs, rate-limit/size-limit bypasses, API keys exposed in output, unsafe defaults
(e.g. binding to a public interface).

## Built-in protections
- Outbound HTTP: HTTPS only, per-provider host allowlist, DNS results must be public IPs,
  no redirects, literal IPs/credentials/odd ports rejected, short timeouts, at most 3 retries,
  a concurrency cap, and a response size cap.
- API: binds to 127.0.0.1 by default, Host-header allowlist (DNS-rebinding defence), 4 KB body
  limit, per-client rate limit, strict CSP, safe error bodies with no stack traces or numbers.
- Logs: phone-like digit runs are masked by a logging filter.
- Secrets live only in `.env` (git-ignored). `doctor` never prints key values.

## Known limitation
The DNS check and the connection are two separate steps, so a DNS-rebinding race is
theoretically possible. The host allowlist only contains fixed public API hosts, which
reduces this risk.
