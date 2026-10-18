"""The classifier dataset: what is read, how it is split, what is written, and that it cannot leak into git."""

import json
import math
import subprocess
import threading
import uuid
from datetime import date
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pyarrow.parquet as pq
import pytest
from transactagent_db.models import BankStatement, Category, CategorySource, Transaction

from model_training import classifier_dataset as cd
from model_training import repository
from model_training.repository import LabelledTransaction

POLICY = cd.SplitPolicy()


def labelled(description, category="Dining", source=CategorySource.MANUAL, *, transaction_id=None, out_flow="10.00", suggested=None):
    return LabelledTransaction(
        transaction_id=transaction_id or uuid.uuid4(),
        transaction_date=date(2026, 1, 1),
        description=description,
        out_flow=Decimal(out_flow) if out_flow else None,
        in_flow=None if out_flow else Decimal("5.00"),
        currency="SGD",
        bank_name="OCBC Bank",
        converted_amount_sgd=Decimal("10.00"),
        conversion_is_approximate=False,
        conversion_unavailable=False,
        bank_statement_id=uuid.uuid4(),
        statement_account_id=None,
        category_id=uuid.uuid4(),
        category_name=category,
        category_source=source,
        llm_suggested_category_name=suggested,
    )


def vectors_for(transactions, dimensions=4):
    return {str(t.transaction_id): [float(i + 1) / 10 for i in range(dimensions)] for t in transactions}


class TestGroupKey:
    def test_case_and_spacing_do_not_make_a_new_merchant(self):
        assert cd.group_key("  NETS QR   Purchase ") == cd.group_key("nets qr purchase")

    def test_a_trailing_reference_code_does_not_make_a_new_merchant(self):
        assert cd.group_key("FAST PAYMENT via PayNow-UEN to TINO OTHR-ABC123XYZ") == cd.group_key("FAST PAYMENT via PayNow-UEN to TINO OTHR-QQQ999")

    def test_a_paynow_mobile_note_is_kept_because_it_is_the_signal(self):
        assert cd.group_key("PayNow-Mobile to Jo OTHR-gold bar") != cd.group_key("PayNow-Mobile to Jo OTHR-shanghai trip")

    def test_the_card_payment_boilerplate_is_ignored(self):
        assert cd.group_key("MISTER MINIT ARC Card Payment") == cd.group_key("mister minit arc")

    def test_a_description_that_is_only_boilerplate_still_has_a_key(self):
        assert cd.group_key("Card Payment") == "card payment"


class TestAssignSplit:
    def test_it_depends_only_on_the_group_and_the_policy(self):
        assert cd.assign_split("fairprice", 3, POLICY) == cd.assign_split("fairprice", 3, POLICY)

    def test_a_different_seed_gives_a_different_assignment(self):
        groups = [f"merchant {i}" for i in range(200)]
        a = [cd.assign_split(g, 1, cd.SplitPolicy(seed=0)) for g in groups]
        b = [cd.assign_split(g, 1, cd.SplitPolicy(seed=1)) for g in groups]
        assert a != b

    def test_the_fractions_hold_over_many_descriptions(self):
        splits = [cd.assign_split(f"merchant {i}", 1, POLICY) for i in range(6000)]
        assert abs(splits.count("val") / 6000 - 0.15) < 0.02
        assert abs(splits.count("test") / 6000 - 0.15) < 0.02

    def test_a_dominant_description_is_train_only(self):
        policy = cd.SplitPolicy(max_eval_group_rows=50)
        assert all(cd.assign_split(f"merchant {i}", 50, policy) == "train" for i in range(300))
        assert {cd.assign_split(f"merchant {i}", 49, policy) for i in range(300)} == {"train", "val", "test"}

    def test_bad_fractions_are_refused(self):
        with pytest.raises(ValueError):
            cd.SplitPolicy(val_fraction=0.6, test_fraction=0.4)


class TestFolds:
    def test_a_description_never_crosses_folds(self):
        transactions = [labelled(f"MERCHANT {i % 40}") for i in range(400)]
        rows = cd.build_dataset(transactions, vectors_for(transactions), POLICY).rows
        folds_by_group = {}
        for row in rows:
            folds_by_group.setdefault(row["group"], set()).add(row["fold"])
        assert all(len(f) == 1 for f in folds_by_group.values())

    def test_the_folds_are_roughly_even_and_in_range(self):
        folds = [cd.assign_fold(f"merchant {i}", POLICY) for i in range(5000)]
        assert set(folds) == set(range(5))
        assert all(abs(folds.count(f) / 5000 - 0.2) < 0.03 for f in range(5))

    def test_a_fold_does_not_follow_from_the_split(self):
        pairs = {(cd.assign_split(f"m{i}", 1, POLICY), cd.assign_fold(f"m{i}", POLICY)) for i in range(2000)}
        assert len(pairs) == 15

    def test_adding_transactions_does_not_move_a_description_to_another_fold(self):
        assert cd.assign_fold("fairprice", POLICY) == cd.assign_fold("fairprice", cd.SplitPolicy(max_eval_group_rows=3))

    def test_one_fold_is_not_a_cross_validation(self):
        with pytest.raises(ValueError):
            cd.SplitPolicy(folds=1)


class TestBuildDataset:
    def test_a_description_never_crosses_splits(self):
        transactions = [labelled(f"MERCHANT {i % 40}") for i in range(400)]
        build = cd.build_dataset(transactions, vectors_for(transactions), POLICY)
        splits_by_group = {}
        for row in build.rows:
            splits_by_group.setdefault(row["group"], set()).add(row["split"])
        assert all(len(s) == 1 for s in splits_by_group.values())
        assert len({row["split"] for row in build.rows}) > 1

    def test_adding_transactions_does_not_move_the_ones_already_there(self):
        before = [labelled(f"MERCHANT {i}") for i in range(300)]
        after = before + [labelled(f"NEW MERCHANT {i}") for i in range(300)]
        split_before = {r["transaction_id"]: r["split"] for r in cd.build_dataset(before, vectors_for(before), POLICY).rows}
        split_after = {r["transaction_id"]: r["split"] for r in cd.build_dataset(after, vectors_for(after), POLICY).rows}
        assert all(split_after[i] == s for i, s in split_before.items())

    def test_rows_without_a_vector_or_with_unsure_are_counted_not_hidden(self):
        kept, no_vector, unsure = labelled("A"), labelled("B"), labelled("C", category="UNSURE")
        vectors = vectors_for([kept, unsure])
        vectors[str(uuid.uuid4())] = [0.1, 0.2, 0.3, 0.4]
        stats = cd.build_dataset([kept, no_vector, unsure], vectors, POLICY).stats
        assert (stats["rows_written"], stats["excluded_no_vector"], stats["excluded_unsure"], stats["vectors_without_a_transaction"]) == (1, 1, 1, 1)

    def test_rows_are_in_transaction_id_order_whatever_the_input_order(self):
        transactions = [labelled(f"M{i}") for i in range(20)]
        build = cd.build_dataset(list(reversed(transactions)), vectors_for(transactions), POLICY)
        ids = [r["transaction_id"] for r in build.rows]
        assert ids == sorted(ids)

    def test_the_label_and_where_it_came_from_are_kept(self):
        t = labelled("X", category="Groceries", source=CategorySource.LLM, suggested="Dining")
        row = cd.build_dataset([t], vectors_for([t]), POLICY).rows[0]
        assert (row["category"], row["label_source"], row["llm_suggested_category"]) == ("Groceries", "llm", "Dining")

    def test_inflows_are_marked_and_use_the_inflow_amount(self):
        t = labelled("Salary", category="Income", out_flow=None)
        row = cd.build_dataset([t], vectors_for([t]), POLICY).rows[0]
        assert (row["direction"], row["amount"]) == ("inflow", 5.0)

    def test_a_description_with_two_categories_is_flagged_as_a_label_conflict(self):
        a, b, c = labelled("PayNow to TINO", "Dining"), labelled("paynow to tino", "Others"), labelled("Mcdonalds", "Dining")
        rows = {r["transaction_id"]: r for r in cd.build_dataset([a, b, c], vectors_for([a, b, c]), POLICY).rows}
        assert rows[str(a.transaction_id)]["label_conflict"] and rows[str(b.transaction_id)]["label_conflict"]
        assert not rows[str(c.transaction_id)]["label_conflict"]

    def test_categories_that_cannot_be_measured_are_named(self):
        # one description per category: whichever split it lands in, the others are empty
        transactions = [labelled(f"unique merchant {i}", category=f"Cat{i}") for i in range(30)]
        stats = cd.build_dataset(transactions, vectors_for(transactions), POLICY).stats
        assert set(stats["categories_missing_from_val_or_test"]) == {f"Cat{i}" for i in range(30)}

    def test_categories_that_are_measured_by_only_a_few_rows_are_named_as_thin(self):
        transactions = [labelled(f"merchant {i}", "Big") for i in range(300)]
        thin = cd.build_dataset(transactions, vectors_for(transactions), cd.SplitPolicy(min_eval_rows=10_000)).stats
        sturdy = cd.build_dataset(transactions, vectors_for(transactions), cd.SplitPolicy(min_eval_rows=1)).stats
        assert thin["categories_thinly_measured"] == ["Big"]
        assert sturdy["categories_thinly_measured"] == [] and sturdy["categories_missing_from_val_or_test"] == []

    def test_categories_with_too_few_descriptions_to_hold_one_out_are_named(self):
        transactions = [labelled("same merchant", "Tiny") for _ in range(20)] + [labelled(f"merchant {i}", "Big") for i in range(20)]
        stats = cd.build_dataset(transactions, vectors_for(transactions), POLICY).stats
        assert stats["categories_with_fewer_than_3_descriptions"] == ["Tiny"]
        assert stats["rows_by_category"]["Tiny"]["descriptions"] == 1 and stats["rows_by_category"]["Big"]["descriptions"] == 20

    def test_vectors_of_different_sizes_are_refused(self):
        a, b = labelled("A"), labelled("B")
        with pytest.raises(ValueError, match="same size"):
            cd.build_dataset([a, b], {str(a.transaction_id): [0.1, 0.2], str(b.transaction_id): [0.1, 0.2, 0.3]}, POLICY)

    def test_a_non_finite_vector_is_refused(self):
        a = labelled("A")
        with pytest.raises(ValueError, match="non-finite"):
            cd.build_dataset([a], {str(a.transaction_id): [0.1, math.nan]}, POLICY)

    def test_nothing_usable_is_an_error_not_an_empty_file(self):
        with pytest.raises(ValueError, match="nothing to export"):
            cd.build_dataset([labelled("A")], {}, POLICY)


class _Qdrant(BaseHTTPRequestHandler):
    points: ClassVar[list] = []
    requests: ClassVar[list] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append((self.path, body))
        start = body.get("offset") or 0
        page = type(self).points[start : start + body["limit"]]
        nxt = start + body["limit"] if start + body["limit"] < len(type(self).points) else None
        payload = json.dumps({"result": {"points": page, "next_page_offset": nxt}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def qdrant():
    _Qdrant.points, _Qdrant.requests = [], []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Qdrant)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", _Qdrant
    server.shutdown()


class TestFetchEmbeddings:
    def test_every_page_is_read_and_vectors_are_asked_for(self, qdrant):
        url, state = qdrant
        state.points = [{"id": f"id-{i}", "vector": [float(i), 1.0]} for i in range(7)]
        vectors = cd.fetch_embeddings(url, page_size=3)
        assert vectors == {f"id-{i}": [float(i), 1.0] for i in range(7)}
        assert len(state.requests) == 3
        assert all(path == "/collections/transactions/points/scroll" and body["with_vector"] is True for path, body in state.requests)

    def test_named_vectors_are_refused_rather_than_misread(self, qdrant):
        url, state = qdrant
        state.points = [{"id": "a", "vector": {"dense": [0.1, 0.2]}}]
        with pytest.raises(ValueError, match="unnamed vector"):
            cd.fetch_embeddings(url)

    def test_an_unreachable_qdrant_is_an_error(self):
        with pytest.raises(OSError):
            cd.fetch_embeddings("http://127.0.0.1:9", timeout=1)


class TestWriteDataset:
    def build(self, n=60, dimensions=8):
        transactions = [labelled(f"MERCHANT {i % 25}", category=["Dining", "Interest", "Transport"][i % 3]) for i in range(n)]
        return cd.build_dataset(transactions, vectors_for(transactions, dimensions), POLICY), transactions

    def write(self, tmp_path, build):
        return cd.write_dataset(build, tmp_path / "out", source={"database": "db", "vectors": "q"}, embedding_model="gemini-embedding-2", policy=POLICY)

    def test_the_parquet_round_trips_with_the_vector_size_in_the_schema(self, tmp_path):
        build, _ = self.build(dimensions=8)
        self.write(tmp_path, build)
        table = pq.read_table(tmp_path / "out" / cd.DATASET_FILE)
        assert table.num_rows == len(build.rows)
        assert table.schema.field("embedding").type.list_size == 8
        first = table.to_pylist()[0]
        assert first["embedding"] == pytest.approx(build.rows[0]["embedding"], rel=1e-6)
        assert first["category"] == build.rows[0]["category"] and first["split"] == build.rows[0]["split"]

    def test_the_manifest_says_what_is_in_the_file(self, tmp_path):
        build, _ = self.build()
        manifest = self.write(tmp_path, build)
        on_disk = json.loads((tmp_path / "out" / cd.MANIFEST_FILE).read_text())
        assert on_disk["dataset_id"] == manifest["dataset_id"] == f"clf-{cd.content_hash(build.rows)[:12]}"
        assert on_disk["embedding"]["dimensions"] == 8 and on_disk["embedding"]["model_declared"] == "gemini-embedding-2"
        assert on_disk["stats"]["rows_written"] == len(build.rows)
        assert on_disk["files"][cd.DATASET_FILE]["bytes"] == (tmp_path / "out" / cd.DATASET_FILE).stat().st_size

    def test_the_same_data_has_the_same_identity_and_different_data_does_not(self, tmp_path):
        build, transactions = self.build()
        assert cd.content_hash(build.rows) == cd.content_hash(cd.build_dataset(transactions, vectors_for(transactions, 8), POLICY).rows)
        changed = dict(vectors_for(transactions, 8))
        changed[str(transactions[0].transaction_id)] = [9.0] * 8
        assert cd.content_hash(build.rows) != cd.content_hash(cd.build_dataset(transactions, changed, POLICY).rows)

    def test_a_relabelled_transaction_changes_the_identity(self):
        a = labelled("A", "Dining")
        before = cd.content_hash(cd.build_dataset([a], vectors_for([a]), POLICY).rows)
        b = LabelledTransaction(**{**a.__dict__, "category_name": "Others"})
        assert before != cd.content_hash(cd.build_dataset([b], vectors_for([b]), POLICY).rows)


class TestNotPublishable:
    def git(self, repo, *args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    def test_a_folder_git_would_track_is_refused(self, tmp_path):
        self.git(tmp_path, "init", "-q")
        with pytest.raises(SystemExit, match="Refusing to write"):
            cd.assert_not_publishable(tmp_path / "dataset")

    def test_a_git_ignored_folder_is_allowed(self, tmp_path):
        self.git(tmp_path, "init", "-q")
        (tmp_path / ".gitignore").write_text("data/\n")
        cd.assert_not_publishable(tmp_path / "data" / "classifier" / "run1")

    def test_outside_any_repository_is_allowed(self, tmp_path):
        cd.assert_not_publishable(tmp_path / "anywhere")

    def test_writing_is_refused_before_anything_is_created(self, tmp_path):
        self.git(tmp_path, "init", "-q")
        a = labelled("A")
        build = cd.build_dataset([a], vectors_for([a]), POLICY)
        with pytest.raises(SystemExit):
            cd.write_dataset(build, tmp_path / "dataset", source={}, embedding_model="m", policy=POLICY)
        assert not (tmp_path / "dataset").exists()

    def test_the_default_output_folder_is_git_ignored_in_this_repository(self):
        cd.assert_not_publishable(cd.DEFAULT_OUTPUT_ROOT / "clf-example")


def _category(db, name):
    category = Category(name=name, active=True, is_reserved=(name == "UNSURE"))
    db.add(category)
    db.flush()
    return category


def _transaction(db, description, category, source, suggested=None, description_amount="10.00"):
    statement = BankStatement(drive_file_id="f1", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32])
    db.add(statement)
    db.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 1),
        description=description,
        out_flow=Decimal(description_amount),
        currency="SGD",
        bank_name="OCBC Bank",
        category_id=category.id,
        category_source=source,
        converted_amount_sgd=Decimal(description_amount),
        llm_suggested_category_id=suggested.id if suggested else None,
    )
    db.add(txn)
    db.flush()
    return txn


class TestListLabelledTransactions:
    def test_every_transaction_comes_back_with_its_label_source_and_llm_suggestion(self, db_session):
        dining, groceries = _category(db_session, "Dining"), _category(db_session, "Groceries")
        for source in (CategorySource.MANUAL, CategorySource.SIMILARITY, CategorySource.LLM, CategorySource.UNSURE):
            _transaction(db_session, f"row {source.value}", dining, source)
        suggested = _transaction(db_session, "with suggestion", groceries, CategorySource.MANUAL, suggested=dining)

        rows = {r.description: r for r in repository.list_labelled_transactions(db_session)}

        assert {r.category_source for r in rows.values()} == set(CategorySource)
        assert rows["with suggestion"].llm_suggested_category_name == "Dining"
        assert rows["with suggestion"].category_name == "Groceries"
        assert rows["row manual"].llm_suggested_category_name is None
        assert rows["with suggestion"].transaction_id == suggested.id

    def test_the_order_is_by_id(self, db_session):
        cat = _category(db_session, "Dining")
        for i in range(5):
            _transaction(db_session, f"t{i}", cat, CategorySource.MANUAL)
        ids = [r.transaction_id for r in repository.list_labelled_transactions(db_session)]
        assert ids == sorted(ids)


def test_export_end_to_end(db_session, qdrant, tmp_path):
    url, state = qdrant
    cats = {n: _category(db_session, n) for n in ("Dining", "Interest", "UNSURE")}
    made = [_transaction(db_session, f"MERCHANT {i % 30}", cats["Dining" if i % 2 else "Interest"], CategorySource.MANUAL) for i in range(80)]
    unsure = _transaction(db_session, "WHO KNOWS", cats["UNSURE"], CategorySource.UNSURE)
    state.points = [{"id": str(t.id), "vector": [0.5, 0.25, 0.125]} for t in [*made, unsure]]

    manifest, out = cd.export_dataset(db_session, url, tmp_path / "out", POLICY, "gemini-embedding-2")

    table = pq.read_table(out / cd.DATASET_FILE)
    assert table.num_rows == 80
    assert set(table.column("category").to_pylist()) == {"Dining", "Interest"}
    assert manifest["stats"]["excluded_unsure"] == 1
    assert manifest["stats"]["rows_by_split"]["train"] > 0
