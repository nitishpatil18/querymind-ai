from fastapi import APIRouter, Depends, Query

from app.api.deps import Container, get_container
from app.services.history_service import HistoryItem, HistoryPage

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryPage, summary="Query history (newest first)")
def list_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conversation_id: str | None = Query(None, max_length=64),
    c: Container = Depends(get_container),
) -> HistoryPage:
    return c.history.list(limit=limit, offset=offset, conversation_id=conversation_id)


@router.get("/{history_id}", response_model=HistoryItem, summary="One history entry")
def get_history(history_id: int, c: Container = Depends(get_container)) -> HistoryItem:
    return c.history.get(history_id)
