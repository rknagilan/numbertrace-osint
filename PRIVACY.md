# Privacy Policy

NumberTrace OSINT runs **on your computer**. There is no NumberTrace server, account or analytics.

| Data | What happens |
|---|---|
| The number you type | Processed in memory. **Not stored** by default. |
| Investigation results | Shown to you. Saved only when **you** export a report or enable history. |
| Local history (opt-in, `NUMBERTRACE_HISTORY=1`) | Stores only the **masked** number (e.g. `+94*******67`), time, mode and risk level, in `~/.local/share/numbertrace/history.jsonl` (mode 600). Delete it with `numbertrace history clear` or the dashboard button. |
| Logs | Phone-like numbers are masked before they are written. |
| Search APIs you configure (Brave, Google) | The number variants are sent to **that provider**, under that provider's privacy policy. Offline mode sends nothing. |
| Manual search links | Nothing is sent until **you** click a link. |

Exported reports contain the full number. Store and share them carefully.
