# Providers

API availability was checked in November 2026. Re-check before relying on any provider.

| Provider | Status | Config | Terms |
|---|---|---|---|
| `brave_search` | Active, documented, key-based (free tier exists; check current pricing) | `NUMBERTRACE_BRAVE_API_KEY` | https://brave.com/search/api/ |
| `google_cse_legacy` | **Closed to new customers**; Google says it stops working on **2027-01-01** | `NUMBERTRACE_GOOGLE_CSE_KEY`, `NUMBERTRACE_GOOGLE_CSE_CX` | https://developers.google.com/custom-search/v1/overview |
| Bing Web Search | Retired by Microsoft (Aug 2025). **Not implemented.** | – | – |
| `local_community_dataset` | Your own JSON file, offline | `NUMBERTRACE_COMMUNITY_DATASET` | You are responsible for its source and licence |
| `demo_synthetic_search` | Only with `--demo`. Returns fake `example.*` results for `+1 415 555 0100/0123` | – | – |
| `manual_search_links` | Always available. Links only; nothing is fetched | – | – |

## Getting a Brave key
1. Create an account at https://api-dashboard.search.brave.com/ and pick a plan.
2. Copy the key into `.env`: `NUMBERTRACE_BRAVE_API_KEY=...`
3. Run `numbertrace providers`. It should show `brave_search  configured: yes`.

## Community dataset format
```json
{
  "dataset": "My reports",
  "synthetic": false,
  "license": "CC0-1.0",
  "reports": [
    {"e164": "+94XXXXXXXXX", "source": "my-own-notes", "category": "scam_attempt",
     "summary": "Asked for OTP", "reported_at": "2026-05-01", "report_count": 1}
  ]
}
```
Maximum size is 5 MB. Every report is shown as `unverified_allegation`. Only add data you are
allowed to use. Never add leaked or scraped data.

## Writing a new adapter
See [CONTRIBUTING.md](../CONTRIBUTING.md#rules-for-new-providers).
