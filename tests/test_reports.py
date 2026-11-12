from numbertrace.config import Settings
from numbertrace.core.investigate import Investigator
from numbertrace.models import EvidenceCategory, Finding
from numbertrace.reporting import render_html, render_json


async def test_html_escapes_untrusted_content():
    inv = await Investigator(Settings()).run("+94771234567")
    inv.findings[EvidenceCategory.OTHER.value] = [
        Finding(
            title="<script>alert(1)</script>",
            url="javascript:alert(1)",
            snippet="<img src=x onerror=1>",
            domain="x",
            provider="p",
            search_variant="v",
        ),
    ]
    out = render_html(inv)
    assert "<script>alert" not in out and "<img src=x" not in out
    assert "href='javascript" not in out
    assert "public_reference_unverified" in out


async def test_json_report_has_provenance_and_notice():
    inv = await Investigator(Settings(demo=True)).run("+14155550100")
    out = render_json(inv)
    assert "_report_notice" in out and "retrieved_at" in out and "search_variant" in out
