"""Pydantic data models shared by the CLI, API and reports."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NumberMetadata(BaseModel):
    region_code: str | None = None
    region_description: str | None = None
    carrier: str | None = Field(default=None, description="Original allocation carrier (may differ after porting).")
    line_type: str = "unknown"
    time_zones: list[str] = Field(default_factory=list)
    source: str = "phonenumbers (Google libphonenumber data, offline)"
    confidence: Confidence = Confidence.MEDIUM
    limitations: list[str] = Field(default_factory=list)


class NormalizedNumber(BaseModel):
    input_masked: str
    e164: str
    international: str
    national: str
    country_code: int
    is_possible: bool
    is_valid: bool
    metadata: NumberMetadata
    variants: list[str] = Field(description="Textual representations used for searching.")
    warnings: list[str] = Field(default_factory=list)


class EvidenceCategory(StrEnum):
    BUSINESS = "public_business_reference"
    COMPLAINT = "community_complaint"
    SOCIAL = "social_platform_public_mention"
    OTHER = "other_web_reference"


class Finding(BaseModel):
    title: str
    url: str
    snippet: str = ""
    domain: str
    provider: str
    search_variant: str
    retrieved_at: datetime = Field(default_factory=utcnow)
    category: EvidenceCategory = EvidenceCategory.OTHER
    status: str = "public_reference_unverified"
    warning: str | None = None


class ReputationReport(BaseModel):
    source: str
    category: str
    summary: str
    reported_at: str | None = None
    report_count: int = 1
    synthetic: bool = False
    license: str | None = None
    status: str = "unverified_allegation"


class ManualLink(BaseModel):
    engine: str
    query: str
    url: str


class ProviderState(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    NOT_CONFIGURED = "not_configured"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    ERROR = "error"
    CANCELLED = "cancelled"


class ProviderStatus(BaseModel):
    name: str
    kind: str
    state: ProviderState
    message: str = ""
    result_count: int = 0
    queries_used: int = 0
    duration_ms: int = 0


class ProviderInfo(BaseModel):
    name: str
    kind: str
    configured: bool
    requires: list[str]
    online: bool
    notes: str = ""


class RiskReason(BaseModel):
    factor: str
    weight: int
    detail: str


class RiskAssessment(BaseModel):
    level: str = Field(description="insufficient_data | low | moderate | elevated")
    score: int = Field(ge=0, le=100)
    reasons: list[RiskReason] = Field(default_factory=list)
    uncertainty: str
    disclaimer: str = (
        "This indicator describes signals about a NUMBER, not a person. It is not proof of "
        "fraud and must not be used to label anyone a criminal or scammer."
    )


class EvidenceSummary(BaseModel):
    observed: list[str]
    unknown: list[str]
    conflicts: list[str]
    next_steps: list[str]


class Investigation(BaseModel):
    tool_version: str
    generated_at: datetime = Field(default_factory=utcnow)
    mode: str = Field(description="offline | online | demo")
    number: NormalizedNumber
    providers: list[ProviderStatus] = Field(default_factory=list)
    findings: dict[str, list[Finding]] = Field(default_factory=dict)
    reputation: list[ReputationReport] = Field(default_factory=list)
    manual_links: list[ManualLink] = Field(default_factory=list)
    risk: RiskAssessment
    summary: EvidenceSummary
    notices: list[str] = Field(default_factory=list)
