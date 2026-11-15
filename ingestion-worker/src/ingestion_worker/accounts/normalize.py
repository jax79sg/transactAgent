"""Pure normalization for account identity (WR-48, Epic 13). No database, no network.

`bank_key` is what makes `OCBC` and `OCBC Bank` (or `Trust` and `Trust Bank Singapore
Limited`) the same bank for matching purposes. It is deliberately conservative: it
removes only generic corporate words, so `DBS`, `DBS / POSB`, and `POSB` stay distinct
keys (different brands a person may hold separately) and `GXS Bank` vs `MariBank` stays
distinct (a rename no rule can know) -- the user resolves those once with a merge, which
the account-key design makes permanent.
"""

import re

_GENERIC_BANK_TOKENS = frozenset({"bank", "limited", "ltd", "pte", "singapore", "sg"})
_PUNCTUATION = re.compile(r"[^\w\s]|_", re.UNICODE)
# ASCII hyphen plus the Unicode hyphens/dashes (U+2010..U+2015) and minus sign (U+2212) that
# statements and PDF text extraction produce -- built from code points so the source has no
# look-alike characters in it.
_DASHES = "-" + "".join(chr(code) for code in (*range(0x2010, 0x2016), 0x2212))
_HYPHENS_AND_SPACES = re.compile(rf"[\s{re.escape(_DASHES)}]+")


def bank_key(bank_name: str) -> str:
    """Case-fold; punctuation to spaces; drop the whole-word tokens bank, limited, ltd,
    pte, singapore, sg; collapse spaces. If nothing is left (the name was only generic
    words), keep the case-folded words rather than returning an empty key."""
    tokens = _PUNCTUATION.sub(" ", bank_name.casefold()).split()
    kept = [token for token in tokens if token not in _GENERIC_BANK_TOKENS]
    return " ".join(kept) or " ".join(tokens) or bank_name.casefold().strip()


def normalize_identifier(raw: str | None) -> str | None:
    """Remove whitespace and hyphens only; everything else (digits, letters, mask
    characters such as X or *) stays exactly as printed. None if nothing is left."""
    if raw is None:
        return None
    cleaned = _HYPHENS_AND_SPACES.sub("", raw)
    return cleaned or None


def display_bank_name(raw: str) -> str:
    """The bank name as first seen, trimmed and with internal whitespace collapsed."""
    return " ".join(raw.split())


def identifier_in_words(identifier: str) -> str:
    """"AlphaBoostPocket" -> "Alpha Boost Pocket", "SavingsPocket2" -> "Savings Pocket 2". Three plain substitutions, kept
    simple so migration 0022 can apply the very same ones in SQL to the names this fixed."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", identifier)
    spaced = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", spaced)
    return re.sub(r"([0-9])([A-Za-z])", r"\1 \2", spaced)


def identifier_is_a_name(identifier: str) -> bool:
    """True when the identifier is words, not an account number: it has lowercase letters and fewer than four digits.
    GXS prints a pocket's name where other banks print a number. A real number has digits, a mask ("411111****1234",
    "XXXXXXXX") has none of the lowercase letters a name has."""
    return any(c.islower() for c in identifier) and sum(c.isdigit() for c in identifier) < 4


def default_account_name(display_bank: str, identifier: str | None) -> str:
    """`<bank> <last 4 characters of the identifier>` for an account number, `<bank> <the name in words>` when the
    identifier is itself a name (issue #66: two GXS pockets were both "GXS Bank cket"), or just the bank when the
    statement printed no identifier. The full identifier is stored either way; the user can rename it."""
    if identifier:
        if identifier_is_a_name(identifier):
            return f"{display_bank} {identifier_in_words(identifier)}"
        return f"{display_bank} {identifier[-4:]}"
    return display_bank
