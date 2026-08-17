"""Tests for llm_classifier.py's classify_batch_prompt (WR-27, Matching Precision
Refinement, revised 2026-08-16 during Build and Test). classify() itself is
exercised indirectly through test_categorization_service.py/test_orchestrator_pipeline.py
-- this file focuses on the new batch-prompt JSON-parsing logic, which is genuinely
new parsing behavior worth its own direct coverage.
"""

from decimal import Decimal
from unittest.mock import patch

from ingestion_worker.categorization.llm_classifier import UNSURE, classify_batch_prompt
from ingestion_worker.clients.retry import TransientError


class TestClassifyBatchPrompt:
    def _descriptions(self):
        """WR-34: classify_batch_prompt now takes (description, amountSgd) pairs --
        the amount values here are arbitrary, since every assertion in this file is
        about description-keyed parsing behavior, not amount handling."""
        return [
            ("NTUC FAIRPRICE", Decimal("45.20")),
            ("STARBUCKS COFFEE", Decimal("6.50")),
            ("SHELL PETROL", Decimal("80.00")),
        ]

    def _whitelist(self):
        return ["Groceries", "Dining", "Petrol"]

    def test_valid_json_array_all_entries_returned(self):
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value='["Groceries", "Dining", "Petrol"]',
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {"NTUC FAIRPRICE": "Groceries", "STARBUCKS COFFEE": "Dining", "SHELL PETROL": "Petrol"}

    def test_unsure_entry_is_a_valid_answer(self):
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value='["Groceries", "UNSURE", "Petrol"]',
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result["STARBUCKS COFFEE"] == UNSURE

    def test_extra_surrounding_text_or_markdown_fences_still_parses(self):
        """Models sometimes wrap the array in prose or a code fence despite being
        asked for ONLY the JSON -- the array itself is still extracted."""
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value='Here you go:\n```json\n["Groceries", "Dining", "Petrol"]\n```',
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {"NTUC FAIRPRICE": "Groceries", "STARBUCKS COFFEE": "Dining", "SHELL PETROL": "Petrol"}

    def test_shorter_array_than_requested_leaves_trailing_descriptions_absent(self):
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value='["Groceries", "Dining"]',
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {"NTUC FAIRPRICE": "Groceries", "STARBUCKS COFFEE": "Dining"}
        assert "SHELL PETROL" not in result

    def test_invalid_entry_is_absent_but_siblings_are_kept(self):
        """A single entry that isn't a whitelist name or UNSURE is dropped -- it
        does not invalidate the whole batch (categorization/service.py's
        classify_batch is what falls it back to an individual call)."""
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value='["Groceries", "Some Made Up Category", "Petrol"]',
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {"NTUC FAIRPRICE": "Groceries", "SHELL PETROL": "Petrol"}
        assert "STARBUCKS COFFEE" not in result

    def test_non_string_entry_is_absent(self):
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value='["Groceries", null, "Petrol"]',
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert "STARBUCKS COFFEE" not in result

    def test_unparseable_json_returns_empty_dict(self):
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value="I cannot help with that.",
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {}

    def test_malformed_json_inside_brackets_returns_empty_dict(self):
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value='["Groceries", "Dining",]',  # trailing comma -- invalid JSON
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {}

    def test_response_not_a_json_array_returns_empty_dict(self):
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            return_value='{"NTUC FAIRPRICE": "Groceries"}',
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {}

    def test_transient_error_returns_empty_dict_never_raises(self):
        """WR-4/WR-7-style contract: exhausted retries are terminal for this batch,
        not propagated -- the caller falls every description back individually."""
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            side_effect=TransientError("network error"),
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {}

    def test_any_other_exception_returns_empty_dict_never_raises(self):
        with patch(
            "ingestion_worker.categorization.llm_classifier.classify_descriptions_batch",
            side_effect=RuntimeError("unexpected"),
        ):
            result = classify_batch_prompt(self._descriptions(), self._whitelist())

        assert result == {}
