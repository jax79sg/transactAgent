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

from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from ingestion_worker.clients import openrouter_client
from ingestion_worker.clients.openrouter_client import (
    _REQUEST_TIMEOUT_SECONDS,
    GEMINI_OPENAI_BASE_URL,
    _client,
    classify_description,
    classify_descriptions_batch,
)
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
            classify_description("NTUC FAIRPRICE", Decimal("45.20"), ["Groceries"])

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
            classify_description("NTUC FAIRPRICE", Decimal("45.20"), ["Groceries"])

        assert fake_client.chat.completions.create.call_count == 3

    def test_would_have_given_up_after_one_attempt_without_the_fix(self):
        # Prove the test actually catches the regression: simulating the old except
        # clause (builtin TimeoutError/ConnectionError only) against a real
        # APITimeoutError shows it doesn't match -- the exception propagates
        # unconverted, past retry_with_backoff (only retries TransientError),
        # after a single attempt.
        error = APITimeoutError(request=self._fake_request())
        assert not isinstance(error, (TimeoutError, ConnectionError))


class TestClassifyDescriptionsBatch:
    """WR-27 (Matching Precision Refinement, revised 2026-08-16): same
    retry/exception-mapping behavior as classify_description, applied to the
    multi-description batch prompt call added to reduce round-trips to the local
    model server for a large statement."""

    def test_prompt_includes_every_description_and_all_categories(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='["Groceries", "Dining"]'))
        ]

        with patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client):
            result = classify_descriptions_batch(
                [("NTUC FAIRPRICE", Decimal("45.20")), ("STARBUCKS", Decimal("6.50"))], ["Groceries", "Dining"]
            )

        assert result == '["Groceries", "Dining"]'
        prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "NTUC FAIRPRICE" in prompt
        assert "STARBUCKS" in prompt
        assert "Groceries" in prompt
        assert "Dining" in prompt

    def test_api_timeout_error_becomes_transient_and_is_retried(self):
        error = APITimeoutError(request=self._fake_request())
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = error

        with (
            patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client),
            patch("ingestion_worker.clients.retry.time.sleep"),
            pytest.raises(TransientError),
        ):
            classify_descriptions_batch([("NTUC FAIRPRICE", Decimal("45.20"))], ["Groceries"])

        assert fake_client.chat.completions.create.call_count == 3

    def _fake_request(self):
        return httpx.Request("POST", "http://host.docker.internal:8000/v1/chat/completions")


class TestAmountInPrompt:
    """WR-34 (Categorization Model Fine-Tuning): the converted SGD amount is now
    part of the categorization prompt, both single and batch, so the live prompt's
    input shape matches what the Model Training unit trains against."""

    def test_classify_description_includes_amount(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="Groceries"))]

        with patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client):
            classify_description("NTUC FAIRPRICE", Decimal("45.20"), ["Groceries"])

        prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "45.20 SGD" in prompt

    def test_classify_description_renders_none_amount_as_unknown(self):
        """WR-6: conversion can be unavailable for a transaction -- the prompt must
        still be well-formed, not crash on a None amount."""
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="Groceries"))]

        with patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client):
            classify_description("NTUC FAIRPRICE", None, ["Groceries"])

        prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "unknown" in prompt

    def test_classify_descriptions_batch_includes_every_amount(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='["Groceries", "Dining"]'))
        ]

        with patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client):
            classify_descriptions_batch(
                [("NTUC FAIRPRICE", Decimal("45.20")), ("STARBUCKS", None)], ["Groceries", "Dining"]
            )

        prompt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "45.20 SGD" in prompt
        assert "unknown" in prompt


class TestCategorizationProvider:
    """`categorization_provider` chooses where categorization goes: `local` is the configurable OpenAI-compatible
    endpoint (unchanged); `gemini` reuses the extraction key and model against Google's OpenAI-compatible endpoint."""

    @pytest.fixture(autouse=True)
    def _distinct_values(self, monkeypatch):
        for name, value in (
            ("openrouter_base_url", "http://host.docker.internal:8000/v1"), ("openrouter_api_key", "local-key"),
            ("openrouter_model", "local-model"), ("gemini_api_key", "gemini-key"), ("gemini_model", "gemini-model"),
        ):
            monkeypatch.setattr(openrouter_client.settings, name, value)

    def _fake(self, content='["Groceries"]'):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content=content))]
        return fake_client

    def test_local_is_the_default_and_uses_the_configured_endpoint_key_and_model(self, monkeypatch):
        monkeypatch.setattr(openrouter_client.settings, "categorization_provider", "local")
        with patch("ingestion_worker.clients.openrouter_client.OpenAI") as openai_cls:
            _client()
        assert openai_cls.call_args.kwargs["base_url"] == "http://host.docker.internal:8000/v1"
        assert openai_cls.call_args.kwargs["api_key"] == "local-key"

    def test_gemini_uses_googles_endpoint_with_the_extraction_key(self, monkeypatch):
        monkeypatch.setattr(openrouter_client.settings, "categorization_provider", "gemini")
        with patch("ingestion_worker.clients.openrouter_client.OpenAI") as openai_cls:
            _client()
        assert openai_cls.call_args.kwargs["base_url"] == GEMINI_OPENAI_BASE_URL
        assert GEMINI_OPENAI_BASE_URL == "https://generativelanguage.googleapis.com/v1beta/openai/"
        assert openai_cls.call_args.kwargs["api_key"] == "gemini-key"
        assert openai_cls.call_args.kwargs["timeout"] == _REQUEST_TIMEOUT_SECONDS  # the bounded timeout applies to both

    @pytest.mark.parametrize(("provider", "model"), [("local", "local-model"), ("gemini", "gemini-model")])
    def test_a_batch_request_names_the_providers_model(self, monkeypatch, provider, model):
        monkeypatch.setattr(openrouter_client.settings, "categorization_provider", provider)
        fake_client = self._fake()
        with patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client):
            classify_descriptions_batch([("NTUC", Decimal("1.00"))], ["Groceries"])
        assert fake_client.chat.completions.create.call_args.kwargs["model"] == model

    @pytest.mark.parametrize(("provider", "model"), [("local", "local-model"), ("gemini", "gemini-model")])
    def test_a_single_request_names_the_providers_model(self, monkeypatch, provider, model):
        monkeypatch.setattr(openrouter_client.settings, "categorization_provider", provider)
        fake_client = self._fake("Groceries")
        with patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client):
            classify_description("NTUC", Decimal("1.00"), ["Groceries"])
        assert fake_client.chat.completions.create.call_args.kwargs["model"] == model

    def test_an_explicit_model_argument_still_wins(self, monkeypatch):
        monkeypatch.setattr(openrouter_client.settings, "categorization_provider", "gemini")
        fake_client = self._fake()
        with patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client):
            classify_descriptions_batch([("NTUC", None)], ["Groceries"], model="something-else")
        assert fake_client.chat.completions.create.call_args.kwargs["model"] == "something-else"

    def test_the_request_is_the_same_prompt_and_temperature_for_both_providers(self, monkeypatch):
        sent = {}
        for provider in ("local", "gemini"):
            monkeypatch.setattr(openrouter_client.settings, "categorization_provider", provider)
            fake_client = self._fake()
            with patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client):
                classify_descriptions_batch([("NTUC", Decimal("1.00"))], ["Groceries"])
            kwargs = fake_client.chat.completions.create.call_args.kwargs
            sent[provider] = (kwargs["messages"], kwargs["temperature"], sorted(set(kwargs) - {"model"}))
        assert sent["local"] == sent["gemini"]  # swapping the provider changes where, never what

    def test_an_error_names_the_endpoint_that_was_actually_called(self, monkeypatch):
        monkeypatch.setattr(openrouter_client.settings, "categorization_provider", "gemini")
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = APIConnectionError(
            request=httpx.Request("POST", GEMINI_OPENAI_BASE_URL + "chat/completions")
        )
        with (
            patch("ingestion_worker.clients.openrouter_client._client", return_value=fake_client),
            patch("ingestion_worker.clients.retry.time.sleep"),
            pytest.raises(TransientError, match=r"generativelanguage\.googleapis\.com"),
        ):
            classify_description("NTUC", Decimal("1.00"), ["Groceries"])
