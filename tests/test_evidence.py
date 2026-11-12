from numbertrace.core.evidence import (
    SOCIAL_WARNING,
    assess_risk,
    build_summary,
    canonical_url,
    dedupe_and_group,
    make_finding,
)
from numbertrace.core.phone import normalize
from numbertrace.models import ProviderState, ProviderStatus, ReputationReport


def f(url, title="t", snippet=""):
    return make_finding(title=title, url=url, snippet=snippet, provider="p", variant="v")


def test_canonical_url_strips_tracking_www_fragment_slash():
    a = canonical_url("https://www.Example.com/contact/?utm_source=x&b=2&a=1#top")
    b = canonical_url("http://example.com/contact?a=1&b=2&fbclid=zzz")
    assert a == b == "https://example.com/contact?a=1&b=2"


def test_dedupe_keeps_first_and_groups():
    items = [
        f("https://www.example.com/contact?utm_source=a", "Acme customer service"),
        f("https://example.com/contact/", "dup"),
        f("https://reddit.com/r/x/1", "post"),
        f("https://800notes.com/Phone.aspx/1", "listing"),
    ]
    groups, hidden = dedupe_and_group(items)
    assert hidden == 0
    assert sum(len(v) for v in groups.values()) == 3
    assert groups["public_business_reference"][0].title == "Acme customer service"
    assert len(groups["social_platform_public_mention"]) == 1
    assert len(groups["community_complaint"]) == 1


def test_people_search_and_excluded_domains_hidden():
    items = [
        f("https://www.spokeo.com/x"),
        f("https://truecaller.com/x"),
        f("https://blocked.example/x"),
        f("https://ok.example/x"),
    ]
    groups, hidden = dedupe_and_group(items, exclude_domains=["blocked.example"])
    assert hidden == 3
    assert [x.domain for v in groups.values() for x in v] == ["ok.example"]


def test_social_mentions_carry_ownership_warning_and_stay_unverified():
    x = f("https://www.facebook.com/somepage", "A page")
    assert x.category.value == "social_platform_public_mention"
    assert x.warning == SOCIAL_WARNING
    assert x.status == "public_reference_unverified"
    assert "owner" not in x.model_dump_json().lower().replace("does not establish who owns", "")


def _rep(source, count=1, synthetic=False):
    return ReputationReport(source=source, category="spam", summary="s", report_count=count, synthetic=synthetic)


def _empty_groups():
    return dedupe_and_group([])[0]


def test_insufficient_data_when_nothing_ran():
    n = normalize("+94771234567", None)
    r = assess_risk(n, _empty_groups(), [], [])
    assert r.level == "insufficient_data" and r.score == 0
    assert "does not mean a number is safe" in r.uncertainty


def test_single_complaint_is_never_elevated():
    n = normalize("+94771234567", None)
    r = assess_risk(n, _empty_groups(), [_rep("one", count=50)], [])
    assert r.level in ("low", "moderate")
    assert "not independently corroborated" in r.uncertainty


def test_score_equals_sum_of_visible_reasons():
    n = normalize("+94771234567", None)
    groups, _ = dedupe_and_group([f("https://800notes.com/a"), f("https://shouldianswer.com/b")])
    r = assess_risk(n, groups, [_rep("a", 3), _rep("b", 3)], [])
    assert r.score == max(0, min(100, sum(x.weight for x in r.reasons)))
    assert r.level == "elevated"
    assert all(x.detail for x in r.reasons)
    assert "not a person" not in r.level and "scammer" in r.disclaimer  # disclaimer forbids labelling


def test_invalid_format_is_a_reason():
    n = normalize("+94 12 345", None)
    r = assess_risk(n, _empty_groups(), [], [])
    assert any(x.factor == "format_anomaly" for x in r.reasons)


def test_synthetic_data_disclosed():
    n = normalize("+94771234567", None)
    r = assess_risk(n, _empty_groups(), [_rep("a", synthetic=True)], [])
    assert "SYNTHETIC" in r.uncertainty


def test_summary_conflicts_and_unknowns():
    n = normalize("+94771234567", None)
    groups, _ = dedupe_and_group([f("https://yelp.com/biz/x", "Biz"), f("https://800notes.com/x")])
    st = [ProviderStatus(name="brave_search", kind="web_search", state=ProviderState.TIMEOUT)]
    s = build_summary(n, groups, [], st, hidden=2)
    assert any("spoofing" in c for c in s.conflicts)
    assert any("brave_search" in u for u in s.unknown)
    assert any("hidden" in o for o in s.observed)
    assert any("official number" in x for x in s.next_steps)
