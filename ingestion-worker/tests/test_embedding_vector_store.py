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
