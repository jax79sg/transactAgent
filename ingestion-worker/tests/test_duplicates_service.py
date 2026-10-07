"""WR-59..WR-64: judging an extracted statement against held ones, recording a skip, and the pair
scan. Real PostgreSQL; the shapes of the real data (the UOB and Trust June pairs, the CIMB
look-alikes) are used throughout."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from duplicates_helpers import extracted, june, make_statement
from transactagent_db.models import (
    CategorySource,
    DuplicateComparison,
    DuplicateComparisonRow,
    DuplicatePair,
    DuplicatePairStatus,
    DuplicateScanState,
    KnownFile,
    KnownFileState,
    Transaction,
)

from ingestion_worker import config
from ingestion_worker.duplicates import repository, service

H1, H2, H3 = "1" * 64, "2" * 64, "3" * 64


@pytest.fixture
def detection_on(monkeypatch):
    monkeypatch.setattr(config.settings, "duplicate_detection_enabled", True)
    monkeypatch.setattr(config.settings, "duplicate_match_ratio", 0.80)
    monkeypatch.setattr(config.settings, "duplicate_min_transactions", 3)


class TestFindProbableDuplicateOf:
    def test_the_uob_june_pair_is_recognised(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5), file_name="JUN 2026_20260728.pdf")

        match = service.find_probable_duplicate_of(db_session, extracted(june(5)), H2, file_name="JUN 2026_20260828.pdf")

        assert match is not None
        assert match.held.content_hash == H1
        assert match.verdict.matched_count == 5
        assert match.draft.earlier.file_name == "JUN 2026_20260728.pdf"  # the held statement is the earlier side
        assert match.draft.later.file_name == "JUN 2026_20260828.pdf"
        assert match.draft.reason.startswith("5 of 5 transactions match")

    def test_the_trust_pair_is_recognised_across_two_spellings_of_the_bank(self, db_session, detection_on):
        make_statement(db_session, h=H1, bank="Trust Bank Singapore Limited", rows=june(8))

        match = service.find_probable_duplicate_of(db_session, extracted(june(8), bank="Trust"), H2)

        assert match is not None and match.verdict.matched_count == 8

    def test_the_cimb_one_transaction_lookalike_is_not_flagged(self, db_session, detection_on):
        one = [(date(2026, 2, 28), "12.34", "INTEREST")]
        make_statement(db_session, h=H1, bank="CIMB", rows=one, direction="in")

        assert service.find_probable_duplicate_of(db_session, extracted(one, bank="CIMB", direction="in"), H2) is None

    def test_a_small_statement_is_flagged_once_identifier_and_closing_balance_match(self, db_session, detection_on):
        one = [(date(2026, 2, 28), "12.34", "INTEREST")]
        closing = ("100.00", date(2026, 2, 28))
        make_statement(
            db_session, h=H1, bank="CIMB", rows=one, direction="in", accounts=[("5678", "SGD", Decimal("100.00"), date(2026, 2, 28))]
        )

        match = service.find_probable_duplicate_of(
            db_session, extracted(one, bank="CIMB", direction="in", identifier="5678", closing=closing), H2
        )

        assert match is not None

    def test_detection_off_judges_nothing(self, db_session, monkeypatch):
        monkeypatch.setattr(config.settings, "duplicate_detection_enabled", False)
        make_statement(db_session, h=H1, rows=june(5))

        assert service.find_probable_duplicate_of(db_session, extracted(june(5)), H2) is None

    def test_force_enabled_judges_even_when_the_switch_is_off(self, db_session, monkeypatch):
        """The Backfill Tool's reingest (WR-69)."""
        monkeypatch.setattr(config.settings, "duplicate_detection_enabled", False)
        make_statement(db_session, h=H1, rows=june(5))

        assert service.find_probable_duplicate_of(db_session, extracted(june(5)), H2, force_enabled=True) is not None

    def test_an_overridden_file_is_exempt(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        match = service.find_probable_duplicate_of(db_session, extracted(june(5)), H2)
        service.record_skipped_duplicate(db_session, match, H2)
        known = repository.get_known_file(db_session, H2)
        known.state = KnownFileState.OVERRIDDEN
        db_session.flush()

        assert service.find_probable_duplicate_of(db_session, extracted(june(5)), H2) is None

    def test_a_dismissed_pair_is_excluded(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        match = service.find_probable_duplicate_of(db_session, extracted(june(5)), H2)
        comparison = repository.create_comparison(db_session, match.draft)
        repository.insert_pair(db_session, key=repository.pair_key(H1, H2), comparison_id=comparison.id, keep_hash=H1, removal_allowed=True)
        db_session.query(DuplicatePair).update({"status": DuplicatePairStatus.DISMISSED})
        db_session.flush()

        assert service.find_probable_duplicate_of(db_session, extracted(june(5)), H2) is None

    def test_a_statement_with_no_bank_name_is_never_compared(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        no_bank = extracted(june(5))
        no_bank.bank_name = None

        assert service.find_probable_duplicate_of(db_session, no_bank, H2) is None

    def test_a_different_month_is_not_a_duplicate(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5, month=5))

        assert service.find_probable_duplicate_of(db_session, extracted(june(5, month=6)), H2) is None

    def test_a_different_bank_is_not_a_duplicate(self, db_session, detection_on):
        make_statement(db_session, h=H1, bank="DBS", rows=june(5))

        assert service.find_probable_duplicate_of(db_session, extracted(june(5), bank="UOB"), H2) is None

    def test_the_best_candidate_wins(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=[*june(6)[:5], (date(2026, 6, 20), "99.00", "OTHER")], ingested_days=0)
        make_statement(db_session, h=H3, rows=june(5), ingested_days=1)

        match = service.find_probable_duplicate_of(db_session, extracted(june(5)), H2)

        assert match.held.content_hash in (H1, H3)
        assert match.verdict.matched_count == 5

    def test_judging_writes_nothing(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        before = (db_session.query(DuplicateComparison).count(), db_session.query(KnownFile).count())

        service.find_probable_duplicate_of(db_session, extracted(june(5)), H2)

        assert (db_session.query(DuplicateComparison).count(), db_session.query(KnownFile).count()) == before


class TestRecordSkippedDuplicate:
    def test_writes_the_comparison_its_rows_and_a_remembered_file_and_nothing_else(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        match = service.find_probable_duplicate_of(db_session, extracted(june(5)), H2, file_name="b.pdf")
        statements_before = db_session.query(Transaction).count()

        comparison = service.record_skipped_duplicate(db_session, match, H2)

        known = repository.get_known_file(db_session, H2)
        assert known.state is KnownFileState.PROBABLE_DUPLICATE
        assert known.matched_statement_hash == H1 and known.comparison_id == comparison.id
        rows = db_session.query(DuplicateComparisonRow).filter_by(comparison_id=comparison.id).all()
        assert len(rows) == 10 and {r.marker.value for r in rows} == {"also_on_other"}
        assert db_session.query(Transaction).count() == statements_before  # nothing ingested

    def test_a_second_skip_of_the_same_file_keeps_the_first_record(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        match = service.find_probable_duplicate_of(db_session, extracted(june(5)), H2)
        service.record_skipped_duplicate(db_session, match, H2)
        first = repository.get_known_file(db_session, H2).comparison_id

        service.record_skipped_duplicate(db_session, match, H2)

        assert repository.get_known_file(db_session, H2).comparison_id == first


def settle(db):
    """Run a scan and return the pairs by canonical key."""
    service.run_pair_scan(db)
    return repository.load_pairs(db)


class TestPairScan:
    def test_finds_both_real_pairs_and_not_the_lookalikes(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5), manual=2, ingested_days=0)
        make_statement(db_session, h=H2, rows=june(5), ingested_days=30)
        make_statement(db_session, h="a" * 64, bank="Trust Bank", rows=june(8), ingested_days=1)
        make_statement(db_session, h="b" * 64, bank="Trust Bank Singapore Limited", rows=june(8), manual=2, ingested_days=31)
        one = [(date(2026, 2, 28), "12.34", "INTEREST")]
        make_statement(db_session, h="c" * 64, bank="CIMB", rows=one, direction="in")
        make_statement(db_session, h="d" * 64, bank="CIMB", rows=one, direction="in", ingested_days=1)

        pairs = settle(db_session)

        assert set(pairs) == {(H1, H2), ("a" * 64, "b" * 64)}
        uob, trust = pairs[(H1, H2)], pairs[("a" * 64, "b" * 64)]
        assert uob.keep_hash == H1  # the copy carrying the corrections
        assert trust.keep_hash == "b" * 64  # corrections on the LATER copy: kept despite being later
        assert uob.removal_allowed and trust.removal_allowed
        assert uob.status is DuplicatePairStatus.PENDING

    def test_the_comparison_is_stored_once_with_both_sides(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5), file_name="first.pdf")
        make_statement(db_session, h=H2, rows=june(5), ingested_days=30, file_name="second.pdf")

        pair = settle(db_session)[(H1, H2)]
        comparison = db_session.get(DuplicateComparison, pair.comparison_id)

        assert (comparison.earlier_file_name, comparison.later_file_name) == ("first.pdf", "second.pdf")
        assert comparison.matched_count == 5 and comparison.match_ratio == Decimal("1.0000")

    def test_rescanning_is_idempotent(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        make_statement(db_session, h=H2, rows=june(5), ingested_days=30)
        first = settle(db_session)
        comparisons = db_session.query(DuplicateComparison).count()

        second = settle(db_session)

        assert set(first) == set(second)
        assert db_session.query(DuplicateComparison).count() == comparisons  # no second snapshot

    def test_a_pending_pairs_proposal_is_refreshed_when_corrections_change(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5), ingested_days=0)
        later = make_statement(db_session, h=H2, rows=june(5), ingested_days=30)
        assert settle(db_session)[(H1, H2)].keep_hash == H1  # neither has corrections: the earlier

        corrected = db_session.query(Transaction).filter_by(bank_statement_id=later.id).first()
        corrected.category_source = CategorySource.MANUAL  # the user corrects a transaction on the LATER copy
        db_session.flush()

        assert settle(db_session)[(H1, H2)].keep_hash == H2

    @pytest.mark.parametrize("status", [DuplicatePairStatus.DISMISSED, DuplicatePairStatus.REMOVED, DuplicatePairStatus.SUPERSEDED])
    def test_decided_pairs_are_left_alone(self, db_session, detection_on, status):
        make_statement(db_session, h=H1, rows=june(5))
        make_statement(db_session, h=H2, rows=june(5), ingested_days=30)
        pair = settle(db_session)[(H1, H2)]
        pair.status = status
        pair.keep_hash = H2
        db_session.flush()

        again = settle(db_session)[(H1, H2)]

        assert again.status is status and again.keep_hash == H2

    def test_a_pending_pair_whose_statement_is_gone_is_superseded(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        gone = make_statement(db_session, h=H2, rows=june(5), ingested_days=30)
        assert settle(db_session)[(H1, H2)].status is DuplicatePairStatus.PENDING
        db_session.query(Transaction).filter_by(bank_statement_id=gone.id).delete()
        db_session.delete(gone)
        db_session.flush()

        assert settle(db_session)[(H1, H2)].status is DuplicatePairStatus.SUPERSEDED

    def test_a_pending_pair_whose_file_was_overridden_is_superseded(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        make_statement(db_session, h=H2, rows=june(5), ingested_days=30)
        pair = settle(db_session)[(H1, H2)]
        db_session.add(KnownFile(pdf_content_hash=H2, state=KnownFileState.OVERRIDDEN, matched_statement_hash=H1, comparison_id=pair.comparison_id))
        db_session.flush()

        assert settle(db_session)[(H1, H2)].status is DuplicatePairStatus.SUPERSEDED

    def test_a_pair_of_clearly_different_sizes_is_listed_without_removal(self, db_session, detection_on):
        """Question 1 = C."""
        make_statement(db_session, h=H1, rows=june(5))
        make_statement(db_session, h=H2, rows=[*june(5), *((date(2026, 6, 20 + i), f"{500 + i}.00", f"EXTRA {i}") for i in range(10))], ingested_days=30)

        pair = settle(db_session)[(H1, H2)]

        assert pair.removal_allowed is False
        assert pair.status is DuplicatePairStatus.PENDING

    def test_three_copies_make_three_pairs(self, db_session, detection_on):
        for i, h in enumerate((H1, H2, H3)):
            make_statement(db_session, h=h, rows=june(5), ingested_days=i)

        assert set(settle(db_session)) == {(H1, H2), (H1, H3), (H2, H3)}

    def test_the_scan_records_what_it_used(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        make_statement(db_session, h=H2, rows=june(5), ingested_days=30)

        service.run_pair_scan(db_session)
        state = db_session.get(DuplicateScanState, 1)

        assert state.last_scan_completed_at >= state.last_scan_started_at
        assert state.last_scan_match_ratio == Decimal("0.8000") and state.last_scan_min_transactions == 3
        assert state.last_scan_pairs_found == 1

    def test_near_misses_are_reported_with_their_reason(self, db_session, detection_on):
        one = [(date(2026, 2, 28), "12.34", "INTEREST")]
        make_statement(db_session, h="c" * 64, bank="CIMB", rows=one, direction="in")
        make_statement(db_session, h="d" * 64, bank="CIMB", rows=one, direction="in", ingested_days=1)

        findings, near = service.compute_findings(db_session, service.current_settings())

        assert findings == [] and len(near) == 1
        assert "fewer than 3" in near[0].why_not

    def test_compute_findings_writes_nothing(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        make_statement(db_session, h=H2, rows=june(5), ingested_days=30)

        service.compute_findings(db_session, service.current_settings())

        assert db_session.query(DuplicatePair).count() == 0 and db_session.query(DuplicateComparison).count() == 0


class TestScanDue:
    def _scan(self, db):
        make_statement(db, h=H1, rows=june(5))
        make_statement(db, h=H2, rows=june(5), ingested_days=30)
        service.run_pair_scan(db)

    def test_not_due_when_detection_is_off(self, db_session, monkeypatch):
        monkeypatch.setattr(config.settings, "duplicate_detection_enabled", False)
        assert service.is_pair_scan_due_now(db_session) is False

    def test_due_when_none_has_ever_run(self, db_session, detection_on):
        assert service.is_pair_scan_due_now(db_session) is True

    def test_not_due_right_after_a_scan(self, db_session, detection_on):
        self._scan(db_session)
        assert service.is_pair_scan_due_now(db_session) is False

    def test_due_when_the_ratio_changed(self, db_session, detection_on, monkeypatch):
        self._scan(db_session)
        monkeypatch.setattr(config.settings, "duplicate_match_ratio", 0.9)
        assert service.is_pair_scan_due_now(db_session) is True

    def test_due_when_the_minimum_changed(self, db_session, detection_on, monkeypatch):
        self._scan(db_session)
        monkeypatch.setattr(config.settings, "duplicate_min_transactions", 5)
        assert service.is_pair_scan_due_now(db_session) is True

    def test_due_when_a_recheck_was_requested_after_the_scan_started(self, db_session, detection_on):
        self._scan(db_session)
        state = db_session.get(DuplicateScanState, 1)
        state.recheck_requested_at = datetime.now(UTC) + timedelta(seconds=1)
        db_session.flush()
        assert service.is_pair_scan_due_now(db_session) is True

    def test_a_recheck_requested_before_the_scan_does_not_re_trigger(self, db_session, detection_on):
        make_statement(db_session, h=H1, rows=june(5))
        state = repository.get_or_create_scan_state(db_session)
        state.recheck_requested_at = datetime.now(UTC) - timedelta(hours=1)
        db_session.flush()
        service.run_pair_scan(db_session)
        assert service.is_pair_scan_due_now(db_session) is False

    def test_due_when_a_statement_was_added_after_the_scan_started(self, db_session, detection_on):
        self._scan(db_session)
        make_statement(db_session, h=H3, rows=june(5), ingested_days=400)  # processed_at in the future of the scan
        assert service.is_pair_scan_due_now(db_session) is True

    def test_due_when_a_scan_began_and_never_finished(self, db_session, detection_on):
        self._scan(db_session)
        state = db_session.get(DuplicateScanState, 1)
        state.last_scan_completed_at = state.last_scan_started_at - timedelta(seconds=5)
        db_session.flush()
        assert service.is_pair_scan_due_now(db_session) is True

    def test_a_scan_that_raises_stays_due(self, db_session, detection_on, monkeypatch):
        make_statement(db_session, h=H1, rows=june(5))
        monkeypatch.setattr(service, "compute_findings", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

        with pytest.raises(RuntimeError):
            service.run_pair_scan(db_session)

        assert service.is_pair_scan_due_now(db_session) is True
