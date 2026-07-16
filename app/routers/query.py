from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import QueryLog
from app.schemas import QueryRequest, QueryResponse, FeedbackRequest
from app.rag import retrieve, generate_answer

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
def query(payload: QueryRequest, db: Session = Depends(get_db)):
    """카카오 스킬서버가 호출하는 핵심 RAG 엔드포인트."""
    retrieved = retrieve(db, payload.tenant_id, payload.question)
    result = generate_answer(payload.question, retrieved)

    log = QueryLog(
        tenant_id=payload.tenant_id,
        kakao_user_key=payload.user_key,
        question=payload.question,
        answer=result["answer"],
        matched_chunk_ids=[r["chunk_id"] for r in retrieved],
        confidence=retrieved[0]["similarity"] if retrieved else 0.0,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return QueryResponse(answer=result["answer"], sources=result["sources"], query_log_id=log.id)


@router.post("/{log_id}/feedback")
def submit_feedback(log_id: str, payload: FeedbackRequest, db: Session = Depends(get_db)):
    """사용자가 카카오톡에서 👍/👎 버튼을 눌렀을 때 호출 - 품질 모니터링용."""
    log = db.query(QueryLog).filter(QueryLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="log not found")
    log.feedback = payload.feedback
    db.commit()
    return {"ok": True}
