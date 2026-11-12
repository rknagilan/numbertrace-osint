"""Self-contained, printable HTML report (no external assets, everything escaped)."""

from __future__ import annotations

from html import escape

from numbertrace.models import Investigation

CATEGORY_LABELS = {
    "public_business_reference": "Public business references",
    "community_complaint": "Community complaint mentions",
    "social_platform_public_mention": "Social-platform public mentions (ownership NOT established)",
    "other_web_reference": "Other indexed web references",
}

CSS = """
:root{--bg:#fff;--fg:#1b1f24;--muted:#57606a;--card:#f6f8fa;--border:#d0d7de;--warn:#9a6700;--bad:#cf222e;--ok:#1a7f37}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#9198a1;--card:#161b22;--border:#30363d;--warn:#d29922;--bad:#f85149;--ok:#3fb950}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px}
main{max-width:920px;margin:auto}h1{font-size:1.5rem}h2{font-size:1.15rem;margin-top:1.6rem;border-bottom:1px solid var(--border);padding-bottom:4px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin:10px 0}
.notice{border-left:4px solid var(--warn)}.muted{color:var(--muted)}.tag{display:inline-block;font-size:.75rem;border:1px solid var(--border);border-radius:99px;padding:0 8px;margin-right:4px}
table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:4px 8px;border-bottom:1px solid var(--border);vertical-align:top}
a{color:inherit;word-break:break-all}.lvl-elevated{color:var(--bad)}.lvl-moderate{color:var(--warn)}.lvl-low{color:var(--ok)}
@media print{body{padding:0}.card{break-inside:avoid}}
"""


def _safe_href(url: str) -> str:
    return escape(url, quote=True) if url.startswith(("https://", "http://")) else "#"


def _list(items: list[str]) -> str:
    if not items:
        return "<p class='muted'>None.</p>"
    return "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>"


def render_html(inv: Investigation) -> str:
    n = inv.number
    md = n.metadata
    e = escape
    parts: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<meta name='robots' content='noindex'>",
        f"<title>NumberTrace report</title><style>{CSS}</style></head><body><main>",
        "<h1>NumberTrace OSINT — caller investigation report</h1>",
        f"<p class='muted'>Generated {e(inv.generated_at.isoformat())} · tool v{e(inv.tool_version)}"
        f" · mode: <strong>{e(inv.mode)}</strong></p>",
    ]
    parts.append("<div class='card notice'><strong>Read this first</strong>" + _list(inv.notices) + "</div>")

    parts.append("<h2>Number metadata (offline)</h2><table>")
    rows = [
        ("E.164", n.e164),
        ("International", n.international),
        ("National", n.national),
        ("Valid", "yes" if n.is_valid else "no"),
        ("Possible", "yes" if n.is_possible else "no"),
        ("Region", f"{md.region_code or 'unknown'} {md.region_description or ''}".strip()),
        ("Original carrier", md.carrier or "unknown"),
        ("Line type", md.line_type),
        ("Time zones", ", ".join(md.time_zones) or "unknown"),
        ("Source", md.source),
        ("Confidence", md.confidence.value),
    ]
    parts += [f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows]
    parts.append("</table>")
    parts.append("<p class='muted'>Limitations:</p>" + _list(md.limitations + n.warnings))

    r = inv.risk
    parts.append("<h2>Risk indicator (about the number, not a person)</h2><div class='card'>")
    parts.append(f"<p>Level: <strong class='lvl-{e(r.level)}'>{e(r.level)}</strong> · score {r.score}/100</p>")
    if r.reasons:
        parts.append("<table><tr><th>Factor</th><th>Weight</th><th>Why</th></tr>")
        parts += [f"<tr><td>{e(x.factor)}</td><td>{x.weight:+d}</td><td>{e(x.detail)}</td></tr>" for x in r.reasons]
        parts.append("</table>")
    parts.append(f"<p><em>Uncertainty:</em> {e(r.uncertainty)}</p><p class='muted'>{e(r.disclaimer)}</p></div>")

    s = inv.summary
    parts.append("<h2>Evidence summary</h2>")
    for title, lines in (
        ("Observed", s.observed),
        ("Still unknown", s.unknown),
        ("Conflicting clues", s.conflicts),
        ("Suggested safe next steps", s.next_steps),
    ):
        parts.append(f"<h3>{e(title)}</h3>{_list(lines)}")

    parts.append(
        "<h2>Providers</h2><table><tr><th>Provider</th><th>Status</th><th>Results</th><th>Queries</th><th>Note</th></tr>"
    )
    parts += [
        f"<tr><td>{e(p.name)}</td><td>{e(p.state.value)}</td><td>{p.result_count}</td>"
        f"<td>{p.queries_used}</td><td>{e(p.message)}</td></tr>"
        for p in inv.providers
    ]
    parts.append("</table>")

    parts.append("<h2>Community reports</h2>")
    if not inv.reputation:
        parts.append("<p class='muted'>No matching reports in configured datasets.</p>")
    for rep in inv.reputation:
        syn = "<span class='tag'>SYNTHETIC</span>" if rep.synthetic else ""
        parts.append(
            f"<div class='card'>{syn}<span class='tag'>{e(rep.status)}</span><strong>{e(rep.category)}</strong>"
            f" — {e(rep.source)} ({rep.report_count} report(s), {e(rep.reported_at or 'date unknown')})"
            f"<br>{e(rep.summary)}</div>"
        )

    parts.append("<h2>Public web references</h2>")
    total = sum(len(v) for v in inv.findings.values())
    if total == 0:
        parts.append(
            "<p class='muted'>No web references collected (offline mode, no API key, or no results). "
            "Use the manual links below.</p>"
        )
    for cat, items in inv.findings.items():
        if not items:
            continue
        parts.append(f"<h3>{e(CATEGORY_LABELS.get(cat, cat))} ({len(items)})</h3>")
        for f in items:
            warn = f"<br><small class='muted'>⚠ {e(f.warning)}</small>" if f.warning else ""
            parts.append(
                f"<div class='card'><span class='tag'>{e(f.status)}</span>"
                f"<a href='{_safe_href(f.url)}' rel='noopener noreferrer nofollow'>{e(f.title)}</a>"
                f"<br><small>{e(f.url)}</small><br>{e(f.snippet)}"
                f"<br><small class='muted'>via {e(f.provider)} · variant {e(f.search_variant)} · "
                f"retrieved {e(f.retrieved_at.isoformat())}</small>{warn}</div>"
            )

    parts.append(
        "<h2>Manual search links</h2><p class='muted'>Open these yourself. NumberTrace did not fetch them.</p><ul>"
    )
    parts += [
        f"<li>{e(m.engine)}: <a href='{_safe_href(m.url)}' rel='noopener noreferrer nofollow'>{e(m.query)}</a></li>"
        for m in inv.manual_links
    ]
    parts.append(
        "</ul><p class='muted'>Tip: use your browser's Print → Save as PDF for a PDF copy.</p></main></body></html>"
    )
    return "".join(parts)
