from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.schemas.request import ChatRequest
from app.schemas.response import GenerateResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=GenerateResponse, summary="Conversational question; follow-ups use earlier turns")
def chat(body: ChatRequest, c: Container = Depends(get_container)) -> GenerateResponse:
    return c.query_service.generate(
        body.question,
        conversation_id=body.conversation_id,
        use_context=True,
        top_k=body.top_k,
        regenerate_of=body.regenerate_of,
    )
