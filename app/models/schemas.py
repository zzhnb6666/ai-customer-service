from pydantic import BaseModel
from datetime import datetime


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    user_id: str
    message: str
    channel: str = "api"  # "telegram" | "whatsapp" | "api"


class ChatResponse(BaseModel):
    reply: str
    intent: str | None = None
    handoff: bool = False


class ConversationRecord(BaseModel):
    id: str
    user_id: str
    channel: str
    messages: list[ChatMessage]
    created_at: datetime
    updated_at: datetime
    handoff: bool = False
