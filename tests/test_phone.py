import pytest

from numbertrace.core.phone import PhoneInputError, normalize


@pytest.mark.parametrize(
    "raw,region",
    [
        ("+94771234567", None),
        ("+94 77 123 4567", None),
        ("+94-77-123-4567", None),
        ("0771234567", "LK"),
        ("077 123 4567", "LK"),
        ("0094771234567", None),
        ("(077) 123-4567", "LK"),
    ],
)
def test_sri_lanka_mobile_formats(raw, region):
    n = normalize(raw, region)
    assert n.e164 == "+94771234567"
    assert n.country_code == 94
    assert n.is_valid
    assert n.metadata.region_code == "LK"
    assert n.metadata.line_type == "mobile"


def test_sri_lanka_colombo_landline():
    n = normalize("011 234 5678", "LK")
    assert n.e164 == "+94112345678"
    assert n.metadata.line_type == "fixed_line"
    assert "Colombo" in (n.metadata.region_description or "")


@pytest.mark.parametrize(
    "raw,e164,region_code",
    [
        ("+14155552671", "+14155552671", "US"),
        ("+44 20 7946 0958", "+442079460958", "GB"),
        ("+91 98765 43210", "+919876543210", "IN"),
        ("+61 2 9374 4000", "+61293744000", "AU"),
    ],
)
def test_international(raw, e164, region_code):
    n = normalize(raw, "LK")
    assert n.e164 == e164
    assert n.metadata.region_code == region_code


def test_national_number_uses_default_region_and_warns():
    n = normalize("0771234567", "LK")
    assert any("national number for region LK" in w for w in n.warnings)


def test_national_number_without_region_is_rejected():
    with pytest.raises(PhoneInputError, match="needs a country"):
        normalize("0771234567", None)


def test_same_digits_different_region_is_different_number():
    lk = normalize("0771234567", "LK")
    gb = normalize("07712345678", "GB")
    assert lk.country_code != gb.country_code


def test_shared_country_code_ambiguity_is_disclosed():
    n = normalize("+12425551234", None)  # +1 is shared (NANP); this is a Bahamas range
    assert any("shared by" in lim for lim in n.metadata.limitations)


def test_metadata_has_limitations_and_never_claims_location():
    n = normalize("+94771234567", None)
    joined = " ".join(n.metadata.limitations).lower()
    assert "ported" in joined and "gps" in joined


def test_invalid_but_parseable_number_is_flagged():
    n = normalize("+94 12 345", None)
    assert not n.is_valid
    assert n.metadata.confidence.value == "low"
    assert any("not valid" in w for w in n.warnings)


@pytest.mark.parametrize(
    "raw,msg",
    [
        ("", "enter a phone number"),
        ("   ", "enter a phone number"),
        ("abc", "unsupported characters"),
        ("+94771234567, +94771234568", "one number"),
        ("+94771234567\n+94771234568", "one number"),
        ("+94771234567;0771234567", "one number"),
        ("1" * 40, "too long"),
        ("12345678901234567890", "Too many digits"),
        ("94+771234567", "only allowed once"),
        ("12", "Too few digits"),
        ("<script>", "unsupported characters"),
    ],
)
def test_invalid_and_bulk_inputs(raw, msg):
    with pytest.raises(PhoneInputError) as exc:
        normalize(raw, "LK")
    assert msg.lower() in str(exc.value).lower()


def test_error_messages_never_echo_number():
    raw = "+94 77 123 4567 x"
    with pytest.raises(PhoneInputError) as exc:
        normalize(raw, "LK")
    assert "1234567" not in str(exc.value)


def test_variants_are_unique_and_capped():
    n = normalize("+94771234567", None, max_variants=3)
    assert len(n.variants) == 3
    assert len(set(n.variants)) == 3
    assert n.variants[0] == "+94771234567"


@pytest.mark.parametrize("bad", [0, 13, 100])
def test_excessive_variants_rejected(bad):
    with pytest.raises(PhoneInputError):
        normalize("+94771234567", None, max_variants=bad)


def test_input_is_masked_in_model():
    n = normalize("+94771234567", None)
    assert n.input_masked == "+94*******67"


def test_extra_trunk_zero_after_country_code_is_removed_with_warning():
    n = normalize("+940771234567", None)
    assert n.e164 == "+94771234567"
    assert any("extra '0'" in w for w in n.warnings)


def test_no_trunk_warning_for_normal_international_input():
    assert not any("extra '0'" in w for w in normalize("+94771234567", None).warnings)
