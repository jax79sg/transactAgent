"""The probable-duplicate matching rule (WR-58, WR-60, WR-64): pure, symmetric, no I/O.

Nothing here touches a database, the network, or the clock, so the same functions serve
the pipeline's check after extraction, the pair scan, `check-duplicates`, and the
backfill's dry run, and property-based tests can hammer them cheaply (NFR-PD-7).

Two details worth knowing before reading the code:

* **Exact arithmetic.** The threshold test compares `matched` with `ratio * smaller` in
  `Decimal`, never `float`: `0.7 * 10` is `7.000000000000001` in floating point, which
  would reject a statement that matches exactly 70% against a 0.70 threshold.
* **Symmetric on purpose.** `match_transactions(a, b)` and `match_transactions(b, a)`
  match the same *number* of transactions. Descriptions that are equal after
  normalization are interchangeable, so pairing them first cannot change the count; the
  fuzzy remainder is a *maximum* bipartite matching (a greedy best-first pairing would
  make the count depend on argument order when scores tie).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

# WR-58: a fixed constant, not a setting. The live statements showed no wording drift
# between two reads of the same PDF, so this is a narrow precaution, not a calibration.
SIMILARITY_FLOOR = 0.85
SNAPSHOT_LIMIT = 10  # FR-PD-5

ACCOUNT_NOT_APPLICABLE = "not_applicable"
ACCOUNT_SHARED = "shared"
ACCOUNT_CONFLICT = "conflict"

MARKER_ALSO_ON_OTHER = "also_on_other"
MARKER_ONLY_ON_THIS_ONE = "only_on_this_one"

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_FOUR_PLACES = Decimal("0.0001")


@dataclass(frozen=True)
class TxnKey:
    """One transaction as the matcher sees it. `amount` is the positive flow."""

    date: date
    amount: Decimal
    direction: str  # "out" | "in"
    currency: str
    description: str


@dataclass(frozen=True)
class AccountFact:
    """What one side knows about one of its accounts."""

    identifier: str
    currency: str
    closing_balance: Decimal | None = None
    closing_balance_date: date | None = None


@dataclass(frozen=True)
class StatementSide:
    """A held statement, or an extracted file about to be judged."""

    content_hash: str
    bank_key: str
    transactions: tuple[TxnKey, ...]
    accounts: tuple[AccountFact, ...] = ()
    bank_name: str | None = None
    file_name: str | None = None
    ingested_at: datetime | None = None

    @property
    def period(self) -> tuple[date, date] | None:
        if not self.transactions:
            return None
        dates = [t.date for t in self.transactions]
        return min(dates), max(dates)


@dataclass(frozen=True)
class DetectionSettings:
    enabled: bool
    match_ratio: Decimal
    min_transactions: int

    @classmethod
    def from_worker_settings(cls, worker_settings) -> "DetectionSettings":
        # str() first: Decimal(0.7) would carry the float's binary error into the threshold.
        return cls(
            enabled=worker_settings.duplicate_detection_enabled,
            match_ratio=Decimal(str(worker_settings.duplicate_match_ratio)),
            min_transactions=worker_settings.duplicate_min_transactions,
        )


@dataclass(frozen=True)
class Verdict:
    """The result of judging two statements. `a` and `b` are the arguments in the order given."""

    is_duplicate: bool
    matched_count: int
    count_a: int
    count_b: int
    ratio: Decimal  # matched / the smaller side, to 4 places; 0 when either side is empty
    sizes_comparable: bool
    small_gate_applied: bool
    account_rule: str
    banks_equal: bool
    periods_overlap: bool
    why_not: str | None  # set when is_duplicate is False: the reason, for near-miss reporting
    matched_pairs: tuple[tuple[int, int], ...]  # (index in a, index in b)

    @property
    def smaller_count(self) -> int:
        return min(self.count_a, self.count_b)

    @property
    def is_candidate(self) -> bool:
        """Same bank, overlapping period, and at least one shared transaction: worth showing
        as a near miss when it is not flagged."""
        return self.banks_equal and self.periods_overlap and self.matched_count >= 1


@dataclass(frozen=True)
class SnapshotRow:
    rank: int  # 1 = the largest amount
    date: date
    description: str
    amount: Decimal
    direction: str
    currency: str
    marker: str


@dataclass(frozen=True)
class CopyFacts:
    content_hash: str
    manual_corrections: int
    ingested_at: datetime


def normalize_description(description: str) -> str:
    """Case-fold and collapse whitespace. Reference codes are deliberately NOT stripped
    (unlike the similarity matcher's WR-20): two same-day, same-amount purchases that differ
    only by a reference must stay distinct."""
    return " ".join(description.casefold().split())


def _group_key(txn: TxnKey) -> tuple:
    return (txn.date, txn.amount, txn.direction, txn.currency)


def _max_bipartite_matching(adjacency: dict[int, list[int]]) -> list[tuple[int, int]]:
    """Kuhn's augmenting-path maximum matching. Groups here are tiny (the transactions that
    share a date, amount, direction and currency), so simplicity beats speed."""
    match_of_right: dict[int, int] = {}

    def try_augment(left: int, seen: set[int]) -> bool:
        for right in adjacency.get(left, []):
            if right in seen:
                continue
            seen.add(right)
            if right not in match_of_right or try_augment(match_of_right[right], seen):
                match_of_right[right] = left
                return True
        return False

    for left in sorted(adjacency):
        try_augment(left, set())
    return sorted((left, right) for right, left in match_of_right.items())


def _pair_group(a: Sequence[TxnKey], b: Sequence[TxnKey], ia: list[int], ib: list[int]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    # Stage 1: descriptions equal after normalization. They are interchangeable, so which
    # copy pairs with which cannot change the count.
    available_b: dict[str, list[int]] = defaultdict(list)
    for j in ib:
        available_b[normalize_description(b[j].description)].append(j)
    leftover_a: list[int] = []
    for i in ia:
        candidates = available_b.get(normalize_description(a[i].description))
        if candidates:
            pairs.append((i, candidates.pop(0)))
        else:
            leftover_a.append(i)
    leftover_b = sorted(j for remaining in available_b.values() for j in remaining)
    if not leftover_a or not leftover_b:
        return pairs
    # Stage 2: the remainder, by similarity, as a maximum matching over the edges at or
    # above the floor (so the count does not depend on which argument comes first).
    adjacency: dict[int, list[int]] = {}
    for i in leftover_a:
        scored = []
        for j in leftover_b:
            score = SequenceMatcher(None, normalize_description(a[i].description), normalize_description(b[j].description)).ratio()
            if score >= SIMILARITY_FLOOR:
                scored.append((-score, j))
        if scored:
            adjacency[i] = [j for _score, j in sorted(scored)]
    pairs.extend(_max_bipartite_matching(adjacency))
    return pairs


def match_transactions(a: Sequence[TxnKey], b: Sequence[TxnKey]) -> list[tuple[int, int]]:
    """One-to-one: each transaction on one side matches at most one on the other. A match
    needs the same date, amount, direction and currency and a description that is equal
    after normalization or at least SIMILARITY_FLOOR similar. Returns (index in a, index in
    b) pairs, sorted."""
    groups_a: dict[tuple, list[int]] = defaultdict(list)
    groups_b: dict[tuple, list[int]] = defaultdict(list)
    for index, txn in enumerate(a):
        groups_a[_group_key(txn)].append(index)
    for index, txn in enumerate(b):
        groups_b[_group_key(txn)].append(index)
    pairs: list[tuple[int, int]] = []
    for key in sorted(set(groups_a) & set(groups_b)):
        pairs.extend(_pair_group(a, b, groups_a[key], groups_b[key]))
    return sorted(pairs)


def match_ratio(matched: int, count_a: int, count_b: int) -> Decimal:
    """matched / the smaller side, to four places (the database column's precision); 0 when
    either side is empty. Used for display and storage. The decision itself is made on the
    exact comparison in `_meets_ratio`, not on this rounded value."""
    smaller = min(count_a, count_b)
    if smaller == 0:
        return Decimal("0.0000")
    return (Decimal(matched) / Decimal(smaller)).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


def _meets_ratio(matched: int, count_a: int, count_b: int, ratio: Decimal) -> bool:
    smaller = min(count_a, count_b)
    return smaller > 0 and Decimal(matched) >= ratio * Decimal(smaller)


def periods_overlap(p: tuple[date, date] | None, q: tuple[date, date] | None) -> bool:
    return p is not None and q is not None and p[0] <= q[1] and q[0] <= p[1]


def sizes_comparable(count_a: int, count_b: int, ratio: Decimal) -> bool:
    """Question 1 = C: the smaller side has at least `ratio` times the larger side's
    transactions. Decides what may be DONE about a pair (removal offered, backfill skip), not
    whether it is a probable duplicate."""
    smaller, larger = sorted((count_a, count_b))
    return Decimal(smaller) >= ratio * Decimal(larger)


def _account_relation(a: StatementSide, b: StatementSide) -> str:
    ids_a = {(f.identifier, f.currency) for f in a.accounts}
    ids_b = {(f.identifier, f.currency) for f in b.accounts}
    if not ids_a or not ids_b:
        return ACCOUNT_NOT_APPLICABLE
    return ACCOUNT_SHARED if ids_a & ids_b else ACCOUNT_CONFLICT


def _closing_balances_agree(a: StatementSide, b: StatementSide) -> bool:
    """A shared account whose closing balance AND closing-balance date are present and
    identical on both sides (FR-PD-4)."""
    by_key_b = {(f.identifier, f.currency): f for f in b.accounts}
    for fact_a in a.accounts:
        fact_b = by_key_b.get((fact_a.identifier, fact_a.currency))
        if fact_b is None:
            continue
        if (
            fact_a.closing_balance is not None
            and fact_a.closing_balance_date is not None
            and fact_a.closing_balance == fact_b.closing_balance
            and fact_a.closing_balance_date == fact_b.closing_balance_date
        ):
            return True
    return False


def evaluate(a: StatementSide, b: StatementSide, settings: DetectionSettings) -> Verdict:
    """Is `a` probably the same statement as `b`? Symmetric in its two arguments (apart from
    the order of `matched_pairs`' indices)."""
    count_a, count_b = len(a.transactions), len(b.transactions)
    banks_equal = a.bank_key == b.bank_key
    overlap = periods_overlap(a.period, b.period)
    account_rule = _account_relation(a, b)
    comparable = sizes_comparable(count_a, count_b, settings.match_ratio) if count_a and count_b else False

    def verdict(is_duplicate, matched_pairs=(), small=False, why_not=None):
        return Verdict(
            is_duplicate=is_duplicate,
            matched_count=len(matched_pairs),
            count_a=count_a,
            count_b=count_b,
            ratio=match_ratio(len(matched_pairs), count_a, count_b),
            sizes_comparable=comparable,
            small_gate_applied=small,
            account_rule=account_rule,
            banks_equal=banks_equal,
            periods_overlap=overlap,
            why_not=why_not,
            matched_pairs=tuple(matched_pairs),
        )

    if not banks_equal:
        return verdict(False, why_not="different banks")
    if not count_a or not count_b:
        return verdict(False, why_not="one statement has no transactions")
    if not overlap:
        return verdict(False, why_not="the periods do not overlap")
    if account_rule == ACCOUNT_CONFLICT:
        return verdict(False, why_not="different accounts (the account identifiers do not match)")

    pairs = match_transactions(a.transactions, b.transactions)
    smaller = min(count_a, count_b)
    if not _meets_ratio(len(pairs), count_a, count_b, settings.match_ratio):
        return verdict(
            False,
            pairs,
            why_not=f"only {len(pairs)} of {smaller} transactions match (below the {settings.match_ratio} threshold)",
        )

    small = smaller < settings.min_transactions
    if small and not (account_rule == ACCOUNT_SHARED and _closing_balances_agree(a, b)):
        return verdict(
            False,
            pairs,
            small=True,
            why_not=(
                f"a statement with fewer than {settings.min_transactions} transactions is never flagged on its "
                "transactions alone: it also needs a matching account identifier and closing balance, and "
                "those are not available for both"
            ),
        )
    return verdict(True, pairs, small=small)


def format_period(start: date, end: date) -> str:
    """"2 Jun to 30 Jun 2026" within one year, "28 Dec 2025 to 3 Jan 2026" across two. Month
    names are written out so the text never depends on a locale."""
    def day(d: date, with_year: bool) -> str:
        return f"{d.day} {_MONTHS[d.month - 1]}" + (f" {d.year}" if with_year else "")

    if start.year == end.year:
        return f"{day(start, False)} to {day(end, True)}"
    return f"{day(start, True)} to {day(end, True)}"


def overlapping_period_text(a: StatementSide, b: StatementSide) -> str:
    pa, pb = a.period, b.period
    if pa is None or pb is None:
        return "unknown"
    return format_period(max(pa[0], pb[0]), min(pa[1], pb[1]))


def describe(verdict: Verdict, earlier: StatementSide, later: StatementSide, *, incoming: bool) -> str:
    """The human-readable reason (WR-60). `earlier` and `later` are the comparison's two sides
    (for a skip, `earlier` is the held statement and `later` the incoming file; `incoming`
    is true then). The verdict must have been computed with the sides in either order."""
    count_e, count_l = len(earlier.transactions), len(later.transactions)
    text = (
        f"{verdict.matched_count} of {verdict.smaller_count} transactions match (the smaller statement); same bank; "
        f"overlapping period {overlapping_period_text(earlier, later)}."
    )
    if verdict.sizes_comparable:
        return text
    unmatched_on_later = count_l - verdict.matched_count
    if incoming:
        if count_l > count_e:
            return (
                f"{text} This file is the larger one: it has {count_l} transactions against {count_e} on the held "
                f"statement, and {unmatched_on_later} of its transactions have no match, so they were not ingested."
            )
        return (
            f"{text} This file is the smaller one: it has {count_l} transactions against {count_e} on the held "
            "statement."
        )
    larger, smaller_n = (count_e, count_l) if count_e >= count_l else (count_l, count_e)
    unmatched_on_larger = larger - verdict.matched_count
    return (
        f"{text} The two statements differ in size ({larger} and {smaller_n} transactions); "
        f"{unmatched_on_larger} on the larger one have no match."
    )


def select_snapshot(
    transactions: Sequence[TxnKey], matched_indexes: set[int], limit: int = SNAPSHOT_LIMIT
) -> list[SnapshotRow]:
    """At most `limit` rows: the largest by amount, ties earlier date first, then description
    and original position so the order is stable. Each row is marked by the same pairing the
    verdict used, so the rows that line up in the view are exactly the rows that were counted."""
    order = sorted(
        range(len(transactions)),
        key=lambda i: (-transactions[i].amount, transactions[i].date, transactions[i].description, i),
    )[:limit]
    return [
        SnapshotRow(
            rank=rank,
            date=transactions[i].date,
            description=transactions[i].description,
            amount=transactions[i].amount,
            direction=transactions[i].direction,
            currency=transactions[i].currency,
            marker=MARKER_ALSO_ON_OTHER if i in matched_indexes else MARKER_ONLY_ON_THIS_ONE,
        )
        for rank, i in enumerate(order, start=1)
    ]


def choose_kept_copy(a: CopyFacts, b: CopyFacts) -> tuple[CopyFacts, CopyFacts]:
    """(keep, remove). The copy carrying manual corrections; if neither or both carry some,
    the earlier ingested; then the smaller content hash, so the answer is deterministic and
    independent of argument order (FR-PD-11)."""
    a_has, b_has = a.manual_corrections > 0, b.manual_corrections > 0
    if a_has != b_has:
        return (a, b) if a_has else (b, a)
    if a.ingested_at != b.ingested_at:
        return (a, b) if a.ingested_at < b.ingested_at else (b, a)
    return (a, b) if a.content_hash <= b.content_hash else (b, a)
