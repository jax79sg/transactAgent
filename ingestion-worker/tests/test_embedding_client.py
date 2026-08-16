"""Tests for embedding/client.py's soft-fail behavior (WR-24/25/26, NFR-5).

No retry here (contrast test_openrouter_client.py's retry-on-transient-error
coverage) -- every failure class, transient or not, is soft-failed identically and
immediately, per the "No-Retry Immediate Soft-Fail" NFR Design pattern.
"""

from unittest.mock import MagicMock, patch

from openai import APIConnectionError, APITimeoutError

from ingestion_worker.embedding.client import compute_embedding


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
