"""Issue #28 (Costs page): an Ask AI call is recorded once with its tokens and the configured prices; a failed call
is not; and recording can never break the answer."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from transactagent_db import model_usage as shared
from transactagent_db.models import ModelUsage

from api_service import usage
from api_service.ai_assistant import gemini_client
from api_service.errors import AiServiceUnavailableError

# Distinct prices, so a call priced with the wrong one shows up in the recorded fields.
_IN, _OUT = 0.31, 2.52


@pytest.fixture(autouse=True)
def _prices(monkeypatch):
    monkeypatch.setattr(usage.settings, "gemini_input_price_per_million_usd", _IN)
    monkeypatch.setattr(usage.settings, "gemini_output_price_per_million_usd", _OUT)


def _response(prompt=5000, candidates=250, thoughts=None, with_usage=True):
    usage_metadata = (
        SimpleNamespace(
            prompt_token_count=prompt, candidates_token_count=candidates, thoughts_token_count=thoughts,
            total_token_count=prompt + candidates + (thoughts or 0),
        )
        if with_usage
        else None
    )
    return SimpleNamespace(text="You spent $25.50.", usage_metadata=usage_metadata)


def _client(response=None, error=None):
    client = MagicMock()
    if error is not None:
        client.models.generate_content.side_effect = error
    else:
        client.models.generate_content.return_value = response
    return client


class TestAskAiRecording:
    def test_a_successful_answer_is_recorded_with_its_tokens_model_and_prices(self, recorded_usage):
        with patch.object(gemini_client, "_client", return_value=_client(_response(5000, 250))):
            answer = gemini_client.ask_gemini("question", model="gemini-test")

        assert answer == "You spent $25.50."
        (rec,) = recorded_usage
        assert rec["purpose"] == "ask_ai"
        assert rec["model"] == "gemini-test"
        assert (rec["input_tokens"], rec["output_tokens"]) == (5000, 250)
        assert (rec["input_price_per_million"], rec["output_price_per_million"]) == (_IN, _OUT)

    def test_the_default_model_is_the_configured_one(self, recorded_usage, monkeypatch):
        monkeypatch.setattr(gemini_client.settings, "gemini_model", "the-configured-model")
        with patch.object(gemini_client, "_client", return_value=_client(_response())):
            gemini_client.ask_gemini("question")

        assert recorded_usage[0]["model"] == "the-configured-model"

    def test_thinking_tokens_are_part_of_the_output(self, recorded_usage):
        with patch.object(gemini_client, "_client", return_value=_client(_response(100, 20, 300))):
            gemini_client.ask_gemini("question", model="m")

        assert (recorded_usage[0]["input_tokens"], recorded_usage[0]["output_tokens"]) == (100, 320)

    def test_a_response_without_usage_records_nothing_but_still_answers(self, recorded_usage):
        with patch.object(gemini_client, "_client", return_value=_client(_response(with_usage=False))):
            assert gemini_client.ask_gemini("question", model="m") == "You spent $25.50."

        assert recorded_usage == []

    def test_a_failed_call_is_not_recorded(self, recorded_usage):
        with patch.object(gemini_client, "_client", return_value=_client(error=TimeoutError("slow"))), pytest.raises(
            AiServiceUnavailableError
        ):
            gemini_client.ask_gemini("question", model="m")

        assert recorded_usage == []


class TestRecorderItself:
    @pytest.fixture
    def real_recorder(self, monkeypatch):
        monkeypatch.setattr(usage, "record_model_usage", shared.record_model_usage)

    def test_a_recording_failure_never_breaks_the_answer(self, real_recorder, monkeypatch, caplog):
        def broken():
            raise RuntimeError("database is down")

        monkeypatch.setattr(usage, "SessionLocal", broken)
        with patch.object(gemini_client, "_client", return_value=_client(_response())):
            assert gemini_client.ask_gemini("question", model="m") == "You spent $25.50."

        assert "Could not record ask_ai model usage" in caplog.text

    def test_a_call_leaves_a_row_with_the_cost_worked_out_from_the_settings_prices(self, real_recorder, engine, monkeypatch):
        monkeypatch.setattr(usage, "SessionLocal", sessionmaker(bind=engine))
        with patch.object(gemini_client, "_client", return_value=_client(_response(2_000_000, 1_000_000))):
            gemini_client.ask_gemini("question", model="gemini-cost-test")

        with sessionmaker(bind=engine)() as session:
            rows = list(session.scalars(select(ModelUsage).where(ModelUsage.model == "gemini-cost-test")))
            try:
                assert len(rows) == 1
                assert rows[0].purpose == "ask_ai"
                assert float(rows[0].cost_usd) == pytest.approx(3.14)  # 2M x 0.31 + 1M x 2.52
            finally:
                for row in rows:
                    session.delete(row)
                session.commit()
