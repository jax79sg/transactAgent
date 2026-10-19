"""Tests for embedding/vector_store.py's soft-fail behavior and the non-blocking
startup pattern (nfr-design-patterns.md). QdrantClient itself is mocked -- a real
Qdrant instance is exercised during Build and Test's live verification, not here
(same split this project already uses for e.g. drive_client.py's unit tests vs.
live Drive verification).
"""

from unittest.mock import MagicMock, patch

from ingestion_worker.embedding import vector_store


class TestEnsureCollections:
    def test_creates_missing_collections(self):
        fake_client = MagicMock()
        fake_client.get_collections.return_value = MagicMock(collections=[])

        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            vector_store.ensure_collections()

        created_names = {call.kwargs["collection_name"] for call in fake_client.create_collection.call_args_list}
        assert created_names == {vector_store.TRANSACTIONS_COLLECTION, vector_store.RECURRING_PAYMENT_NAMES_COLLECTION}

    def test_skips_collections_that_already_exist(self):
        fake_client = MagicMock()
        existing = MagicMock()
        existing.name = vector_store.TRANSACTIONS_COLLECTION
        fake_client.get_collections.return_value = MagicMock(collections=[existing])

        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            vector_store.ensure_collections()

        created_names = {call.kwargs["collection_name"] for call in fake_client.create_collection.call_args_list}
        assert created_names == {vector_store.RECURRING_PAYMENT_NAMES_COLLECTION}

    def test_never_raises_when_qdrant_is_unreachable(self):
        """Non-Blocking Vector Store Startup pattern -- FR-10's soft-dependency
        framing covers this project's own Qdrant container too, not just oMLX."""
        with patch("ingestion_worker.embedding.vector_store._client", side_effect=ConnectionError("refused")):
            vector_store.ensure_collections()  # must not raise


class TestUpsertEmbedding:
    def test_returns_true_on_success(self):
        fake_client = MagicMock()
        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            assert vector_store.upsert_embedding("transactions", "abc-123", [0.1, 0.2]) is True
        fake_client.upsert.assert_called_once()

    def test_returns_false_never_raises_on_failure(self):
        fake_client = MagicMock()
        fake_client.upsert.side_effect = ConnectionError("refused")
        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            assert vector_store.upsert_embedding("transactions", "abc-123", [0.1, 0.2]) is False


class TestQueryNearestNeighbors:
    def _fake_point(self, point_id, score):
        point = MagicMock()
        point.id = point_id
        point.score = score
        return point

    def test_returns_neighbors_nearest_first(self):
        fake_client = MagicMock()
        fake_client.query_points.return_value = MagicMock(
            points=[self._fake_point("a", 0.9), self._fake_point("b", 0.8)]
        )
        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            result = vector_store.query_nearest_neighbors([0.1], collection="transactions", top_k=5)

        assert result == [("a", 0.9), ("b", 0.8)]

    def test_excludes_the_given_entity_id(self):
        fake_client = MagicMock()
        fake_client.query_points.return_value = MagicMock(
            points=[self._fake_point("self", 1.0), self._fake_point("other", 0.8)]
        )
        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            result = vector_store.query_nearest_neighbors(
                [0.1], collection="transactions", top_k=5, exclude_entity_id="self"
            )

        assert result == [("other", 0.8)]

    def test_returns_none_never_raises_when_unavailable(self):
        with patch("ingestion_worker.embedding.vector_store._client", side_effect=ConnectionError("refused")):
            assert vector_store.query_nearest_neighbors([0.1], collection="transactions", top_k=5) is None

    def test_empty_result_is_distinct_from_unavailable(self):
        fake_client = MagicMock()
        fake_client.query_points.return_value = MagicMock(points=[])
        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            result = vector_store.query_nearest_neighbors([0.1], collection="transactions", top_k=5)

        assert result == []
        assert result is not None


class TestRecreateTransactionsCollection:
    """Epic 13 (WR-52): the backfill wipes every in-scope transaction, so the whole
    `transactions` collection is orphaned and is recreated empty."""

    def test_drops_and_recreates_only_the_transactions_collection(self):
        fake_client = MagicMock()
        both = [MagicMock(), MagicMock()]
        both[0].name, both[1].name = vector_store.TRANSACTIONS_COLLECTION, vector_store.RECURRING_PAYMENT_NAMES_COLLECTION
        fake_client.get_collections.return_value = MagicMock(collections=both)

        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            assert vector_store.recreate_transactions_collection() is True

        fake_client.delete_collection.assert_called_once_with(collection_name=vector_store.TRANSACTIONS_COLLECTION)
        created = [c.kwargs["collection_name"] for c in fake_client.create_collection.call_args_list]
        assert created == [vector_store.TRANSACTIONS_COLLECTION]  # the recurring-payment collection is untouched

    def test_creates_it_when_it_does_not_exist_yet(self):
        fake_client = MagicMock()
        fake_client.get_collections.return_value = MagicMock(collections=[])

        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            assert vector_store.recreate_transactions_collection() is True

        fake_client.delete_collection.assert_not_called()
        assert fake_client.create_collection.call_count == 1

    def test_returns_false_and_never_raises_when_qdrant_is_unreachable(self):
        with patch("ingestion_worker.embedding.vector_store._client", side_effect=ConnectionError("refused")):
            assert vector_store.recreate_transactions_collection() is False


class TestDeleteEmbeddings:
    """Epic 14 (WR-68): used only by the Statement Removal Handler."""

    def test_deletes_the_given_points_from_the_given_collection(self):
        fake_client = MagicMock()
        ids = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]

        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            assert vector_store.delete_embeddings(vector_store.TRANSACTIONS_COLLECTION, ids) is True

        call = fake_client.delete.call_args.kwargs
        assert call["collection_name"] == vector_store.TRANSACTIONS_COLLECTION
        assert call["points_selector"].points == ids  # the ids pass through unchanged

    def test_an_empty_list_is_a_successful_no_op(self):
        fake_client = MagicMock()

        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            assert vector_store.delete_embeddings(vector_store.TRANSACTIONS_COLLECTION, []) is True

        fake_client.delete.assert_not_called()

    def test_returns_false_and_never_raises_when_the_delete_fails(self):
        fake_client = MagicMock()
        fake_client.delete.side_effect = ConnectionError("refused")

        with patch("ingestion_worker.embedding.vector_store._client", return_value=fake_client):
            assert vector_store.delete_embeddings(vector_store.TRANSACTIONS_COLLECTION, ["x"]) is False

    def test_returns_false_and_never_raises_when_the_client_cannot_be_created(self):
        with patch("ingestion_worker.embedding.vector_store._client", side_effect=ConnectionError("refused")):
            assert vector_store.delete_embeddings(vector_store.TRANSACTIONS_COLLECTION, ["x"]) is False

