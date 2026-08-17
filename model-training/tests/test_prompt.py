"""MTR-5: prompt-template rendering, including the cross-check that this unit's
independent copy of the template stays byte-identical to ingestion-worker's real
one (WR-34) -- the whole point of Requirements' Resolved Decision 5/6."""

from decimal import Decimal
from pathlib import Path
from typing import ClassVar

from model_training.prompt import format_amount_sgd, render_classification_prompt


class TestFormatAmountSgd:
    def test_decimal_renders_with_sgd_suffix(self):
        assert format_amount_sgd(Decimal("45.20")) == "45.20 SGD"

    def test_none_renders_as_unknown(self):
        assert format_amount_sgd(None) == "unknown"


class TestRenderClassificationPrompt:
    def test_includes_description_amount_and_categories(self):
        prompt = render_classification_prompt("NTUC FAIRPRICE", Decimal("45.20"), ["Groceries", "Dining"])

        assert "NTUC FAIRPRICE" in prompt
        assert "45.20 SGD" in prompt
        assert "Groceries" in prompt
        assert "Dining" in prompt
        assert "UNSURE" in prompt

    def test_none_amount_renders_as_unknown(self):
        prompt = render_classification_prompt("NTUC FAIRPRICE", None, ["Groceries"])

        assert "unknown" in prompt


class TestMatchesLiveIngestionWorkerTemplate:
    """Not a unit test of this module alone -- a cross-repo consistency check.
    Asserts every literal text fragment this unit's template is built from also
    appears verbatim in ingestion_worker/clients/openrouter_client.py's real
    source (read as text -- this unit deliberately never imports
    ingestion_worker's package, per Application Design). If this test ever fails,
    it means WR-34's live prompt changed without this unit's copy being updated
    to match -- exactly the drift Requirements' Resolved Decision 5/6 exists to
    prevent. Fragment-level rather than a single-regex full-string match, so it
    survives incidental reformatting of the source (e.g. line-wrapping) without
    losing its ability to catch an actual wording change."""

    _EXPECTED_FRAGMENTS: ClassVar[list[str]] = [
        "Classify this bank transaction description into exactly one of the following ",
        "categories, responding with ONLY the category name and nothing else:",
        "Categories: {",
        "Transaction description: {description}",
        "Transaction amount: {",
        "If none of the categories clearly fit, respond with exactly: UNSURE",
    ]

    def test_every_template_fragment_appears_in_the_real_source(self):
        ingestion_worker_client = (
            Path(__file__).resolve().parents[2]
            / "ingestion-worker"
            / "src"
            / "ingestion_worker"
            / "clients"
            / "openrouter_client.py"
        )
        source = ingestion_worker_client.read_text()

        for fragment in self._EXPECTED_FRAGMENTS:
            assert fragment in source, f"template fragment not found in ingestion-worker's real source: {fragment!r}"

    def test_render_classification_prompt_itself_contains_the_same_fragments(self):
        """Confirms this unit's own function actually produces those fragments too
        -- the two tests together prove both sides agree, not just that the
        fragment list looks plausible."""
        prompt = render_classification_prompt("NTUC FAIRPRICE", Decimal("45.20"), ["Groceries"])
        for fragment in self._EXPECTED_FRAGMENTS:
            static_part = fragment.split("{")[0]
            assert static_part in prompt, f"expected fragment not found in rendered prompt: {static_part!r}"
