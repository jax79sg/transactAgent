from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_service.ai_assistant import service
from api_service.ai_assistant.schemas import AskAiRequest, AskAiResponse
from api_service.auth.dependencies import get_current_user_id
from api_service.db import get_db

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(get_current_user_id)])


@router.post("/ask", response_model=AskAiResponse)
def ask(payload: AskAiRequest, db: Session = Depends(get_db)) -> AskAiResponse:
    answer, transactions_considered, truncated = service.ask_question(
        db,
        question=payload.question,
        date_from=payload.date_from,
        date_to=payload.date_to,
        use_all_transactions=payload.use_all_transactions,
    )
    return AskAiResponse(answer=answer, transactions_considered=transactions_considered, truncated=truncated)
