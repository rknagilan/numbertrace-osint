"""NumberTrace command-line interface (Typer + Rich)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape as esc
from rich.panel import Panel
from rich.table import Table

from numbertrace import __version__, history
from numbertrace.config import Settings, get_settings
from numbertrace.core.investigate import Investigator
from numbertrace.core.phone import PhoneInputError
from numbertrace.doctor import run_checks
from numbertrace.models import Investigation, NormalizedNumber
from numbertrace.providers.search import manual_search_links
from numbertrace.redact import configure_logging
from numbertrace.reporting import render_json, write_reports

app = typer.Typer(
    name="numbertrace",
    help=(
        "NumberTrace OSINT - investigate ONE unknown caller number using offline metadata, "
        "manual search links and (optionally) documented search APIs. Results are evidence, "
        "not identity. Run 'numbertrace doctor' first."
    ),
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
history_app = typer.Typer(help="Opt-in local history (OFF by default).", no_args_is_help=True)
app.add_typer(history_app, name="history")

STATE: dict[str, Any] = {"light": False}
NUMBER_OPT = typer.Option("--number", "-n", help="ONE phone number, e.g. '+94 77 123 4567'.")
COUNTRY_OPT = typer.Option("--country", "-c", help="Default region for national numbers (e.g. LK, IN, US).")


def console() -> Console:
    if STATE["light"]:
        return Console(no_color=True, highlight=False, emoji=False)
    return Console()


def err(message: str, hint: str = "") -> None:
    c = Console(stderr=True, no_color=STATE["light"])
    c.print(f"[bold red]Error:[/] {esc(message)}")
    if hint:
        c.print(f"[yellow]Hint:[/] {esc(hint)}")


def _settings(**overrides: Any) -> Settings:
    try:
        return get_settings(None, **overrides)
    except Exception as exc:  # pydantic validation of .env values
        err("Invalid configuration in .env or environment.", str(exc).splitlines()[0])
        raise typer.Exit(2) from exc


def _normalize_or_exit(inv: Investigator, number: str, country: str | None) -> NormalizedNumber:
    try:
        return inv.normalize(number, country)
    except PhoneInputError as exc:
        err(
            str(exc),
            "Example: numbertrace normalize '+94 77 123 4567'  or  --country LK 0771234567",
        )
        raise typer.Exit(2) from exc


def _print_number(n: NormalizedNumber) -> None:
    c = console()
    md = n.metadata
    t = Table(title="Number metadata (offline, from phonenumbers)", show_header=False)
    for k, v in (
        ("E.164", n.e164),
        ("International", n.international),
        ("National", n.national),
        (
            "Valid / Possible",
            f"{'yes' if n.is_valid else 'NO'} / {'yes' if n.is_possible else 'NO'}",
        ),
        ("Region", f"{md.region_code or 'unknown'} {md.region_description or ''}".strip()),
        ("Original carrier", md.carrier or "unknown"),
        ("Line type", md.line_type),
        ("Time zones", ", ".join(md.time_zones) or "unknown"),
        ("Confidence", md.confidence.value),
    ):
        t.add_row(esc(k), esc(v))
    c.print(t)
    c.print("[bold]Search variants:[/] " + esc(" | ".join(n.variants)))
    for w in n.warnings:
        c.print(f"[yellow]Warning:[/] {esc(w)}")
    for lim in md.limitations:
        c.print(f"[dim]Note: {esc(lim)}[/]")


def _print_investigation(inv: Investigation) -> None:
    c = console()
    for notice in inv.notices[:2]:
        c.print(f"[bold yellow]![/] {esc(notice)}")
    _print_number(inv.number)
    pt = Table(title="Providers")
    for col in ("Provider", "Status", "Results", "Queries", "Note"):
        pt.add_column(col)
    for p in inv.providers:
        pt.add_row(p.name, p.state.value, str(p.result_count), str(p.queries_used), esc(p.message))
    c.print(pt)
    r = inv.risk
    reasons = esc("\n".join(f"{x.weight:+d}  {x.factor}: {x.detail}" for x in r.reasons) or "No risk signals found.")
    c.print(
        Panel(
            f"Level: [bold]{r.level}[/] (score {r.score}/100)\n{reasons}\n\n[italic]{esc(r.uncertainty)}[/]\n"
            f"[dim]{esc(r.disclaimer)}[/]",
            title="Risk indicator (about the number, not a person)",
        )
    )
    for rep in inv.reputation:
        tag = "[SYNTHETIC] " if rep.synthetic else ""
        c.print(
            esc(f"- {tag}{rep.category} via {rep.source}: {rep.summary} ({rep.report_count} report(s), {rep.status})")
        )
    for cat, items in inv.findings.items():
        if items:
            c.print(f"\n[bold]{cat}[/] ({len(items)}) - public_reference_unverified")
            for f in items:
                c.print(esc(f"  - {f.title}\n    {f.url}"))
                if f.warning:
                    c.print(f"    [yellow]{esc(f.warning)}[/]")
    s = inv.summary
    for title, lines in (
        ("Observed", s.observed),
        ("Unknown", s.unknown),
        ("Conflicts", s.conflicts),
        ("Next steps", s.next_steps),
    ):
        if lines:
            c.print(f"\n[bold]{title}[/]")
            for i in lines:
                c.print(f"  - {esc(i)}")
    if not any(inv.findings.values()):
        c.print("\n[bold]Manual search links[/] (open yourself; nothing was fetched):")
        for m in inv.manual_links[:4]:
            c.print(esc(f"  {m.engine}: {m.url}"))


@app.callback()
def main_callback(
    light: Annotated[bool, typer.Option("--light", help="Plain output, no colours (low-resource terminals).")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show redacted debug logs.")] = False,
) -> None:
    STATE["light"] = light
    configure_logging(logging.DEBUG if verbose else logging.WARNING)


@app.command()
def version() -> None:
    """Show the version."""
    console().print(f"numbertrace {__version__}")


@app.command()
def normalize(
    number: Annotated[str, typer.Argument(help="ONE phone number, e.g. +94771234567")],
    country: Annotated[str | None, COUNTRY_OPT] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Validate and normalize a single number (offline)."""
    settings = _settings()
    n = _normalize_or_exit(Investigator(settings, search_providers=[], reputation_providers=[]), number, country)
    if as_json:
        typer.echo(n.model_dump_json(indent=2))
    else:
        _print_number(n)


@app.command()
def inspect(
    number: Annotated[str, NUMBER_OPT],
    country: Annotated[str | None, COUNTRY_OPT] = None,
    offline: Annotated[bool, typer.Option("--offline", help="Offline (always true for inspect).")] = True,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Offline metadata + manual search links. Never touches the network."""
    settings = _settings()
    n = _normalize_or_exit(Investigator(settings, search_providers=[], reputation_providers=[]), number, country)
    links = manual_search_links(n, settings)
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "number": n.model_dump(mode="json"),
                    "manual_links": [m.model_dump() for m in links],
                },
                indent=2,
            )
        )
        return
    _print_number(n)
    console().print("\n[bold]Manual search links[/] (offline mode - open them yourself):")
    for m in links:
        console().print(esc(f"  {m.engine}: {m.url}"))


def _default_report_name(ext: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("reports") / f"numbertrace-report-{stamp}.{ext}"


@app.command()
def search(
    number: Annotated[str, NUMBER_OPT],
    country: Annotated[str | None, COUNTRY_OPT] = None,
    offline: Annotated[bool, typer.Option("--offline", help="Do not call any online API.")] = False,
    demo: Annotated[bool, typer.Option("--demo", help="Use SYNTHETIC demo providers/data.")] = False,
    html_out: Annotated[Path | None, typer.Option("--html", help="Write an HTML report to this path.")] = None,
    json_out: Annotated[Path | None, typer.Option("--json-report", help="Write a JSON report to this path.")] = None,
    export: Annotated[bool, typer.Option("--export", help="Write HTML+JSON into ./reports/.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the investigation as JSON.")] = False,
) -> None:
    """Full single-number investigation (metadata, configured sources, manual links)."""
    settings = _settings(demo=demo or None)
    inv_engine = Investigator(settings)
    n = _normalize_or_exit(inv_engine, number, country)
    if not offline and not settings.has_live_search and not settings.demo:
        console().print(
            "[dim]No search API key configured: running without live web search (manual links will be shown).[/]"
        )
    try:
        if as_json or STATE["light"]:
            inv = asyncio.run(inv_engine.run(number, region=country, online=not offline, number=n))
        else:
            with console().status("Investigating (single number, bounded queries)..."):
                inv = asyncio.run(inv_engine.run(number, region=country, online=not offline, number=n))
    except KeyboardInterrupt:
        err("Cancelled by user.")
        raise typer.Exit(130) from None
    if as_json:
        typer.echo(render_json(inv))
    else:
        _print_investigation(inv)
    if export:
        html_out = html_out or _default_report_name("html")
        json_out = json_out or _default_report_name("json")
    for p in write_reports(inv, html_out, json_out):
        console().print(f"[green]Report written:[/] {esc(str(p))}")
    if settings.history_enabled:
        history.record(inv)


app.command(name="investigate", help="Alias of 'search'.")(search)


@app.command()
def demo() -> None:
    """Run a safe demo on a fictional number (+1 415 555 0100) with SYNTHETIC data."""
    search(
        number="+14155550100",
        country=None,
        offline=False,
        demo=True,
        html_out=None,
        json_out=None,
        export=False,
        as_json=False,
    )


@app.command()
def providers(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """List adapters, whether they are configured, and what they need."""
    infos = Investigator(_settings()).provider_info()
    if as_json:
        typer.echo(json.dumps([i.model_dump() for i in infos], indent=2))
        return
    t = Table(title="Providers")
    for col in ("Name", "Kind", "Configured", "Online", "Requires", "Notes"):
        t.add_column(col)
    for i in infos:
        t.add_row(
            i.name,
            i.kind,
            "yes" if i.configured else "no",
            "yes" if i.online else "no",
            esc(", ".join(i.requires) or "-"),
            esc(i.notes),
        )
    console().print(t)


@app.command()
def doctor(
    offline: Annotated[bool, typer.Option("--offline", help="Skip the DNS check.")] = False,
) -> None:
    """Check Python, venv, packages, network, API config and disk space."""
    checks = run_checks(_settings(), offline=offline)
    icons = {
        "ok": "[green]OK[/]",
        "warn": "[yellow]WARN[/]",
        "fail": "[red]FAIL[/]",
        "info": "[cyan]INFO[/]",
    }
    c = console()
    for ch in checks:
        c.print(f"{icons[ch.status]:>18}  {esc(ch.name)}: {esc(ch.detail)}")
        if ch.fix:
            c.print(f"{'':>8}fix -> {esc(ch.fix)}")
    failed = [ch for ch in checks if ch.status == "fail"]
    c.print(
        "\n[bold green]All required checks passed.[/]"
        if not failed
        else f"\n[bold red]{len(failed)} required check(s) failed.[/] See 'fix ->' lines above."
    )
    if failed:
        raise typer.Exit(1)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address. Default is localhost only.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port.")] = 8765,
    allow_remote: Annotated[
        bool,
        typer.Option("--allow-remote", help="Allow binding a non-local address (NOT recommended)."),
    ] = False,
    demo: Annotated[bool, typer.Option("--demo", help="Use SYNTHETIC demo providers/data.")] = False,
) -> None:
    """Start the optional local web dashboard (needs: pip install -e '.[web]')."""
    if host not in ("127.0.0.1", "localhost", "::1") and not allow_remote:
        err(
            "Refusing to bind a non-local address.",
            "Use the default 127.0.0.1, or add --allow-remote if you understand the risk.",
        )
        raise typer.Exit(2)
    try:
        import uvicorn

        from numbertrace.api import create_app
    except ImportError as exc:
        err("Web extra is not installed.", "Run: pip install -e '.[web]'   (inside your venv)")
        raise typer.Exit(1) from exc
    settings = _settings(demo=demo or None)
    console().print(f"Dashboard: http://{host}:{port}  (Ctrl+C to stop)")
    uvicorn.run(create_app(settings), host=host, port=port, log_level="warning", access_log=False)


@history_app.command("show")
def history_show() -> None:
    """Show masked local history entries (only if you enabled history)."""
    entries = history.load()
    if not entries:
        console().print("No history stored.")
    for e in entries:
        console().print(esc(f"{e.get('at')}  {e.get('number_masked')}  {e.get('mode')}  risk={e.get('risk_level')}"))


@history_app.command("clear")
def history_clear() -> None:
    """Delete all local history (one step, no confirmation needed)."""
    console().print("History deleted." if history.clear() else "No history file to delete.")


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        err("Cancelled by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
