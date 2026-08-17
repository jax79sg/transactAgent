"""MTR-8: accuracy/confusion-matrix scoring, given already-known predictions --
pure function, no real model or HTTP call involved (NFR Requirements'
"Two-Speed Testability")."""

import pytest

from model_training.evaluate import score_predictions


class TestScorePredictions:
    def test_all_correct_and_all_agree(self):
        result = score_predictions(
            ground_truth=["Groceries", "Dining"],
            fine_tuned_predictions=["Groceries", "Dining"],
            live_predictions=["Groceries", "Dining"],
        )

        assert result.accuracy == 1.0
        assert result.agreement_with_live_model == 1.0

    def test_partial_accuracy(self):
        result = score_predictions(
            ground_truth=["Groceries", "Dining", "Petrol"],
            fine_tuned_predictions=["Groceries", "Transport", "Petrol"],
            live_predictions=["Groceries", "Dining", "Petrol"],
        )

        assert result.accuracy == pytest.approx(2 / 3)

    def test_agreement_is_independent_of_accuracy(self):
        """A fine-tuned prediction can agree with the live model while both are
        wrong -- agreement measures fine-tuned-vs-live, not fine-tuned-vs-truth."""
        result = score_predictions(
            ground_truth=["Groceries"],
            fine_tuned_predictions=["Dining"],
            live_predictions=["Dining"],
        )

        assert result.accuracy == 0.0
        assert result.agreement_with_live_model == 1.0

    def test_confusion_matrix_shape(self):
        result = score_predictions(
            ground_truth=["Groceries", "Groceries", "Dining"],
            fine_tuned_predictions=["Groceries", "Dining", "Dining"],
            live_predictions=["Groceries", "Groceries", "Dining"],
        )

        assert result.confusion_matrix["Groceries"] == {"Groceries": 1, "Dining": 1}
        assert result.confusion_matrix["Dining"] == {"Dining": 1}

    def test_off_whitelist_prediction_counts_as_incorrect_not_a_crash(self):
        """MTR-8: an invalid/UNSURE prediction never matches a real category label
        -- it's simply wrong, not a special case requiring different handling."""
        result = score_predictions(
            ground_truth=["Groceries"],
            fine_tuned_predictions=["UNSURE"],
            live_predictions=["Groceries"],
        )

        assert result.accuracy == 0.0
        assert result.confusion_matrix["Groceries"] == {"UNSURE": 1}

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            score_predictions(ground_truth=["Groceries"], fine_tuned_predictions=[], live_predictions=["Groceries"])

    def test_empty_validation_set_raises(self):
        with pytest.raises(ValueError):
            score_predictions(ground_truth=[], fine_tuned_predictions=[], live_predictions=[])
