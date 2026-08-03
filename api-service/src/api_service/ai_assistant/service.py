"""Ask AI business logic (US-6.1): ground a free-text question in the user's own
transaction history, scoped by date range or explicitly "all transactions".
"""

from datetime import date

from sqlalchemy.orm import Session

from api_service.ai_assistant import gemini_client
from api_service.ai_assistant.prompts import build_prompt
from api_service.config import settings
from api_service.errors import InvalidDateRangeError, NoTransactionsInScopeError
from api_service.transactions import repository as transactions_repository


def ask_question(
    db: Session,
    *,
    question: str,
    date_from: date | None,
    date_to: date | None,
    use_all_transactions: bool,
) -> tuple[str, int, bool]:
    if not use_all_transactions:
        if date_from is None or date_to is None:
            raise InvalidDateRangeError("A date range is required unless using all transactions")
        if date_from > date_to:
            raise InvalidDateRangeError("date_from must not be after date_to")

    effective_from = None if use_all_transactions else date_from
    effective_to = None if use_all_transactions else date_to

    transactions, truncated = transactions_repository.query_for_ai_context(
        db, effective_from, effective_to, settings.ai_assistant_max_transactions
    )
    if not transactions:
        raise NoTransactionsInScopeError("No transactions found in the selected scope")

    scope_description = (
        "all transactions"
        if use_all_transactions
        else f"{date_from.isoformat()} to {date_to.isoformat()}"
    )
    prompt = build_prompt(question, transactions, truncated, scope_description)
    answer = gemini_client.ask_gemini(prompt)

    return answer, len(transactions), truncated
