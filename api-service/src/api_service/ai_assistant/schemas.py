from datetime import date

from pydantic import Field

from api_service.schemas import CamelModel


class AskAiRequest(CamelModel):
    # JSON request bodies are camelCase throughout this app (unlike query params,
    # which are snake_case -- see api_service/schemas.py's CamelModel docstring and
    # frontend/src/api/client.ts's toSnakeCase, which only applies to query strings).
    question: str = Field(min_length=1, max_length=2000)
    date_from: date | None = None
    date_to: date | None = None
    use_all_transactions: bool = False


class AskAiResponse(CamelModel):
    answer: str
    transactions_considered: int
    truncated: bool
