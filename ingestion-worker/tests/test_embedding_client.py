"""Tests for embedding/client.py's soft-fail behavior (WR-24/25/26, NFR-5).

No retry here (contrast test_openrouter_client.py's retry-on-transient-error
coverage) -- every failure class, transient or not, is soft-failed identically and
immediately, per the "No-Retry Immediate Soft-Fail" NFR Design pattern.
"""

from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, APITimeoutError

from ingestion_worker.clients.openrouter_client import GEMINI_OPENAI_BASE_URL
from ingestion_worker.embedding import client as embedding_client
from ingestion_worker.embedding import service as embedding_service
from ingestion_worker.embedding.client import GEMINI_TASK_PREFIX, compute_embedding


class TestComputeEmbedding:
    def test_returns_none_when_base_url_is_unset(self):
        with patch("ingestion_worker.embedding.client.settings.embedding_base_url", ""):
            assert compute_embedding("NTUC FAIRPRICE") is None

    def test_returns_vector_on_success(self):
        fake_response = MagicMock()
        fake_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = fake_response

        with (
            patch("ingestion_worker.embedding.client.settings.embedding_base_url", "http://host.docker.internal:8001/v1"),
            patch("ingestion_worker.embedding.client._client", return_value=fake_client),
        ):
            result = compute_embedding("NTUC FAIRPRICE")

        assert result == [0.1, 0.2, 0.3]

    def test_passes_text_through_raw_and_unnormalized(self):
        """WR-24: no normalize_reference_noise call anywhere in this path."""
        fake_response = MagicMock()
        fake_response.data = [MagicMock(embedding=[0.1])]
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = fake_response

        with (
            patch("ingestion_worker.embedding.client.settings.embedding_base_url", "http://host.docker.internal:8001/v1"),
            patch("ingestion_worker.embedding.client._client", return_value=fake_client),
        ):
            compute_embedding("PAYNOW OTHR-260102595543212111")

        fake_client.embeddings.create.assert_called_once()
        _, kwargs = fake_client.embeddings.create.call_args
        assert kwargs["input"] == "PAYNOW OTHR-260102595543212111"

    def test_connection_error_soft_fails_with_no_retry(self):
        fake_client = MagicMock()
        fake_client.embeddings.create.side_effect = APIConnectionError(request=MagicMock())

        with (
            patch("ingestion_worker.embedding.client.settings.embedding_base_url", "http://host.docker.internal:8001/v1"),
            patch("ingestion_worker.embedding.client._client", return_value=fake_client),
        ):
            result = compute_embedding("NTUC FAIRPRICE")

        assert result is None
        assert fake_client.embeddings.create.call_count == 1  # no retry, unlike openrouter_client.py

    def test_timeout_error_soft_fails(self):
        fake_client = MagicMock()
        fake_client.embeddings.create.side_effect = APITimeoutError(request=MagicMock())

        with (
            patch("ingestion_worker.embedding.client.settings.embedding_base_url", "http://host.docker.internal:8001/v1"),
            patch("ingestion_worker.embedding.client._client", return_value=fake_client),
        ):
            assert compute_embedding("NTUC FAIRPRICE") is None

    def test_empty_vector_response_soft_fails(self):
        fake_response = MagicMock()
        fake_response.data = [MagicMock(embedding=[])]
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = fake_response

        with (
            patch("ingestion_worker.embedding.client.settings.embedding_base_url", "http://host.docker.internal:8001/v1"),
            patch("ingestion_worker.embedding.client._client", return_value=fake_client),
        ):
            assert compute_embedding("NTUC FAIRPRICE") is None


class TestEmbeddingProvider:
    """`embedding_provider`: `local` is the configurable server, unchanged; `gemini` reuses the extraction key against
    Google's OpenAI-compatible endpoint, asks for embedding_dimensions-sized vectors and prefixes the task."""

    @pytest.fixture(autouse=True)
    def _distinct_values(self, monkeypatch):
        for name, value in (
            ("embedding_base_url", "http://host.docker.internal:8001/v1"), ("embedding_api_key", "local-embed-key"),
            ("embedding_model", "local-embed-model"), ("openrouter_api_key", "openrouter-key"),
            ("gemini_api_key", "gemini-key"), ("gemini_embedding_model", "gemini-embed-model"), ("embedding_dimensions", 4),
        ):
            monkeypatch.setattr(embedding_client.settings, name, value)

    def _fake(self, vector):
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=vector)])
        return fake_client

    def test_local_sends_exactly_the_model_and_the_raw_text_as_before(self, monkeypatch):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "local")
        fake_client = self._fake([0.1] * 7)  # a local server's vector length is not checked against the setting
        with patch("ingestion_worker.embedding.client._client", return_value=fake_client):
            assert compute_embedding("NTUC | $10 to $20") == [0.1] * 7
        assert fake_client.embeddings.create.call_args.kwargs == {"model": "local-embed-model", "input": "NTUC | $10 to $20"}

    def test_local_client_uses_the_configured_endpoint_key_and_short_timeout(self, monkeypatch):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "local")
        with patch("ingestion_worker.embedding.client.OpenAI") as openai_cls:
            embedding_client._client()
        assert openai_cls.call_args.kwargs == {"api_key": "local-embed-key", "base_url": "http://host.docker.internal:8001/v1", "timeout": 5.0}

    def test_gemini_client_uses_googles_endpoint_the_extraction_key_and_a_bounded_timeout(self, monkeypatch):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "gemini")
        with patch("ingestion_worker.embedding.client.OpenAI") as openai_cls:
            embedding_client._client()
        assert openai_cls.call_args.kwargs == {"api_key": "gemini-key", "base_url": GEMINI_OPENAI_BASE_URL, "timeout": 15.0}

    def test_gemini_asks_for_the_configured_size_and_prefixes_the_task(self, monkeypatch):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "gemini")
        fake_client = self._fake([0.1, 0.2, 0.3, 0.4])
        with patch("ingestion_worker.embedding.client._client", return_value=fake_client):
            assert compute_embedding("NTUC | $10 to $20") == [0.1, 0.2, 0.3, 0.4]
        assert fake_client.embeddings.create.call_args.kwargs == {
            "model": "gemini-embed-model", "input": GEMINI_TASK_PREFIX + "NTUC | $10 to $20", "dimensions": 4,
        }
        assert GEMINI_TASK_PREFIX == "task: classification | query: "

    def test_gemini_is_on_even_though_the_local_endpoint_is_empty(self, monkeypatch):
        """Blanking embedding_base_url switches the LOCAL server off; it must not switch the Gemini provider off."""
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "gemini")
        monkeypatch.setattr(embedding_client.settings, "embedding_base_url", "")
        with patch("ingestion_worker.embedding.client._client", return_value=self._fake([1.0, 0.0, 0.0, 0.0])):
            assert compute_embedding("NTUC") is not None

    def test_local_with_an_empty_endpoint_is_still_off_whatever_the_gemini_settings_are(self, monkeypatch):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "local")
        monkeypatch.setattr(embedding_client.settings, "embedding_base_url", "")
        assert compute_embedding("NTUC") is None

    @pytest.mark.parametrize("vector", [[0.1] * 3, [0.1] * 5, [0.1] * 3072])
    def test_gemini_vector_of_the_wrong_size_is_unavailable_not_stored(self, monkeypatch, vector):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "gemini")
        with patch("ingestion_worker.embedding.client._client", return_value=self._fake(vector)):
            assert compute_embedding("NTUC") is None  # the vector store would reject it; fall back to fuzzy text

    @pytest.mark.parametrize("error", [APIConnectionError(request=MagicMock()), APITimeoutError(request=MagicMock())])
    def test_gemini_failures_soft_fail_once_without_retry(self, monkeypatch, error):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "gemini")
        fake_client = MagicMock()
        fake_client.embeddings.create.side_effect = error
        with patch("ingestion_worker.embedding.client._client", return_value=fake_client):
            assert compute_embedding("NTUC") is None
        assert fake_client.embeddings.create.call_count == 1

    def test_stored_and_query_texts_get_the_same_prefix(self, monkeypatch):
        """The batch path (storage) and the single path (query) both go through compute_embedding."""
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "gemini")
        fake_client = self._fake([0.1, 0.2, 0.3, 0.4])
        with patch("ingestion_worker.embedding.client._client", return_value=fake_client):
            embedding_service._compute_embeddings_concurrently(["A | $1 to $5", "B | $5 to $10"])
            compute_embedding("C | $1 to $5")
        sent = sorted(c.kwargs["input"] for c in fake_client.embeddings.create.call_args_list)
        assert sent == sorted(GEMINI_TASK_PREFIX + t for t in ("A | $1 to $5", "B | $5 to $10", "C | $1 to $5"))
