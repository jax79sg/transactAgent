"""Pure-function tests for account identity normalization (WR-48), including a regression
table of the real bank names found in the live data on 2026-10-03 and property tests
(the project's PBT scope covers pure functions)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ingestion_worker.accounts.normalize import (
    bank_key,
    default_account_name,
    display_bank_name,
    normalize_identifier,
)

# The 15 raw values in the live database, and the key each should get. DBS / DBS-POSB / POSB
# and GXS Bank / MariBank deliberately stay separate: the user merges those once, and the
# account-key design makes the merge permanent.
_LIVE_BANK_NAMES = [
    ("CIMB BANK", "cimb"),
    ("CIMB Bank", "cimb"),
    ("DBS", "dbs"),
    ("DBS / POSB", "dbs posb"),
    ("GXS Bank", "gxs"),
    ("HSBC", "hsbc"),
    ("MariBank", "maribank"),
    ("Maybank", "maybank"),
    ("OCBC", "ocbc"),
    ("OCBC Bank", "ocbc"),
    ("POSB", "posb"),
    ("Trust", "trust"),
    ("Trust Bank", "trust"),
    ("Trust Bank Singapore Limited", "trust"),
    ("UOB", "uob"),
]


class TestBankKey:
    @pytest.mark.parametrize(("raw", "expected"), _LIVE_BANK_NAMES)
    def test_live_bank_names(self, raw, expected):
        assert bank_key(raw) == expected

    def test_the_fifteen_live_names_collapse_to_eleven_keys(self):
        assert len({bank_key(raw) for raw, _ in _LIVE_BANK_NAMES}) == 11

    def test_punctuation_and_case_are_ignored(self):
        assert bank_key("O.C.B.C. Bank, Ltd.") == "o c b c"
        assert bank_key("  oCbC   bank ") == "ocbc"

    def test_a_name_made_only_of_generic_words_is_kept_not_emptied(self):
        assert bank_key("Bank") == "bank"
        assert bank_key("Bank of Singapore Limited") == "of"  # generic tokens go, the rest stays

    def test_unrelated_banks_stay_distinct(self):
        assert bank_key("DBS") != bank_key("POSB") != bank_key("UOB")

    @given(st.text(min_size=1, max_size=60))
    def test_is_idempotent(self, raw):
        once = bank_key(raw)
        assert bank_key(once) == once

    @given(st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), min_size=1, max_size=40))
    def test_a_name_with_letters_or_digits_never_yields_an_empty_key(self, raw):
        assert bank_key(raw) != ""


class TestNormalizeIdentifier:
    def test_whitespace_and_hyphens_are_removed_and_nothing_else(self):
        assert normalize_identifier(" 501-123 456-001 ") == "501123456001"
        assert normalize_identifier("XXX-XXX-7890") == "XXXXXX7890"
        assert normalize_identifier("12*34") == "12*34"

    def test_unicode_dashes_are_removed_too(self):
        # U+2010 hyphen, U+2013 en dash, U+2212 minus sign -- built from code points so the source has no look-alikes
        raw = f"501{chr(0x2010)}123{chr(0x2013)}456{chr(0x2212)}001"
        assert normalize_identifier(raw) == "501123456001"

    def test_nothing_left_means_none(self):
        assert normalize_identifier(None) is None
        assert normalize_identifier("") is None
        assert normalize_identifier(" - - ") is None

    @given(st.text(max_size=40))
    def test_is_idempotent_and_leaves_no_whitespace_or_ascii_hyphen(self, raw):
        once = normalize_identifier(raw)
        assert normalize_identifier(once) == once
        if once is not None:
            assert not any(ch.isspace() or ch == "-" for ch in once)


class TestNames:
    def test_default_name_uses_the_last_four_characters(self):
        assert default_account_name("OCBC Bank", "501123456001") == "OCBC Bank 6001"

    def test_default_name_with_a_short_identifier_uses_all_of_it(self):
        assert default_account_name("DBS", "12") == "DBS 12"

    def test_default_name_without_an_identifier_is_just_the_bank(self):
        assert default_account_name("Trust Bank", None) == "Trust Bank"

    def test_display_bank_name_collapses_whitespace(self):
        assert display_bank_name("  Trust   Bank \n Singapore ") == "Trust Bank Singapore"
