from typing import Optional, Literal
from pydantic import BaseModel


class ContentCreate(BaseModel):
    tenant_id: str
    author_name: str
    content_type: Literal["voice", "text", "video"]
    raw_text: str                      # 텍스트 직접 입력 또는 STT 결과
    media_url: Optional[str] = None
    process_tag: Optional[str] = None
    equipment_tag: Optional[str] = None
    risk_level: Literal["low", "medium", "high"] = "low"


class ContentReview(BaseModel):
    status: Literal["approved", "rejected"]
    reviewed_by: str


class QueryRequest(BaseModel):
    tenant_id: str
    question: str
    user_key: Optional[str] = None     # 카카오 사용자 식별자 등


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    query_log_id: str


class FeedbackRequest(BaseModel):
    feedback: Literal["up", "down"]
