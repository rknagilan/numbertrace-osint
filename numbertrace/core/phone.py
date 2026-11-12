"""Local phone-number parsing and normalization using `phonenumbers`."""

from __future__ import annotations

import re

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType
from phonenumbers import carrier as pn_carrier
from phonenumbers import geocoder as pn_geocoder
from phonenumbers import timezone as pn_timezone

from numbertrace.config import HARD_MAX_VARIANTS
from numbertrace.models import Confidence, NormalizedNumber, NumberMetadata
from numbertrace.redact import mask_number

MAX_INPUT_LENGTH = 32
_ALLOWED_CHARS = re.compile(r"^[0-9+\-().\s/]+$")

PORTABILITY_NOTE = (
    "Carrier and region come from number-range allocation data. Numbers can be ported to "
    "another carrier, so this may be stale. It never indicates the caller's live/GPS location."
)

_LINE_TYPES: dict[int, str] = {
    PhoneNumberType.FIXED_LINE: "fixed_line",
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
    PhoneNumberType.TOLL_FREE: "toll_free",
    PhoneNumberType.PREMIUM_RATE: "premium_rate",
    PhoneNumberType.SHARED_COST: "shared_cost",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.PERSONAL_NUMBER: "personal_number",
    PhoneNumberType.PAGER: "pager",
    PhoneNumberType.UAN: "uan",
    PhoneNumberType.VOICEMAIL: "voicemail",
    PhoneNumberType.UNKNOWN: "unknown",
}


class PhoneInputError(ValueError):
    """User-facing input error. Messages never contain the submitted number."""


def _check_single_number(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise PhoneInputError("Please enter a phone number.")
    if len(text) > MAX_INPUT_LENGTH:
        raise PhoneInputError(f"Input is too long (max {MAX_INPUT_LENGTH} characters). Enter one number only.")
    if any(sep in text for sep in (",", ";", "\n", "|")):
        raise PhoneInputError("Only one number per investigation is allowed (no lists).")
    if not _ALLOWED_CHARS.match(text):
        raise PhoneInputError("Number contains unsupported characters. Use digits, spaces, +, -, ( ) only.")
    digits = sum(c.isdigit() for c in text)
    if digits > 17:
        raise PhoneInputError("Too many digits for a single phone number (max 17).")
    if digits < 3:
        raise PhoneInputError("Too few digits to be a phone number.")
    if text.count("+") > 1 or ("+" in text and not text.startswith("+")):
        raise PhoneInputError("A '+' is only allowed once, at the start of the number.")
    return text


def build_variants(num: phonenumbers.PhoneNumber, max_variants: int) -> list[str]:
    if max_variants < 1 or max_variants > HARD_MAX_VARIANTS:
        raise PhoneInputError(f"max_variants must be between 1 and {HARD_MAX_VARIANTS}.")
    e164 = phonenumbers.format_number(num, PhoneNumberFormat.E164)
    intl = phonenumbers.format_number(num, PhoneNumberFormat.INTERNATIONAL)
    national = phonenumbers.format_number(num, PhoneNumberFormat.NATIONAL)
    national_digits = re.sub(r"\D", "", national)
    candidates = [
        e164,
        intl,
        national,
        national_digits,
        intl.replace(" ", "-"),
        e164.lstrip("+"),
        re.sub(r"[\s-]", "", national),
        f"00{e164.lstrip('+')}",
    ]
    out: list[str] = []
    for c in candidates:
        c = c.strip()
        if c and c not in out:
            out.append(c)
    return out[:max_variants]


def normalize(raw: str, default_region: str | None = "LK", max_variants: int = 4) -> NormalizedNumber:
    """Parse and normalize ONE number entirely offline."""
    text = _check_single_number(raw)
    region = (default_region or "").upper() or None
    warnings: list[str] = []
    if not text.startswith("+") and not text.startswith("00") and region is None:
        raise PhoneInputError("National-format number needs a country. Add a +country code or choose a region.")
    if text.startswith("00"):
        text = "+" + text[2:]
    try:
        num = phonenumbers.parse(text, None if text.startswith("+") else region)
    except NumberParseException as exc:
        raise PhoneInputError("Could not parse that number. Check the digits and the country code.") from exc

    if text.startswith("+"):
        digits_after_cc = re.sub(r"\D", "", text)[len(str(num.country_code)) :]
        if digits_after_cc.startswith("0") and str(num.national_number) != digits_after_cc:
            warnings.append(
                f"Removed an extra '0' after +{num.country_code}. In international format the local "
                "trunk '0' is dropped (e.g. +94 077... becomes +94 77...)."
            )
    if not text.startswith("+"):
        warnings.append(
            f"Interpreted as a national number for region {region}. If the call came from "
            "abroad, re-enter it with its +country code."
        )

    country_code = int(num.country_code or 0)
    is_possible = phonenumbers.is_possible_number(num)
    is_valid = phonenumbers.is_valid_number(num)
    region_code = phonenumbers.region_code_for_number(num)
    ntype = phonenumbers.number_type(num)
    line_type = _LINE_TYPES.get(ntype, "unknown")
    carrier_name = pn_carrier.name_for_number(num, "en") or None
    region_desc = pn_geocoder.description_for_number(num, "en") or None
    tzs = [tz for tz in pn_timezone.time_zones_for_number(num) if tz != "Etc/Unknown"]

    limitations = [PORTABILITY_NOTE]
    if carrier_name is None:
        limitations.append("No carrier allocation data is available for this number.")
    if not is_valid:
        warnings.append(
            "The number is not valid according to the numbering plan (it may be spoofed, "
            "mistyped, or from a range not yet in the library data)."
        )
    elif not is_possible:
        warnings.append("Number length is not possible for this region.")

    regions_for_cc = phonenumbers.region_codes_for_country_code(country_code)
    if len(regions_for_cc) > 1:
        limitations.append(
            f"Country code +{num.country_code} is shared by {len(regions_for_cc)} regions; "
            f"region was inferred as {region_code or 'unknown'} from the number range."
        )

    confidence = Confidence.MEDIUM if is_valid else Confidence.LOW
    metadata = NumberMetadata(
        region_code=region_code if region_code not in (None, "ZZ") else None,
        region_description=region_desc,
        carrier=carrier_name,
        line_type=line_type,
        time_zones=tzs,
        confidence=confidence,
        limitations=limitations,
    )
    return NormalizedNumber(
        input_masked=mask_number(raw.strip()),
        e164=phonenumbers.format_number(num, PhoneNumberFormat.E164),
        international=phonenumbers.format_number(num, PhoneNumberFormat.INTERNATIONAL),
        national=phonenumbers.format_number(num, PhoneNumberFormat.NATIONAL),
        country_code=country_code,
        is_possible=is_possible,
        is_valid=is_valid,
        metadata=metadata,
        variants=build_variants(num, max_variants),
        warnings=warnings,
    )
