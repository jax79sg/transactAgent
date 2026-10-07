"""Issue #28 (Costs page): each paid Gemini call is recorded once, with the right purpose, model, tokens and price;
free (local) calls and failed calls are not; and recording can never break the call it describes."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from transactagent_db import model_usage as shared
from transactagent_db.models import ModelUsage

from ingestion_worker import usage
from ingestion_worker.clients import gemini_client, openrouter_client
from ingestion_worker.embedding import client as embedding_client

# Distinct prices, so a call priced with the wrong one of the three shows up in the recorded fields.
_IN, _OUT, _EMB = 0.31, 2.52, 0.23


@pytest.fixture(autouse=True)
def _prices(monkeypatch):
    monkeypatch.setattr(usage.settings, "gemini_input_price_per_million_usd", _IN)
    monkeypatch.setattr(usage.settings, "gemini_output_price_per_million_usd", _OUT)
    monkeypatch.setattr(usage.settings, "gemini_embedding_price_per_million_usd", _EMB)


def _genai_response(prompt=1200, candidates=80, thoughts=None, with_usage=True):
    usage_metadata = (
        SimpleNamespace(
            prompt_token_count=prompt, candidates_token_count=candidates, thoughts_token_count=thoughts,
            total_token_count=prompt + candidates + (thoughts or 0),
        )
        if with_usage
        else None
    )
    return SimpleNamespace(text="[]", usage_metadata=usage_metadata)


def _fake_genai_client(response=None, error=None):
    client = MagicMock()
    if error is not None:
        client.models.generate_content.side_effect = error
    else:
        client.models.generate_content.return_value = response
    return client


def _chat_response(prompt=300, completion=20, content="Dining", with_usage=True):
    usage_obj = (
        SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion)
        if with_usage
        else None
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage_obj)


def _fake_chat_client(response):
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _fake_embedding_client(vector):
    client = MagicMock()
    client.embeddings.create.return_value = SimpleNamespace(data=[SimpleNamespace(embedding=vector)])
    return client


class TestStatementExtraction:
    def test_a_successful_call_is_recorded_with_its_tokens_prices_and_model(self, recorded_usage):
        with patch.object(gemini_client, "_client", return_value=_fake_genai_client(_genai_response(1200, 80))):
            gemini_client.extract_statement_raw([b"page"], "prompt", model="gemini-test")

        (rec,) = recorded_usage
        assert rec["purpose"] == "statement_extraction"
        assert rec["model"] == "gemini-test"
        assert (rec["input_tokens"], rec["output_tokens"]) == (1200, 80)
        assert (rec["input_price_per_million"], rec["output_price_per_million"]) == (_IN, _OUT)
        assert not rec.get("tokens_estimated")

    def test_the_default_model_is_the_one_recorded(self, recorded_usage, monkeypatch):
        monkeypatch.setattr(gemini_client.settings, "gemini_model", "the-configured-model")
        with patch.object(gemini_client, "_client", return_value=_fake_genai_client(_genai_response())):
            gemini_client.extract_statement_raw([b"page"], "prompt")

        assert recorded_usage[0]["model"] == "the-configured-model"

    def test_thinking_tokens_are_part_of_the_output(self, recorded_usage):
        with patch.object(gemini_client, "_client", return_value=_fake_genai_client(_genai_response(100, 20, 300))):
            gemini_client.extract_statement_raw([b"page"], "prompt", model="m")

        assert (recorded_usage[0]["input_tokens"], recorded_usage[0]["output_tokens"]) == (100, 320)

    def test_a_response_without_usage_records_nothing_but_still_returns_its_text(self, recorded_usage):
        with patch.object(gemini_client, "_client", return_value=_fake_genai_client(_genai_response(with_usage=False))):
            text = gemini_client.extract_statement_raw([b"page"], "prompt", model="m")

        assert text == "[]"
        assert recorded_usage == []

    def test_a_failed_call_is_not_recorded(self, recorded_usage):
        failing = _fake_genai_client(error=ValueError("rejected"))
        with patch.object(gemini_client, "_client", return_value=failing), pytest.raises(ValueError):
            gemini_client.extract_statement_raw([b"page"], "prompt", model="m")

        assert recorded_usage == []


class TestCategorization:
    @pytest.fixture
    def gemini_provider(self, monkeypatch):
        monkeypatch.setattr(openrouter_client.settings, "categorization_provider", "gemini")

    def test_a_single_classification_is_recorded(self, recorded_usage, gemini_provider):
        with patch.object(openrouter_client, "_client", return_value=_fake_chat_client(_chat_response(300, 20))):
            answer = openrouter_client.classify_description("NTUC", None, ["Groceries"], model="gemini-test")

        assert answer == "Dining"
        (rec,) = recorded_usage
        assert rec["purpose"] == "categorization"
        assert rec["model"] == "gemini-test"
        assert (rec["input_tokens"], rec["output_tokens"]) == (300, 20)
        assert (rec["input_price_per_million"], rec["output_price_per_million"]) == (_IN, _OUT)

    def test_a_batch_classification_is_recorded_once_for_the_one_call(self, recorded_usage, gemini_provider):
        with patch.object(openrouter_client, "_client", return_value=_fake_chat_client(_chat_response(900, 60))):
            openrouter_client.classify_descriptions_batch([("A", None), ("B", None)], ["Groceries"], model="m")

        (rec,) = recorded_usage
        assert (rec["purpose"], rec["input_tokens"], rec["output_tokens"]) == ("categorization", 900, 60)

    def test_the_default_model_is_the_geminis_one(self, recorded_usage, gemini_provider, monkeypatch):
        monkeypatch.setattr(openrouter_client.settings, "gemini_model", "the-gemini-model")
        with patch.object(openrouter_client, "_client", return_value=_fake_chat_client(_chat_response())):
            openrouter_client.classify_description("NTUC", None, ["Groceries"])

        assert recorded_usage[0]["model"] == "the-gemini-model"

    def test_the_local_provider_costs_nothing_and_is_not_recorded(self, recorded_usage, monkeypatch):
        monkeypatch.setattr(openrouter_client.settings, "categorization_provider", "local")
        with patch.object(openrouter_client, "_client", return_value=_fake_chat_client(_chat_response())):
            openrouter_client.classify_description("NTUC", None, ["Groceries"], model="m")
            openrouter_client.classify_descriptions_batch([("A", None)], ["Groceries"], model="m")

        assert recorded_usage == []

    def test_a_response_without_usage_records_nothing_but_still_answers(self, recorded_usage, gemini_provider):
        with patch.object(openrouter_client, "_client", return_value=_fake_chat_client(_chat_response(with_usage=False))):
            answer = openrouter_client.classify_description("NTUC", None, ["Groceries"], model="m")

        assert answer == "Dining"
        assert recorded_usage == []

    def test_a_failed_call_is_not_recorded(self, recorded_usage, gemini_provider):
        client = MagicMock()
        client.chat.completions.create.side_effect = ValueError("boom")
        with patch.object(openrouter_client, "_client", return_value=client), pytest.raises(ValueError):
            openrouter_client.classify_description("NTUC", None, ["Groceries"], model="m")

        assert recorded_usage == []


class TestEmbeddings:
    @pytest.fixture
    def gemini_provider(self, monkeypatch):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "gemini")
        monkeypatch.setattr(embedding_client.settings, "embedding_dimensions", 3)
        monkeypatch.setattr(embedding_client.settings, "gemini_embedding_model", "gemini-embedding-test")

    def test_a_gemini_embedding_is_recorded_as_an_estimate_at_the_embedding_price(self, recorded_usage, gemini_provider):
        with patch.object(embedding_client, "_client", return_value=_fake_embedding_client([0.1, 0.2, 0.3])):
            embedding_client.compute_embedding("NTUC FAIRPRICE 123")

        (rec,) = recorded_usage
        sent = embedding_client.GEMINI_TASK_PREFIX + "NTUC FAIRPRICE 123"
        assert rec["purpose"] == "embedding"
        assert rec["model"] == "gemini-embedding-test"
        assert rec["input_tokens"] == shared.estimate_tokens(sent)  # what was actually sent, prefix included
        assert rec["output_tokens"] == 0
        assert rec["tokens_estimated"] is True
        assert (rec["input_price_per_million"], rec["output_price_per_million"]) == (_EMB, 0.0)

    def test_the_local_provider_is_free_and_not_recorded(self, recorded_usage, monkeypatch):
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "local")
        monkeypatch.setattr(embedding_client.settings, "embedding_base_url", "http://localhost:1/v1")
        with patch.object(embedding_client, "_client", return_value=_fake_embedding_client([0.1, 0.2, 0.3])):
            embedding_client.compute_embedding("NTUC")

        assert recorded_usage == []

    def test_an_unreachable_endpoint_is_not_recorded(self, recorded_usage, gemini_provider):
        client = MagicMock()
        client.embeddings.create.side_effect = ConnectionError("down")
        with patch.object(embedding_client, "_client", return_value=client):
            assert embedding_client.compute_embedding("NTUC") is None

        assert recorded_usage == []

    def test_a_billed_call_whose_vector_is_then_rejected_is_still_recorded(self, recorded_usage, gemini_provider):
        """Google billed the request even though the wrong-sized vector is treated as unavailable."""
        with patch.object(embedding_client, "_client", return_value=_fake_embedding_client([0.1, 0.2])):
            assert embedding_client.compute_embedding("NTUC") is None

        assert len(recorded_usage) == 1


class TestRecorderItself:
    """The real recorder, put back, against the real thing it wraps."""

    @pytest.fixture
    def real_recorder(self, monkeypatch):
        monkeypatch.setattr(usage, "record_model_usage", shared.record_model_usage)

    def test_a_recording_failure_never_breaks_the_call_it_describes(self, real_recorder, monkeypatch, caplog):
        def broken():
            raise RuntimeError("database is down")

        monkeypatch.setattr(usage, "SessionLocal", broken)
        monkeypatch.setattr(embedding_client.settings, "embedding_provider", "gemini")
        monkeypatch.setattr(embedding_client.settings, "embedding_dimensions", 3)
        with patch.object(embedding_client, "_client", return_value=_fake_embedding_client([0.1, 0.2, 0.3])):
            assert embedding_client.compute_embedding("NTUC") == [0.1, 0.2, 0.3]

        assert "Could not record embedding model usage" in caplog.text

    def test_a_call_leaves_a_row_with_the_cost_worked_out_from_the_settings_prices(self, real_recorder, engine, monkeypatch):
        monkeypatch.setattr(usage, "SessionLocal", sessionmaker(bind=engine))
        with patch.object(gemini_client, "_client", return_value=_fake_genai_client(_genai_response(2_000_000, 1_000_000))):
            gemini_client.extract_statement_raw([b"page"], "prompt", model="gemini-cost-test")

        with sessionmaker(bind=engine)() as session:
            rows = list(session.scalars(select(ModelUsage).where(ModelUsage.model == "gemini-cost-test")))
            try:
                assert len(rows) == 1
                # 2M input at 0.31 + 1M output at 2.52 = 0.62 + 2.52
                assert float(rows[0].cost_usd) == pytest.approx(3.14)
            finally:
                for row in rows:
                    session.delete(row)
                session.commit()
