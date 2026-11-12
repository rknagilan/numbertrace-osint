import json

import pytest
from fastapi.testclient import TestClient

from numbertrace.api import create_app
from numbertrace.config import Settings


@pytest.fixture
def client():
    return TestClient(create_app(Settings(api_rate_limit_per_minute=50, provider_timeout=2)))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_providers(client):
    names = {p["name"] for p in client.get("/api/v1/providers").json()}
    assert {
        "brave_search",
        "google_cse_legacy",
        "local_community_dataset",
        "manual_search_links",
    } <= names


def test_normalize_ok(client):
    r = client.post("/api/v1/normalize", json={"number": "0771234567", "country": "LK"})
    assert r.status_code == 200 and r.json()["e164"] == "+94771234567"


def test_normalize_invalid_number_safe_error(client):
    r = client.post("/api/v1/normalize", json={"number": "abc+94771234567"})
    assert r.status_code == 422
    assert "771234567" not in r.text


@pytest.mark.parametrize("payload", [{"number": "+94771234567, +94771234568"}, {"number": "+94771234567\n0771234568"}])
def test_bulk_inputs_rejected(client, payload):
    assert client.post("/api/v1/investigate", json=payload).status_code == 422


def test_schema_validation(client):
    r = client.post("/api/v1/normalize", json={"number": "+94771234567", "country": "LKA"})
    assert r.status_code == 422 and r.json()["fields"] == ["country"]
    assert client.post("/api/v1/normalize", json={"number": "1" * 33}).status_code == 422


def test_oversized_payload(client):
    r = client.post(
        "/api/v1/investigate",
        content=json.dumps({"number": "1", "pad": "x" * 10_000}),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413


def test_investigate_no_key_mode(client):
    r = client.post("/api/v1/investigate", json={"number": "+94771234567"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "offline"
    assert {p["state"] for p in body["providers"]} == {"not_configured"}
    assert body["manual_links"]


def test_stream_ndjson(client):
    with client.stream("POST", "/api/v1/investigate/stream", json={"number": "+94771234567"}) as r:
        assert r.status_code == 200
        events = [json.loads(line) for line in r.iter_lines() if line]
    assert events[0]["type"] == "normalized" and events[-1]["type"] == "result"


def test_rate_limit():
    c = TestClient(create_app(Settings(api_rate_limit_per_minute=2)))
    codes = [c.post("/api/v1/normalize", json={"number": "+94771234567"}).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and codes[2:] == [429, 429]
    r = c.post("/api/v1/normalize", json={"number": "+94771234567"})
    assert int(r.headers["retry-after"]) >= 1


def test_untrusted_host_header_rejected(client):
    r = client.get("/health", headers={"host": "evil.example"})
    assert r.status_code == 400


def test_history_disabled_by_default(client):
    assert client.get("/api/v1/history").status_code == 404
    assert client.delete("/api/v1/history").json() == {"deleted": False}


def test_history_opt_in_and_delete(tmp_path):
    c = TestClient(create_app(Settings(history_enabled=True)))
    c.post("/api/v1/investigate", json={"number": "+94771234567"})
    entries = c.get("/api/v1/history").json()
    assert len(entries) == 1 and entries[0]["number_masked"] == "+94*******67"
    assert "771234567" not in json.dumps(entries)
    assert c.delete("/api/v1/history").json() == {"deleted": True}


def test_report_endpoints(client):
    inv = client.post("/api/v1/investigate", json={"number": "+94771234567"}).json()
    h = client.post("/api/v1/report/html", json=inv)
    assert h.status_code == 200 and "NumberTrace" in h.text and "attachment" in h.headers["content-disposition"]
    j = client.post("/api/v1/report/json", json=inv)
    assert j.json()["number"]["e164"] == "+94771234567"


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "NumberTrace" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_demo_mode_api():
    c = TestClient(create_app(Settings(demo=True)))
    body = c.post("/api/v1/investigate", json={"number": "+14155550100"}).json()
    assert body["mode"] == "demo" and body["notices"][0].startswith("DEMO MODE")


def test_report_endpoint_size_capped(client):
    r = client.post("/api/v1/report/html", content=b"x" * 600_000, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_chunked_oversized_body_rejected(client):
    def gen():
        yield b'{"number": "1", "pad": "' + b"x" * 8000 + b'"}'

    r = client.post("/api/v1/normalize", content=gen(), headers={"content-type": "application/json"})
    assert r.status_code == 413
