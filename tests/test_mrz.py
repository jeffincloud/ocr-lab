"""MRZ post-processing tests.

Run from the repo root:
    ../.venv/bin/python -m pytest tests/test_mrz.py -v
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))

from app import ocr  # noqa: E402
from app.ocr import _merge_mrz, _yymmdd_to_iso  # noqa: E402
from app.schemas import PassportFields  # noqa: E402


# ICAO-valid sample MRZ from the TD3 spec — all check digits are correct.
VALID_MRZ_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
VALID_MRZ_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_valid_mrz_overrides_vlm_fields():
    vlm = PassportFields(
        surname="WRONG",
        given_names="WRONG",
        passport_number="WRONG",
        nationality="WRONG",
        date_of_birth="1900-01-01",
        sex="M",
        date_of_expiry="1900-01-01",
        date_of_issue="2010-01-01",       # not in MRZ — should be kept
        issuing_authority="SOME AUTH",    # not in MRZ — should be kept
        mrz_line1=VALID_MRZ_L1,
        mrz_line2=VALID_MRZ_L2,
    )
    out = _merge_mrz(vlm)
    assert out.passport_number == "L898902C3"
    assert out.nationality == "UTO"
    assert out.date_of_birth == "1974-08-12"
    assert out.sex == "F"
    assert out.date_of_expiry == "2012-04-15"
    # Fields not in MRZ must be untouched.
    assert out.date_of_issue == "2010-01-01"
    assert out.issuing_authority == "SOME AUTH"


def test_valid_mrz_does_not_overwrite_names():
    # TD3 check digits don't cover names: an MRZ that validates can still carry a
    # misread name, and must not replace what the model read from the printed page.
    vlm = PassportFields(surname="OKAFOR", given_names="CHIDI",
                         mrz_line1=VALID_MRZ_L1, mrz_line2=VALID_MRZ_L2)
    out = _merge_mrz(vlm)
    assert out.surname == "OKAFOR"
    assert out.given_names == "CHIDI"


def test_field_agreement_skips_nationality(monkeypatch):
    # The page prints COLOMBIA and the MRZ says COL. Counting that as a disagreement
    # would put a floor under the visual-agreement SLI's error rate on every passport.
    seen = []
    monkeypatch.setattr(ocr.tel.field_agreement, "add", lambda n, attrs: seen.append(attrs["field"]))
    _merge_mrz(PassportFields(nationality="UTOPIA", mrz_line1=VALID_MRZ_L1, mrz_line2=VALID_MRZ_L2))
    assert "nationality" not in seen
    assert "surname" in seen


def test_valid_mrz_fills_in_missing_names():
    out = _merge_mrz(PassportFields(mrz_line1=VALID_MRZ_L1, mrz_line2=VALID_MRZ_L2))
    assert out.surname == "ERIKSSON"
    assert out.given_names == "ANNA MARIA"


def test_bad_check_digits_falls_back_to_vlm():
    # Valid MRZ with the last composite check digit flipped (0 -> 9) so the
    # overall check digit fails; library must reject and we keep VLM values.
    bad_l2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<19"
    vlm = PassportFields(
        surname="SMITH",
        given_names="JANE",
        mrz_line1=VALID_MRZ_L1,
        mrz_line2=bad_l2,
    )
    out = _merge_mrz(vlm)
    assert out.surname == "SMITH"
    assert out.given_names == "JANE"


def test_missing_mrz_is_a_noop():
    vlm = PassportFields(surname="SMITH", given_names="JANE")
    out = _merge_mrz(vlm)
    assert out.surname == "SMITH"


def test_yymmdd_expansion():
    assert _yymmdd_to_iso("740812", "dob") == "1974-08-12"
    assert _yymmdd_to_iso("050101", "dob") == "2005-01-01"
    assert _yymmdd_to_iso("211010", "future") == "2021-10-10"
    assert _yymmdd_to_iso("", "dob") is None
    assert _yymmdd_to_iso("bad", "dob") is None
