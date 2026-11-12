import json

from typer.testing import CliRunner

from numbertrace.cli import app

runner = CliRunner()


def test_help():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0 and "doctor" in r.output and "inspect" in r.output


def test_normalize_json():
    r = runner.invoke(app, ["normalize", "+94771234567", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output)["e164"] == "+94771234567"


def test_normalize_national_with_country():
    r = runner.invoke(app, ["--light", "normalize", "0771234567", "--country", "LK"])
    assert r.exit_code == 0 and "+94771234567" in r.output


def test_invalid_number_human_error():
    r = runner.invoke(app, ["normalize", "hello"])
    assert r.exit_code == 2 and "Error" in r.output and "Traceback" not in r.output


def test_inspect_offline():
    r = runner.invoke(app, ["--light", "inspect", "--number", "+14155550100", "--offline"])
    assert r.exit_code == 0 and "duckduckgo.com" in r.output


def test_search_offline_exports(tmp_path):
    h, j = tmp_path / "r.html", tmp_path / "r.json"
    r = runner.invoke(
        app,
        [
            "--light",
            "search",
            "--number",
            "+94771234567",
            "--offline",
            "--html",
            str(h),
            "--json-report",
            str(j),
        ],
    )
    assert r.exit_code == 0, r.output
    data = json.loads(j.read_text())
    assert data["mode"] == "offline" and data["risk"]["level"] == "insufficient_data"
    assert "unverified" in h.read_text().lower()


def test_search_export_default_dir(tmp_path):
    r = runner.invoke(app, ["--light", "search", "-n", "+94771234567", "--offline", "--export"])
    assert r.exit_code == 0
    assert len(list((tmp_path / "reports").glob("numbertrace-report-*"))) == 2


def test_search_json_stdout():
    r = runner.invoke(app, ["search", "-n", "+94771234567", "--offline", "--json"])
    assert r.exit_code == 0 and json.loads(r.output)["number"]["country_code"] == 94


def test_demo():
    r = runner.invoke(app, ["--light", "demo"])
    assert r.exit_code == 0 and "SYNTHETIC" in r.output


def test_providers_json():
    r = runner.invoke(app, ["providers", "--json"])
    assert r.exit_code == 0 and any(p["name"] == "brave_search" for p in json.loads(r.output))


def test_doctor_offline():
    r = runner.invoke(app, ["--light", "doctor", "--offline"])
    assert "Python version" in r.output and "Free disk space" in r.output


def test_serve_refuses_public_bind():
    r = runner.invoke(app, ["serve", "--host", "0.0.0.0"])
    assert r.exit_code == 2 and "Refusing" in r.output


def test_bad_env_config_is_friendly(monkeypatch):
    monkeypatch.setenv("NUMBERTRACE_MAX_VARIANTS", "999")
    r = runner.invoke(app, ["normalize", "+94771234567"])
    assert r.exit_code == 2 and "Invalid configuration" in r.output


def test_history_opt_in_and_clear(monkeypatch):
    monkeypatch.setenv("NUMBERTRACE_HISTORY", "1")
    runner.invoke(app, ["search", "-n", "+94771234567", "--offline", "--json"])
    shown = runner.invoke(app, ["history", "show"])
    assert "+94*******67" in shown.output and "771234567" not in shown.output
    assert "deleted" in runner.invoke(app, ["history", "clear"]).output


def test_untrusted_text_cannot_inject_rich_markup(monkeypatch):
    from numbertrace.providers.base import RawHit
    from numbertrace.providers.search import DemoSearchProvider

    async def evil(self, query, http):
        return [
            RawHit("[bold red]FAKE VERIFIED OWNER[/] [link=https://evil.example]x[/link]", "https://a.example/x", "")
        ]

    monkeypatch.setattr(DemoSearchProvider, "search", evil)
    r = runner.invoke(app, ["--light", "search", "-n", "+14155550100", "--demo"])
    assert r.exit_code == 0
    assert "[bold red]FAKE VERIFIED OWNER[/]" in r.output  # printed literally, not interpreted


def test_doctor_hint_shows_extra_name(monkeypatch):
    import importlib.util as iu

    real = iu.find_spec
    monkeypatch.setattr(iu, "find_spec", lambda name, *a: None if name in ("fastapi", "uvicorn") else real(name, *a))
    r = runner.invoke(app, ["--light", "doctor", "--offline"])
    assert "pip install -e '.[web]'" in r.output


def test_help_shows_extras_literally():
    for args in (["--help"], ["serve", "--help"]):
        out = runner.invoke(app, args).output
        assert "'.[web]'" in out and "\\[web]" not in out
