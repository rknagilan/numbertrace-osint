import logging

from numbertrace.redact import RedactingFilter, configure_logging, mask_number, redact_text


def test_mask_number():
    assert mask_number("+94771234567") == "+94*******67"
    assert mask_number("077 123 4567") == "*** *** **67"
    assert mask_number("12") == "12"


def test_redact_text_masks_all_numbers():
    text = "lookup for +94 77 123 4567 and 0112345678 failed after 3 tries"
    out = redact_text(text)
    assert "123 4567" not in out and "0112345678" not in out
    assert "3 tries" in out


def test_logging_filter_redacts_message_and_args(caplog):
    logger = configure_logging(logging.DEBUG)
    with caplog.at_level(logging.DEBUG, logger="numbertrace"):
        logger.warning("number %s failed", "+94771234567")
        logging.getLogger("numbertrace.sub").warning("raw +94771234567")
    assert "771234567" not in caplog.text
    assert "+94*******67" in caplog.text


def test_filter_handles_dict_args():
    rec = logging.LogRecord("numbertrace", logging.INFO, __file__, 1, "%(n)s", None, None)
    rec.args = {"n": "+94771234567"}
    RedactingFilter().filter(rec)
    assert rec.getMessage() == "+94*******67"
