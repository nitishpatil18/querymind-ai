"""Conversation context: which earlier turns are relevant to the next question."""
from __future__ import annotations

import uuid

from app.config import Settings, get_settings
from app.llm.sql_generator import ContextTurn
from app.services.history_service import HistoryService


class ConversationService:
    def __init__(self, history: HistoryService, settings: Settings | None = None):
        self.history = history
        self.settings = settings or get_settings()

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def context(self, conversation_id: str, exclude_history_id: int | None = None) -> list[ContextTurn]:
        """Bounded window of earlier turns (default 4). Failed or superseded turns never enter the context."""
        turns = self.history.recent_turns(
            conversation_id, self.settings.conversation_context_turns, exclude_id=exclude_history_id
        )
        out: list[ContextTurn] = []
        for t in turns:
            if t.status == "ok":
                out.append(ContextTurn(question=t.standalone_question or t.question, sql=t.sql))
            else:  # clarification_needed: keep what the assistant asked so the user's answer can be resolved
                out.append(ContextTurn(question=t.question, sql=None, note=t.clarification_question))
        return out
