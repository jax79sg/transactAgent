"""Issue #28 (Costs page): GET /costs against a real database -- grouping by period and by purpose/model, the viewer's
own calendar days, inclusive range edges, and every refusal."""

import random
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from transactagent_db.models import ModelUsage

from api_service.costs.service import list_periods


def _use(db, when: str, *, purpose="categorization", model="gemini-3.5-flash-lite", cost="0.01", tokens_in=1000,
         tokens_out=100, estimated=False):
    """`when` is a UTC instant, e.g. "2026-10-05 17:30"."""
    db.add(
        ModelUsage(
            occurred_at=datetime.fromisoformat(when).replace(tzinfo=UTC), purpose=purpose, provider="gemini",
            model=model, input_tokens=tokens_in, output_tokens=tokens_out, cost_usd=Decimal(cost),
            tokens_estimated=estimated,
        )
    )
    db.flush()


def _get(client, auth_headers, **params):
    params = {"date_from": "2026-10-01", "date_to": "2026-10-31", **params}
    return client.get("/costs", params=params, headers=auth_headers)


class TestEmptyAndShape:
    def test_nothing_recorded_is_zero_everywhere_but_still_lists_every_day(self, client, auth_headers):
        response = _get(client, auth_headers, date_to="2026-10-03")

        assert response.status_code == 200
        body = response.json()
        assert body["currency"] == "USD"
        assert body["periods"] == ["2026-10-01", "2026-10-02", "2026-10-03"]
        assert body["series"] == []
        assert body["groups"] == []
        assert body["totals"] == {
            "costUsd": "0", "inputTokens": 0, "outputTokens": 0, "calls": 0, "estimatedCalls": 0,
        }

    def test_the_request_is_echoed_back(self, client, auth_headers):
        body = _get(client, auth_headers, granularity="week", group_by="model", timezone="Asia/Singapore").json()

        assert (body["dateFrom"], body["dateTo"], body["granularity"], body["groupBy"], body["timezone"]) == (
            "2026-10-01", "2026-10-31", "week", "model", "Asia/Singapore",
        )

    def test_it_requires_a_login(self, client):
        assert client.get("/costs", params={"date_from": "2026-10-01", "date_to": "2026-10-31"}).status_code == 401


class TestTotalsAndSeries:
    def test_calls_on_one_day_are_summed_exactly(self, client, auth_headers, db_session):
        _use(db_session, "2026-10-05 01:00", cost="0.00000400", tokens_in=20, tokens_out=0, estimated=True)
        _use(db_session, "2026-10-05 02:00", cost="0.12345678", tokens_in=3000, tokens_out=500)
        _use(db_session, "2026-10-05 23:00", cost="0.00000002", tokens_in=1, tokens_out=1)

        body = _get(client, auth_headers).json()

        assert body["totals"] == {
            "costUsd": "0.12346080", "inputTokens": 3021, "outputTokens": 501, "calls": 3, "estimatedCalls": 1,
        }
        assert body["series"] == [{
            "period": "2026-10-05", "group": "All", "costUsd": "0.12346080", "inputTokens": 3021,
            "outputTokens": 501, "calls": 3, "estimatedCalls": 1,
        }]

    def test_days_with_calls_each_get_a_row_and_days_without_do_not(self, client, auth_headers, db_session):
        _use(db_session, "2026-10-02 05:00", cost="1")
        _use(db_session, "2026-10-04 05:00", cost="2")

        body = _get(client, auth_headers, date_to="2026-10-05").json()

        assert [p["period"] for p in body["series"]] == ["2026-10-02", "2026-10-04"]
        assert body["periods"] == [f"2026-10-0{d}" for d in range(1, 6)]  # the empty days are still on the axis

    def test_calls_outside_the_range_are_not_counted(self, client, auth_headers, db_session):
        _use(db_session, "2026-09-30 23:59", cost="100")
        _use(db_session, "2026-11-01 00:00", cost="100")
        _use(db_session, "2026-10-15 12:00", cost="1")

        assert _get(client, auth_headers).json()["totals"]["costUsd"] == "1.00000000"


class TestRangeEdgesAreTheViewersCalendarDays:
    def test_both_end_days_are_inclusive_to_the_last_instant(self, client, auth_headers, db_session):
        _use(db_session, "2026-10-01 00:00:00", cost="1")  # first instant of date_from (UTC)
        _use(db_session, "2026-10-03 23:59:59", cost="2")  # last second of date_to
        _use(db_session, "2026-10-04 00:00:00", cost="4")  # first instant after
        _use(db_session, "2026-09-30 23:59:59", cost="8")  # last instant before

        body = _get(client, auth_headers, date_to="2026-10-03").json()

        assert body["totals"]["calls"] == 2
        assert body["totals"]["costUsd"] == "3.00000000"

    def test_a_late_evening_utc_call_is_the_next_day_in_singapore(self, client, auth_headers, db_session):
        _use(db_session, "2026-10-05 17:30", cost="1")  # 01:30 on the 6th in Singapore (UTC+8)

        in_utc = _get(client, auth_headers, timezone="UTC").json()
        in_singapore = _get(client, auth_headers, timezone="Asia/Singapore").json()

        assert [p["period"] for p in in_utc["series"]] == ["2026-10-05"]
        assert [p["period"] for p in in_singapore["series"]] == ["2026-10-06"]

    def test_the_range_edges_move_with_the_time_zone_too(self, client, auth_headers, db_session):
        _use(db_session, "2026-09-30 16:00", cost="1")  # 00:00 on 1 Oct in Singapore: the first instant of date_from
        _use(db_session, "2026-09-30 15:59", cost="2")  # 23:59 on 30 Sep in Singapore: the day before

        sg = _get(client, auth_headers, timezone="Asia/Singapore", date_to="2026-10-01").json()
        utc = _get(client, auth_headers, timezone="UTC", date_to="2026-10-01").json()

        assert sg["totals"]["costUsd"] == "1.00000000"
        assert utc["totals"]["costUsd"] == "0"  # both calls are on 30 September in UTC


class TestGranularity:
    @pytest.fixture(autouse=True)
    def _calls(self, db_session):
        # Mon 5 Oct, Sun 11 Oct (same ISO week), Mon 12 Oct (next week), 30 Sep (previous month and week).
        _use(db_session, "2026-10-05 05:00", cost="1")
        _use(db_session, "2026-10-11 05:00", cost="2")
        _use(db_session, "2026-10-12 05:00", cost="4")
        _use(db_session, "2026-09-30 05:00", cost="8")

    def test_weeks_start_on_monday(self, client, auth_headers):
        body = _get(client, auth_headers, date_from="2026-09-28", granularity="week").json()

        assert [(p["period"], p["costUsd"]) for p in body["series"]] == [
            ("2026-09-28", "8.00000000"), ("2026-10-05", "3.00000000"), ("2026-10-12", "4.00000000"),
        ]
        assert body["periods"] == ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]

    def test_months_start_on_the_first(self, client, auth_headers):
        body = _get(client, auth_headers, date_from="2026-09-01", granularity="month").json()

        assert [(p["period"], p["costUsd"]) for p in body["series"]] == [
            ("2026-09-01", "8.00000000"), ("2026-10-01", "7.00000000"),
        ]
        assert body["periods"] == ["2026-09-01", "2026-10-01"]

    def test_a_week_that_starts_before_the_range_only_counts_calls_inside_it(self, client, auth_headers):
        body = _get(client, auth_headers, date_from="2026-10-07", date_to="2026-10-13", granularity="week").json()

        # the call on Monday 5 Oct is before date_from, so the week of 5 Oct holds only the Sunday 11 Oct call
        assert [(p["period"], p["costUsd"]) for p in body["series"]] == [
            ("2026-10-05", "2.00000000"), ("2026-10-12", "4.00000000"),
        ]

    def test_the_total_is_the_same_whatever_the_granularity(self, client, auth_headers):
        totals = {
            g: _get(client, auth_headers, date_from="2026-09-01", granularity=g).json()["totals"]
            for g in ("day", "week", "month")
        }

        assert totals["day"] == totals["week"] == totals["month"]
        assert totals["day"]["costUsd"] == "15.00000000"


class TestGrouping:
    @pytest.fixture(autouse=True)
    def _calls(self, db_session):
        _use(db_session, "2026-10-05 05:00", purpose="statement_extraction", model="big", cost="5")
        _use(db_session, "2026-10-05 06:00", purpose="categorization", model="small", cost="1")
        _use(db_session, "2026-10-05 07:00", purpose="categorization", model="small", cost="2", estimated=True)
        _use(db_session, "2026-10-06 05:00", purpose="embedding", model="emb", cost="0.5", estimated=True)

    def test_by_purpose_splits_each_day_and_ranks_groups_by_cost(self, client, auth_headers):
        body = _get(client, auth_headers, group_by="purpose").json()

        assert [(p["period"], p["group"], p["costUsd"], p["calls"]) for p in body["series"]] == [
            ("2026-10-05", "categorization", "3.00000000", 2),
            ("2026-10-05", "statement_extraction", "5.00000000", 1),
            ("2026-10-06", "embedding", "0.50000000", 1),
        ]
        assert [(g["group"], g["costUsd"], g["calls"], g["estimatedCalls"]) for g in body["groups"]] == [
            ("statement_extraction", "5.00000000", 1, 0),
            ("categorization", "3.00000000", 2, 1),
            ("embedding", "0.50000000", 1, 1),
        ]

    def test_by_model(self, client, auth_headers):
        body = _get(client, auth_headers, group_by="model").json()

        assert [g["group"] for g in body["groups"]] == ["big", "small", "emb"]

    def test_no_grouping_is_one_group_called_all(self, client, auth_headers):
        body = _get(client, auth_headers, group_by="none").json()

        assert [g["group"] for g in body["groups"]] == ["All"]
        assert body["groups"][0]["costUsd"] == body["totals"]["costUsd"] == "8.50000000"

    def test_the_groups_always_add_up_to_the_total_and_the_series_does_too(self, client, auth_headers):
        for group_by in ("none", "purpose", "model"):
            body = _get(client, auth_headers, group_by=group_by).json()
            assert sum(Decimal(g["costUsd"]) for g in body["groups"]) == Decimal(body["totals"]["costUsd"])
            assert sum(Decimal(p["costUsd"]) for p in body["series"]) == Decimal(body["totals"]["costUsd"])
            assert sum(g["calls"] for g in body["groups"]) == body["totals"]["calls"] == 4

    def test_groups_with_equal_cost_are_ordered_by_name(self, client, auth_headers, db_session):
        _use(db_session, "2026-10-07 05:00", purpose="ask_ai", model="zeta", cost="5")

        body = _get(client, auth_headers, group_by="purpose").json()

        assert [g["group"] for g in body["groups"][:2]] == ["ask_ai", "statement_extraction"]  # both cost 5


class TestRefusals:
    def test_an_unknown_time_zone_is_a_400(self, client, auth_headers):
        response = _get(client, auth_headers, timezone="Mars/Olympus_Mons")

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_time_zone"

    @pytest.mark.parametrize("zone", ["", "../etc/passwd", "UTC'; DROP TABLE model_usage; --"])
    def test_a_malformed_time_zone_is_refused_not_passed_to_the_database(self, client, auth_headers, zone):
        assert _get(client, auth_headers, timezone=zone).status_code == 400

    def test_a_range_that_ends_before_it_starts_is_a_400(self, client, auth_headers):
        response = _get(client, auth_headers, date_from="2026-10-31", date_to="2026-10-01")

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_date_range"

    @pytest.mark.parametrize(("name", "value"), [("granularity", "hour"), ("group_by", "bank"), ("date_from", "soon")])
    def test_an_unknown_choice_is_a_422(self, client, auth_headers, name, value):
        assert _get(client, auth_headers, **{name: value}).status_code == 422

    def test_both_dates_are_required(self, client, auth_headers):
        assert client.get("/costs", params={"date_from": "2026-10-01"}, headers=auth_headers).status_code == 422


class TestListPeriods:
    def test_days(self):
        assert list_periods(date(2026, 12, 30), date(2027, 1, 2), "day") == [
            date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 2),
        ]

    def test_weeks_begin_on_the_monday_on_or_before_the_start(self):
        assert list_periods(date(2026, 10, 7), date(2026, 10, 20), "week") == [
            date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19),
        ]

    def test_months_roll_over_the_year_end(self):
        assert list_periods(date(2026, 11, 20), date(2027, 2, 3), "month") == [
            date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1),
        ]

    @pytest.mark.parametrize("granularity", ["day", "week", "month"])
    def test_a_single_day_range_is_one_period(self, granularity):
        assert len(list_periods(date(2026, 10, 7), date(2026, 10, 7), granularity)) == 1

    @pytest.mark.parametrize("granularity", ["day", "week", "month"])
    def test_periods_are_ordered_unique_and_cover_the_whole_range(self, granularity):
        rng = random.Random(28)  # seeded: a failure reproduces
        for _ in range(200):
            start = date.fromordinal(rng.randint(date(2020, 1, 1).toordinal(), date(2035, 12, 31).toordinal()))
            end = date.fromordinal(start.toordinal() + rng.randint(0, 800))
            periods = list_periods(start, end, granularity)

            assert periods == sorted(set(periods))
            assert periods[0] <= start
            assert periods[-1] <= end
            # the period holding `end` is last: nothing between the last period and `end` is left uncovered
            assert list_periods(end, end, granularity)[0] == periods[-1]
