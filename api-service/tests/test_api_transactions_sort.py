"""Issue #23: every sortable column of the Transactions table orders correctly, and ties never make a page repeat or
skip rows of another."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from transactagent_db.models import BankStatement, Category, CategorySource, Transaction


@pytest.fixture
def category(db_session):
    category = Category(name="Groceries", active=True, is_reserved=False)
    db_session.add(category)
    db_session.flush()
    return category


@pytest.fixture
def statement(db_session):
    statement = BankStatement(drive_file_id=f"f-{uuid.uuid4()}", pdf_content_hash=uuid.uuid4().hex.ljust(64, "0"))
    db_session.add(statement)
    db_session.flush()
    return statement


@pytest.fixture
def add(db_session, category, statement):
    def _add(description, *, day=15, out_flow="10.00", converted="10.00", bank="DBS"):
        txn = Transaction(
            bank_statement_id=statement.id,
            transaction_date=date(2026, 1, day),
            description=description,
            out_flow=Decimal(out_flow),
            currency="SGD",
            bank_name=bank,
            category_id=category.id,
            category_source=CategorySource.SIMILARITY,
            converted_amount_sgd=None if converted is None else Decimal(converted),
            conversion_unavailable=converted is None,
        )
        db_session.add(txn)
        db_session.flush()
        return txn

    return _add


def _list(client, auth_headers, **params):
    response = client.get("/transactions", params=params, headers=auth_headers)
    assert response.status_code == 200
    return response.json()


def _column(body, field):
    return [item[field] for item in body["items"]]


class TestSortByDescription:
    def test_ascending_and_descending_are_alphabetical(self, client, auth_headers, add):
        for name in ("GRAB TRANSPORT", "AIA INSURANCE", "NTUC FAIRPRICE"):
            add(name)

        asc = _column(_list(client, auth_headers, sort_by="description", sort_dir="asc"), "description")
        desc = _column(_list(client, auth_headers, sort_by="description", sort_dir="desc"), "description")

        assert asc == ["AIA INSURANCE", "GRAB TRANSPORT", "NTUC FAIRPRICE"]
        assert desc == list(reversed(asc))

    def test_case_makes_no_difference(self, client, auth_headers, add):
        # chosen so byte order (capitals first) and alphabetical order disagree: "Zebra" would precede "banana" in bytes
        for name in ("banana stand", "Zebra Cafe", "APPLE STORE", "cherry bar"):
            add(name)

        asc = _column(_list(client, auth_headers, sort_by="description", sort_dir="asc"), "description")

        assert asc == ["APPLE STORE", "banana stand", "cherry bar", "Zebra Cafe"]

    def test_the_same_description_comes_newest_first_in_either_direction(self, client, auth_headers, add):
        # six rows: the chance that an arbitrary tie order happens to be newest-first is under 1 in 700
        days = [3, 20, 11, 7, 28, 15]
        for day in days:
            add("NTUC FAIRPRICE", day=day)

        for direction in ("asc", "desc"):
            body = _list(client, auth_headers, sort_by="description", sort_dir=direction)
            assert _column(body, "transactionDate") == [f"2026-01-{d:02d}" for d in sorted(days, reverse=True)]


class TestSortByConverted:
    def test_orders_by_the_converted_amount_not_the_original(self, client, auth_headers, add):
        add("A", out_flow="1.00", converted="30.00")
        add("B", out_flow="999.00", converted="5.00")
        add("C", out_flow="50.00", converted="12.50")

        asc = _column(_list(client, auth_headers, sort_by="converted", sort_dir="asc"), "convertedAmountSgd")
        desc = _column(_list(client, auth_headers, sort_by="converted", sort_dir="desc"), "convertedAmountSgd")

        assert asc == ["5.00", "12.50", "30.00"]
        assert desc == ["30.00", "12.50", "5.00"]

    def test_a_transaction_with_no_exchange_rate_goes_last_in_either_direction(self, client, auth_headers, add):
        add("NO RATE", converted=None)
        add("LOW", converted="1.00")
        add("HIGH", converted="99.00")

        for direction in ("asc", "desc"):
            body = _list(client, auth_headers, sort_by="converted", sort_dir=direction)
            assert _column(body, "description")[-1] == "NO RATE"


class TestPagingStaysConsistentWhenValuesRepeat:
    """Sorting by a column where most rows tie (one bank, one description) used to leave the order to chance, so a
    page could repeat or skip rows that belong to another page."""

    @pytest.mark.parametrize("sort_by", ["description", "bank", "category", "converted", "amount", "date"])
    @pytest.mark.parametrize("sort_dir", ["asc", "desc"])
    def test_walking_every_page_yields_each_row_exactly_once_in_the_same_order(
        self, client, auth_headers, add, sort_by, sort_dir
    ):
        for index in range(11):
            add("NTUC FAIRPRICE", day=1 + index % 3, out_flow="10.00", converted="10.00", bank="DBS")

        seen = []
        for page in range(1, 7):
            body = _list(client, auth_headers, sort_by=sort_by, sort_dir=sort_dir, page=page, page_size=2)
            seen.extend(_column(body, "id"))

        assert len(seen) == 11
        assert len(set(seen)) == 11
        everything = _column(_list(client, auth_headers, sort_by=sort_by, sort_dir=sort_dir, page_size=50), "id")
        assert seen == everything


class TestSortOptionsAreValidated:
    def test_an_unknown_column_is_refused(self, client, auth_headers):
        response = client.get("/transactions", params={"sort_by": "colour"}, headers=auth_headers)

        assert response.status_code == 422
