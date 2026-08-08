"""Tests for openrouter_client.py's timeout configuration and exception mapping.

Regression coverage for a real incident (2026-08-04, see aidlc-docs/audit.md): a
categorization call to a local model server hung for 9+ hours with no timeout ever
firing, leaving the whole single-worker ingestion run stuck. Two distinct bugs
contributed: (1) no explicit request timeout was configured, relying on the SDK
default which never fired in practice; (2) even when a timeout DOES fire, the old
`except (TimeoutError, ConnectionError)` clause never matched openai's actual
exception classes (APITimeoutError/APIConnectionError, which do NOT inherit from
the builtins), so it fell straight through retry_with_backoff (which only retries
TransientError) to categorization/llm_classifier.py's catch-all -- giving up as
UNSURE after zero retries instead of retrying a transient blip.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from ingestion_worker.clients.openrouter_client import _REQUEST_TIMEOUT_SECONDS, _client, classify_description
from ingestion_worker.clients.retry import TransientError


class TestClientTimeout:
    def test_client_is_constructed_with_an_explicit_timeout(self):
        client = _client()
        assert client.timeout == _REQUEST_TIMEOUT_SECONDS


class TestExceptionMapping:
    def _fake_request(self):
        return httpx.Request("POST", "http://host.docker.internal:8000/v1/chat/completions")

    def test_api_timeout_error_becomes_transient_and_is_retried(self):
        error = APITimeoutError(request=self._fake_request())
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = error

        with (
            patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client),
            patch("ingestion_worker.clients.retry.time.sleep"),
            pytest.raises(TransientError),
        ):
            classify_description("NTUC FAIRPRICE", ["Groceries"])

        # retry_with_backoff's default max_attempts (3) -- proves it actually retried,
        # not just mapped-and-immediately-gave-up.
        assert fake_client.chat.completions.create.call_count == 3

    def test_api_connection_error_becomes_transient_and_is_retried(self):
        error = APIConnectionError(request=self._fake_request())
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = error

        with (
            patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client),
            patch("ingestion_worker.clients.retry.time.sleep"),
            pytest.raises(TransientError),
        ):
            classify_description("NTUC FAIRPRICE", ["Groceries"])

        assert fake_client.chat.completions.create.call_count == 3

    def test_would_have_given_up_after_one_attempt_without_the_fix(self):
        # Prove the test actually catches the regression: simulating the old except
        # clause (builtin TimeoutError/ConnectionError only) against a real
        # APITimeoutError shows it doesn't match -- the exception propagates
        # unconverted, past retry_with_backoff (only retries TransientError),
        # after a single attempt.
        error = APITimeoutError(request=self._fake_request())
        assert not isinstance(error, (TimeoutError, ConnectionError))
