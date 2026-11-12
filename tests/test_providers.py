import asyncio
import json

import httpx

from numbertrace.config import Settings
from numbertrace.core.investigate import Investigator
from numbertrace.core.phone import normalize
from numbertrace.providers.base import RawHit, SearchProvider
from numbertrace.providers.reputation import LocalDatasetReputationProvider, bundled_sample_path
from numbertrace.providers.search import (
    BraveSearchProvider,
    GoogleCSEProvider,
    build_queries,
    manual_search_links,
)

BRAVE_OK = {
    "web": {
        "results": [
            {
                "title": "Acme <strong>customer service</strong>",
                "url": "https://acme.example/contact",
                "description": "Call <b>us</b>",
            },
            {"title": "bad", "url": "javascript:alert(1)", "description": "x"},
            "not-a-dict",
        ]
    }
}


def test_queries_bounded_and_quoted():
    s = Settings(max_queries=3, include_domains=["lk"], exclude_domains=["spam.example"])
    q = build_queries(normalize("+94771234567", None), s)
    assert len(q) == 3
    assert all('"' in query and "site:lk" in query and "-site:spam.example" in query for _, query in q)


def test_manual_links_are_encoded_and_offline():
    links = manual_search_links(normalize("+94771234567", None), Settings())
    assert links and all(link.url.startswith("https://") for link in links)
    assert all(" " not in link.url and '"' not in link.url for link in links)
    assert "%2B94771234567" in links[0].url


async def test_no_key_mode(settings):
    inv = await Investigator(settings).run("+94771234567")
    states = {p.name: p.state.value for p in inv.providers}
    assert states["brave_search"] == "not_configured"
    assert states["google_cse_legacy"] == "not_configured"
    assert states["local_community_dataset"] == "not_configured"
    assert inv.mode == "offline"
    assert inv.manual_links
    assert not any(inv.findings.values()) and not inv.reputation  # nothing fabricated


async def test_brave_parsing_and_header(settings, make_http):
    seen = {}

    def handler(req):
        seen["key"] = req.headers.get("X-Subscription-Token")
        seen["host"] = req.url.host
        return httpx.Response(200, json=BRAVE_OK)

    s = settings.model_copy(update={"max_queries": 1})
    inv = await Investigator(
        s,
        search_providers=[BraveSearchProvider("k123")],
        reputation_providers=[],
        http=make_http(handler),
    ).run("+94771234567")
    assert seen == {"key": "k123", "host": "api.search.brave.com"}
    found = [x for v in inv.findings.values() for x in v]
    assert len(found) == 1
    assert found[0].title == "Acme customer service" and found[0].snippet == "Call us"
    assert found[0].status == "public_reference_unverified"
    assert inv.mode == "online"


async def test_google_cse_parsing(settings, make_http):
    def handler(req):
        assert req.url.host == "www.googleapis.com"
        return httpx.Response(200, json={"items": [{"title": "T", "link": "https://x.example/a", "snippet": "S"}]})

    inv = await Investigator(
        settings.model_copy(update={"max_queries": 1}),
        search_providers=[GoogleCSEProvider("k", "cx")],
        reputation_providers=[],
        http=make_http(handler),
    ).run("+94771234567")
    assert inv.providers[0].state.value == "ok" and inv.providers[0].result_count == 1


async def test_malformed_provider_response(settings, make_http):
    inv = await Investigator(
        settings,
        search_providers=[BraveSearchProvider("k")],
        reputation_providers=[],
        http=make_http(lambda r: httpx.Response(200, json={"web": {"results": "oops"}})),
    ).run("+94771234567")
    st = inv.providers[0]
    assert st.state.value == "error" and "malformed" in st.message


async def test_non_json_response(settings, make_http):
    inv = await Investigator(
        settings,
        search_providers=[BraveSearchProvider("k")],
        reputation_providers=[],
        http=make_http(lambda r: httpx.Response(200, text="<html>")),
    ).run("+94771234567")
    assert inv.providers[0].state.value == "error"


async def test_auth_error_message_is_actionable_and_pii_free(settings, make_http):
    inv = await Investigator(
        settings,
        search_providers=[BraveSearchProvider("bad")],
        reputation_providers=[],
        http=make_http(lambda r: httpx.Response(401)),
    ).run("+94771234567")
    st = inv.providers[0]
    assert "API key" in st.message and "771234567" not in st.message


async def test_quota_error(settings, make_http):
    inv = await Investigator(
        settings,
        search_providers=[BraveSearchProvider("k")],
        reputation_providers=[],
        http=make_http(lambda r: httpx.Response(429), retries=0),
    ).run("+94771234567")
    assert "429" in inv.providers[0].message


class SlowProvider(SearchProvider):
    name = "slow"
    online = True

    def __init__(self):
        self.calls = 0

    def is_configured(self):
        return True

    async def search(self, query, http):
        self.calls += 1
        if self.calls == 1:
            return [RawHit("first", "https://first.example/a", "")]
        await asyncio.sleep(10)
        return []


async def test_timeout_keeps_partial_results(settings):
    s = settings.model_copy(update={"provider_timeout": 0.3})
    inv = await Investigator(s, search_providers=[SlowProvider()], reputation_providers=[]).run("+94771234567")
    st = inv.providers[0]
    assert st.state.value == "timeout" and "partial" in st.message
    assert st.result_count == 1
    assert [x.title for v in inv.findings.values() for x in v] == ["first"]


class BoomProvider(SlowProvider):
    name = "boom"

    async def search(self, query, http):
        raise RuntimeError("secret detail +94771234567")


async def test_one_failure_does_not_break_others(settings, make_http):
    good = BraveSearchProvider("k")
    inv = await Investigator(
        settings.model_copy(update={"max_queries": 2}),
        search_providers=[BoomProvider(), good],
        reputation_providers=[],
        http=make_http(lambda r: httpx.Response(200, json=BRAVE_OK)),
    ).run("+94771234567")
    states = {p.name: p for p in inv.providers}
    assert states["boom"].state.value == "error" and "771234567" not in states["boom"].message
    assert states["brave_search"].state.value == "ok"


async def test_offline_mode_skips_online_providers(settings):
    inv = await Investigator(settings, search_providers=[BraveSearchProvider("k")], reputation_providers=[]).run(
        "+94771234567", online=False
    )
    assert inv.providers[0].state.value == "skipped" and inv.providers[0].queries_used == 0


async def test_query_budget_split_between_providers(settings, make_http):
    count = {"n": 0}

    def handler(req):
        count["n"] += 1
        return httpx.Response(200, json={"web": {"results": []}, "items": []})

    s = settings.model_copy(update={"max_queries": 4})
    await Investigator(
        s,
        search_providers=[BraveSearchProvider("k"), GoogleCSEProvider("k", "c")],
        reputation_providers=[],
        http=make_http(handler),
    ).run("+94771234567")
    assert count["n"] == 4


async def test_local_dataset(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(
        json.dumps(
            {
                "synthetic": False,
                "license": "CC0-1.0",
                "reports": [
                    {
                        "e164": "+94771234567",
                        "source": "my-notes",
                        "category": "spam",
                        "summary": "x",
                        "report_count": "bad",
                    },
                    {"e164": "+94770000000", "source": "other"},
                ],
            }
        )
    )
    reports = await LocalDatasetReputationProvider(p).lookup(normalize("+94771234567", None), None)
    assert len(reports) == 1 and reports[0].report_count == 1 and not reports[0].synthetic
    assert reports[0].status == "unverified_allegation"


async def test_malformed_dataset_reports_error(tmp_path, settings):
    p = tmp_path / "d.json"
    p.write_text("{not json")
    inv = await Investigator(
        settings, search_providers=[], reputation_providers=[LocalDatasetReputationProvider(p)]
    ).run("+94771234567")
    assert inv.providers[0].state.value == "error" and "JSON" in inv.providers[0].message


async def test_bundled_sample_is_marked_synthetic():
    data = json.loads(bundled_sample_path().read_text())
    assert data["synthetic"] is True
    assert all(r["e164"].startswith("+1415555") for r in data["reports"])  # reserved fictional range


async def test_demo_results_all_synthetic():
    inv = await Investigator(Settings(demo=True)).run("+14155550100")
    assert inv.mode == "demo"
    items = [x for v in inv.findings.values() for x in v]
    assert items and all("SYNTHETIC" in x.title for x in items)
    assert all(x.domain.endswith(("example.com", "example.org", "example.net")) for x in items)
    assert inv.reputation and all(r.synthetic for r in inv.reputation)


async def test_demo_does_not_fabricate_for_other_numbers():
    inv = await Investigator(Settings(demo=True)).run("+94771234567")
    assert not any(inv.findings.values()) and not inv.reputation


async def test_stream_events_order(settings):
    events = [e async for e in Investigator(settings).stream("+94771234567")]
    assert events[0]["type"] == "normalized" and events[-1]["type"] == "result"
    assert any(e["type"] == "provider" for e in events)


async def test_stream_reports_input_error(settings):
    events = [e async for e in Investigator(settings).stream("not a number")]
    assert events[-1]["type"] == "error"
