"""The shared recording module (issue #28): the cost arithmetic, the token estimate, and the rule that recording is
bookkeeping that can never fail or undo the call it describes."""

import random
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from transactagent_db.model_usage import (
    PURPOSE_ASK_AI,
    PURPOSE_CATEGORIZATION,
    PURPOSE_EMBEDDING,
    PURPOSE_STATEMENT_EXTRACTION,
    PURPOSES,
    compute_cost_usd,
    estimate_tokens,
    record_model_usage,
    tokens_from_genai_usage,
    tokens_from_openai_usage,
)
from transactagent_db.models import ModelUsage


class TestComputeCost:
    def test_flash_lite_prices_for_a_known_call(self):
        # 1,000,000 in at $0.30 + 1,000,000 out at $2.50
        assert compute_cost_usd(1_000_000, 1_000_000, 0.30, 2.50) == Decimal("2.80")

    def test_input_and_output_are_priced_separately(self):
        assert compute_cost_usd(2_000_000, 0, 0.30, 2.50) == Decimal("0.60")
        assert compute_cost_usd(0, 2_000_000, 0.30, 2.50) == Decimal("5.00")

    def test_a_float_price_adds_no_float_noise(self):
        # 0.1 + 0.2 style error would show here if prices were multiplied as floats
        assert compute_cost_usd(1_000_000, 0, 0.1, 0.0) == Decimal("0.1")
        assert compute_cost_usd(3, 0, 0.3, 0.0) == Decimal("0.0000009")

    def test_zero_tokens_cost_nothing(self):
        assert compute_cost_usd(0, 0, 0.30, 2.50) == 0

    def test_a_zero_price_costs_nothing(self):
        assert compute_cost_usd(5_000, 5_000, 0.0, 0.0) == 0

    def test_cost_is_never_negative_and_never_falls_as_tokens_grow(self):
        rng = random.Random(28)  # seeded: a failure reproduces
        for _ in range(300):
            tokens_in, tokens_out = rng.randint(0, 10**9), rng.randint(0, 10**9)
            price_in, price_out = rng.randint(0, 10_000) / 100, rng.randint(0, 10_000) / 100
            cost = compute_cost_usd(tokens_in, tokens_out, price_in, price_out)
            assert cost >= 0
            assert compute_cost_usd(tokens_in + 1000, tokens_out, price_in, price_out) >= cost
            assert compute_cost_usd(tokens_in, tokens_out + 1000, price_in, price_out) >= cost


class TestEstimateTokens:
    @pytest.mark.parametrize(
        ("text", "tokens"),
        [("", 1), ("a", 1), ("abcd", 1), ("abcde", 2), ("x" * 40, 10), ("x" * 41, 11)],
    )
    def test_one_token_per_four_characters_rounded_up_never_below_one(self, text, tokens):
        assert estimate_tokens(text) == tokens

    def test_the_estimate_is_at_least_one_and_never_exceeds_the_character_count_plus_one(self):
        rng = random.Random(28)
        for _ in range(300):
            text = "x" * rng.randint(0, 2000)
            assert 1 <= estimate_tokens(text) <= len(text) + 1


class TestTokensFromGenaiUsage:
    def test_a_plain_answer(self):
        usage = SimpleNamespace(prompt_token_count=55, candidates_token_count=5, thoughts_token_count=None,
                                total_token_count=60)
        assert tokens_from_genai_usage(usage) == (55, 5)

    def test_thinking_tokens_count_as_output(self):
        usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=20, thoughts_token_count=300,
                                total_token_count=420)
        assert tokens_from_genai_usage(usage) == (100, 320)

    def test_thinking_tokens_count_as_output_even_when_no_total_is_reported(self):
        usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=20, thoughts_token_count=300,
                                total_token_count=None)
        assert tokens_from_genai_usage(usage) == (100, 320)

    def test_a_total_larger_than_the_parts_is_not_lost(self):
        usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=20, thoughts_token_count=None,
                                total_token_count=170)
        assert tokens_from_genai_usage(usage) == (100, 70)

    def test_missing_counts_are_zero_not_an_error(self):
        assert tokens_from_genai_usage(SimpleNamespace()) == (0, 0)
        assert tokens_from_genai_usage(SimpleNamespace(prompt_token_count=7)) == (7, 0)

    def test_no_usage_at_all_is_none(self):
        assert tokens_from_genai_usage(None) is None

    def test_junk_counts_are_ignored_not_trusted(self):
        usage = SimpleNamespace(prompt_token_count="9", candidates_token_count=True, thoughts_token_count=-4,
                                total_token_count=None)
        assert tokens_from_genai_usage(usage) == (0, 0)


class TestTokensFromOpenaiUsage:
    def test_a_plain_answer(self):
        usage = SimpleNamespace(prompt_tokens=55, completion_tokens=5, total_tokens=60)
        assert tokens_from_openai_usage(usage) == (55, 5)

    def test_reasoning_tokens_missing_from_completion_are_recovered_from_the_total(self):
        usage = SimpleNamespace(prompt_tokens=55, completion_tokens=5, total_tokens=360)
        assert tokens_from_openai_usage(usage) == (55, 305)

    def test_no_usage_at_all_is_none(self):
        assert tokens_from_openai_usage(None) is None

    def test_missing_counts_are_zero(self):
        assert tokens_from_openai_usage(SimpleNamespace(prompt_tokens=None, completion_tokens=None,
                                                         total_tokens=None)) == (0, 0)


@pytest.fixture
def factory(engine):
    """A session factory over real commits, so what the recorder commits is visible to a fresh session; the table is
    emptied around each test because these tests deliberately commit."""
    def make() -> Session:
        return Session(bind=engine)

    def clear() -> None:
        with Session(bind=engine) as cleanup:
            cleanup.query(ModelUsage).delete()
            cleanup.commit()

    clear()
    yield make
    clear()


def _all_rows(factory) -> list[ModelUsage]:
    with factory() as session:
        return list(session.scalars(select(ModelUsage).order_by(ModelUsage.occurred_at)))


class TestRecordModelUsage:
    def test_a_call_leaves_one_row_with_the_computed_cost(self, factory):
        record_model_usage(
            factory, purpose=PURPOSE_CATEGORIZATION, model="gemini-3.5-flash-lite",
            input_tokens=1000, output_tokens=200, input_price_per_million=0.30, output_price_per_million=2.50,
        )

        (row,) = _all_rows(factory)
        assert (row.purpose, row.provider, row.model) == ("categorization", "gemini", "gemini-3.5-flash-lite")
        assert (row.input_tokens, row.output_tokens, row.tokens_estimated) == (1000, 200, False)
        assert row.cost_usd == Decimal("0.00080000")  # 1000*0.30/1e6 + 200*2.50/1e6

    def test_estimated_tokens_are_flagged(self, factory):
        record_model_usage(
            factory, purpose=PURPOSE_EMBEDDING, model="gemini-embedding-2", input_tokens=20, output_tokens=0,
            input_price_per_million=0.20, output_price_per_million=0.0, tokens_estimated=True,
        )

        (row,) = _all_rows(factory)
        assert row.tokens_estimated is True
        assert row.cost_usd == Decimal("0.00000400")

    @pytest.mark.parametrize("purpose", PURPOSES)
    def test_every_known_purpose_is_recordable(self, factory, purpose):
        record_model_usage(
            factory, purpose=purpose, model="m", input_tokens=1, output_tokens=1,
            input_price_per_million=1.0, output_price_per_million=1.0,
        )

        assert [r.purpose for r in _all_rows(factory)] == [purpose]

    def test_the_four_purposes_are_exactly_the_ones_the_page_explains(self):
        assert set(PURPOSES) == {
            PURPOSE_STATEMENT_EXTRACTION, PURPOSE_CATEGORIZATION, PURPOSE_EMBEDDING, PURPOSE_ASK_AI,
        }

    def test_an_unknown_purpose_is_logged_and_swallowed_not_raised_and_not_stored(self, factory, caplog):
        record_model_usage(
            factory, purpose="mystery", model="m", input_tokens=1, output_tokens=1,
            input_price_per_million=1.0, output_price_per_million=1.0,
        )

        assert _all_rows(factory) == []
        assert "Could not record mystery model usage" in caplog.text

    def test_a_database_failure_never_reaches_the_caller(self, caplog):
        def broken() -> Session:
            raise RuntimeError("database is down")

        record_model_usage(  # must not raise
            broken, purpose=PURPOSE_ASK_AI, model="m", input_tokens=1, output_tokens=1,
            input_price_per_million=1.0, output_price_per_million=1.0,
        )

        assert "Could not record ask_ai model usage" in caplog.text

    def test_a_failing_commit_rolls_back_closes_the_session_and_does_not_raise(self, factory):
        closed: list[bool] = []

        class ExplodingSession(Session):
            def commit(self):
                raise RuntimeError("commit failed")

            def close(self):
                closed.append(True)
                super().close()

        record_model_usage(
            lambda: ExplodingSession(bind=factory().get_bind()), purpose=PURPOSE_ASK_AI, model="m",
            input_tokens=1, output_tokens=1, input_price_per_million=1.0, output_price_per_million=1.0,
        )

        assert closed == [True]
        assert _all_rows(factory) == []

    def test_the_row_survives_a_rollback_of_the_callers_own_transaction(self, factory, engine):
        """Money spent stays recorded even if the work that spent it is rolled back (MC-4)."""
        with Session(bind=engine) as callers_work:
            callers_work.execute(select(1))
            record_model_usage(
                factory, purpose=PURPOSE_STATEMENT_EXTRACTION, model="m", input_tokens=10, output_tokens=5,
                input_price_per_million=1.0, output_price_per_million=1.0,
            )
            callers_work.rollback()

        assert len(_all_rows(factory)) == 1

    def test_negative_token_counts_from_a_misbehaving_provider_are_clamped_to_zero(self, factory):
        record_model_usage(
            factory, purpose=PURPOSE_CATEGORIZATION, model="m", input_tokens=-5, output_tokens=-1,
            input_price_per_million=1.0, output_price_per_million=1.0,
        )

        (row,) = _all_rows(factory)
        assert (row.input_tokens, row.output_tokens, row.cost_usd) == (0, 0, 0)
