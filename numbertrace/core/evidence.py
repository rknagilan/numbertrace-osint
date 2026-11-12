"""Evidence handling: URL de-duplication, categorisation, transparent risk and summary.

Design rules:
* Every web finding stays `public_reference_unverified`.
* A social-platform mention never implies account ownership.
* Risk describes signals about a number, never a verdict about a person.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from numbertrace.models import (
    EvidenceCategory,
    EvidenceSummary,
    Finding,
    NormalizedNumber,
    ProviderState,
    ProviderStatus,
    ReputationReport,
    RiskAssessment,
    RiskReason,
)

SOCIAL_DOMAINS = frozenset(
    {
        "facebook.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "linkedin.com",
        "tiktok.com",
        "youtube.com",
        "reddit.com",
        "t.me",
        "telegram.me",
        "pinterest.com",
        "threads.net",
        "vk.com",
        "example.net",
    }
)
COMPLAINT_DOMAINS = frozenset(
    {
        "800notes.com",
        "shouldianswer.com",
        "whocallsme.com",
        "tellows.com",
        "tellows.co.uk",
        "spamcalls.net",
        "callercenter.com",
        "forum.example.org",
    }
)
BUSINESS_DOMAINS = frozenset({"yellowpages.com", "yelp.com", "bbb.org", "yellow.lk", "example.com"})
# People-search / data-broker / contact-sync sites: results are hidden by policy.
BLOCKED_DOMAINS = frozenset(
    {
        "spokeo.com",
        "whitepages.com",
        "beenverified.com",
        "truepeoplesearch.com",
        "fastpeoplesearch.com",
        "intelius.com",
        "radaris.com",
        "peoplefinders.com",
        "mylife.com",
        "thatsthem.com",
        "truecaller.com",
        "sync.me",
        "getcontact.com",
        "eyecon-app.com",
        "nuwber.com",
        "instantcheckmate.com",
    }
)
COMPLAINT_WORDS = ("spam", "scam", "fraud", "complaint", "harass", "robocall", "who called")
BUSINESS_WORDS = ("contact us", "customer service", "hotline", "head office", "business", "company")

SOCIAL_WARNING = (
    "Public mention only. Appearing on a social platform does NOT establish who owns an "
    "account or who uses this number."
)
_TRACKING = ("utm_", "gclid", "fbclid", "mc_", "ref", "igshid", "si")


def registrable_domain(host: str) -> str:
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _matches(domain: str, pool: frozenset[str]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in pool)


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = registrable_domain(parts.hostname or "")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith(_TRACKING)]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def classify(domain: str, title: str, snippet: str) -> EvidenceCategory:
    if _matches(domain, SOCIAL_DOMAINS):
        return EvidenceCategory.SOCIAL
    text = f"{title} {snippet}".lower()
    if _matches(domain, COMPLAINT_DOMAINS) or any(w in text for w in COMPLAINT_WORDS):
        return EvidenceCategory.COMPLAINT
    if _matches(domain, BUSINESS_DOMAINS) or any(w in text for w in BUSINESS_WORDS):
        return EvidenceCategory.BUSINESS
    return EvidenceCategory.OTHER


def dedupe_and_group(
    findings: list[Finding], exclude_domains: list[str] | None = None
) -> tuple[dict[str, list[Finding]], int]:
    """De-duplicate by canonical URL and group by category.

    Returns (groups, hidden_count) where hidden_count counts results removed because they
    came from blocked people-search sites or user-excluded domains.
    """
    excluded = frozenset(d.lower() for d in (exclude_domains or []))
    seen: dict[str, Finding] = {}
    hidden = 0
    for f in findings:
        if _matches(f.domain, BLOCKED_DOMAINS) or _matches(f.domain, excluded):
            hidden += 1
            continue
        key = canonical_url(f.url)
        if key not in seen:
            seen[key] = f
    groups: dict[str, list[Finding]] = {c.value: [] for c in EvidenceCategory}
    for f in seen.values():
        groups[f.category.value].append(f)
    return groups, hidden


def make_finding(*, title: str, url: str, snippet: str, provider: str, variant: str) -> Finding:
    domain = registrable_domain(urlsplit(url).hostname or "")
    category = classify(domain, title, snippet)
    return Finding(
        title=title,
        url=url,
        snippet=snippet,
        domain=domain,
        provider=provider,
        search_variant=variant,
        category=category,
        warning=SOCIAL_WARNING if category is EvidenceCategory.SOCIAL else None,
    )


def assess_risk(
    number: NormalizedNumber,
    groups: dict[str, list[Finding]],
    reputation: list[ReputationReport],
    providers: list[ProviderStatus],
) -> RiskAssessment:
    reasons: list[RiskReason] = []
    if not number.is_valid:
        reasons.append(
            RiskReason(
                factor="format_anomaly",
                weight=15,
                detail="Number is not valid in the numbering plan; spoofed caller IDs often look like this.",
            )
        )
    elif not number.is_possible:
        reasons.append(RiskReason(factor="format_anomaly", weight=10, detail="Unusual length."))
    lt = number.metadata.line_type
    if lt == "premium_rate":
        reasons.append(
            RiskReason(
                factor="line_type",
                weight=15,
                detail="Premium-rate range: calling back may be charged at a high rate.",
            )
        )
    elif lt == "voip":
        reasons.append(
            RiskReason(
                factor="line_type",
                weight=5,
                detail="VoIP range: easy to obtain; also widely used by legitimate businesses.",
            )
        )

    sources = {r.source for r in reputation}
    total_reports = sum(r.report_count for r in reputation)
    if len(sources) == 1:
        reasons.append(
            RiskReason(
                factor="community_complaints",
                weight=15,
                detail="Complaints from a single source only - unverified, not corroborated.",
            )
        )
    elif len(sources) >= 2:
        reasons.append(
            RiskReason(
                factor="community_complaints",
                weight=35,
                detail=f"Complaints from {len(sources)} independent sources ({total_reports} reports).",
            )
        )
    if total_reports >= 5:
        reasons.append(
            RiskReason(
                factor="complaint_volume",
                weight=10,
                detail=f"{total_reports} reports in total.",
            )
        )

    complaint_domains = {f.domain for f in groups.get(EvidenceCategory.COMPLAINT.value, [])}
    if len(complaint_domains) == 1:
        reasons.append(
            RiskReason(
                factor="web_complaint_mentions",
                weight=10,
                detail="One website contains complaint-like text with this number (unverified).",
            )
        )
    elif len(complaint_domains) >= 2:
        reasons.append(
            RiskReason(
                factor="web_complaint_mentions",
                weight=20,
                detail=f"{len(complaint_domains)} websites contain complaint-like text (unverified).",
            )
        )
    if groups.get(EvidenceCategory.BUSINESS.value):
        reasons.append(
            RiskReason(
                factor="business_reference",
                weight=-10,
                detail="A public business page lists this number. Note: scammers can spoof real "
                "business numbers, so verify by calling the official number yourself.",
            )
        )

    score = max(0, min(100, sum(r.weight for r in reasons)))
    searched = any(p.state in (ProviderState.OK, ProviderState.EMPTY) and p.kind.startswith("web") for p in providers)
    any_evidence = bool(reputation) or any(groups.values())
    evidence_kinds = sum([bool(reputation), bool(complaint_domains)])

    if not any_evidence and not searched and number.is_valid and score == 0:
        level = "insufficient_data"
    elif score < 20:
        level = "low"
    elif score < 45 or evidence_kinds < 2:
        # Never "elevated" unless two independent kinds of evidence agree.
        level = "moderate"
    else:
        level = "elevated"

    synthetic = any(r.synthetic for r in reputation)
    uncertainty_parts = []
    if not searched:
        uncertainty_parts.append("No live web search was run (offline or no API key).")
    if not reputation:
        uncertainty_parts.append("No reputation dataset matched or none is configured.")
    if evidence_kinds < 2:
        uncertainty_parts.append("Signals are not independently corroborated.")
    if synthetic:
        uncertainty_parts.append("SYNTHETIC demo data was used; this result is not real.")
    uncertainty_parts.append("Absence of reports does not mean a number is safe.")
    return RiskAssessment(level=level, score=score, reasons=reasons, uncertainty=" ".join(uncertainty_parts))


def build_summary(
    number: NormalizedNumber,
    groups: dict[str, list[Finding]],
    reputation: list[ReputationReport],
    providers: list[ProviderStatus],
    hidden: int,
) -> EvidenceSummary:
    observed: list[str] = []
    unknown: list[str] = []
    conflicts: list[str] = []
    md = number.metadata
    observed.append(
        f"Number format is {'valid' if number.is_valid else 'NOT valid'} "
        f"(country code +{number.country_code}, line type: {md.line_type})."
    )
    if md.carrier:
        observed.append(f"Original carrier allocation: {md.carrier} (may be outdated due to porting).")
    for cat, items in groups.items():
        if items:
            observed.append(f"{len(items)} unverified public reference(s) of type '{cat}'.")
    if reputation:
        srcs = sorted({r.source for r in reputation})
        tag = " [SYNTHETIC]" if any(r.synthetic for r in reputation) else ""
        observed.append(f"{len(reputation)} community report(s) from: {', '.join(srcs)}{tag}.")
    if hidden:
        observed.append(f"{hidden} result(s) hidden from people-search/data-broker or excluded sites.")

    unknown.append("Who is actually calling: caller ID can be spoofed and numbers get reassigned.")
    unknown.append("The caller's real location (metadata is allocation data, not GPS).")
    failed = [p.name for p in providers if p.state in (ProviderState.ERROR, ProviderState.TIMEOUT)]
    if failed:
        unknown.append(f"Results from providers that failed or timed out: {', '.join(failed)}.")
    if not any(p.state in (ProviderState.OK, ProviderState.EMPTY) and p.kind.startswith("web") for p in providers):
        unknown.append("Live web references (use the manual search links, or configure an API key).")

    if groups.get(EvidenceCategory.BUSINESS.value) and (reputation or groups.get(EvidenceCategory.COMPLAINT.value)):
        conflicts.append(
            "Number appears on a business page AND in complaints. It may be a real business "
            "with unpopular calls, or scammers spoofing a real business number."
        )
    if groups.get(EvidenceCategory.SOCIAL.value):
        conflicts.append("Social-platform mentions do not show who owns or uses the number.")

    next_steps = [
        "Do not share OTPs, passwords, bank or card details with an unknown caller.",
        "If the caller claims to be a company or bank, hang up and call the official number "
        "printed on its website, card or bill.",
        "Block the number on your phone if calls are unwanted.",
        "Report scam calls to your mobile operator and your national authority "
        "(Sri Lanka: TRCSL / Sri Lanka CERT; USA: FTC at reportfraud.ftc.gov).",
    ]
    return EvidenceSummary(observed=observed, unknown=unknown, conflicts=conflicts, next_steps=next_steps)
