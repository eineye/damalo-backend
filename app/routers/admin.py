from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Tenant, ExpertContent, QueryLog

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/tenants")
def create_tenant(name: str, kakao_channel_id: str | None = None, db: Session = Depends(get_db)):
    tenant = Tenant(name=name, kakao_channel_id=kakao_channel_id)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return {"id": tenant.id, "name": tenant.name}


@router.get("/tenants/{tenant_id}/stats")
def tenant_stats(tenant_id: str, days: int = 7, db: Session = Depends(get_db)):
    """관리자 대시보드 통계: 콘텐츠 현황, 최근 질문량, 미해결(저신뢰) 질문 수."""
    since = datetime.utcnow() - timedelta(days=days)

    content_counts = dict(
        db.query(ExpertContent.status, func.count(ExpertContent.id))
        .filter(ExpertContent.tenant_id == tenant_id)
        .group_by(ExpertContent.status).all()
    )

    total_queries = (
        db.query(func.count(QueryLog.id))
        .filter(QueryLog.tenant_id == tenant_id, QueryLog.created_at >= since)
        .scalar()
    )

    low_confidence = (
        db.query(func.count(QueryLog.id))
        .filter(QueryLog.tenant_id == tenant_id, QueryLog.created_at >= since,
                QueryLog.confidence < 0.3)
        .scalar()
    )

    negative_feedback = (
        db.query(func.count(QueryLog.id))
        .filter(QueryLog.tenant_id == tenant_id, QueryLog.created_at >= since,
                QueryLog.feedback == "down")
        .scalar()
    )

    return {
        "content_counts": {
            "pending": content_counts.get("pending", 0),
            "approved": content_counts.get("approved", 0),
            "rejected": content_counts.get("rejected", 0),
        },
        "queries_last_n_days": total_queries,
        "low_confidence_answers": low_confidence,
        "negative_feedback": negative_feedback,
    }


@router.get("/tenants/{tenant_id}/unresolved-queries")
def unresolved_queries(tenant_id: str, db: Session = Depends(get_db)):
    """근거 자료가 부족했거나(낮은 신뢰도) 부정 피드백을 받은 질문들 -> 전문가에게 재입력 요청할 목록."""
    logs = (
        db.query(QueryLog)
        .filter(QueryLog.tenant_id == tenant_id)
        .filter((QueryLog.confidence < 0.3) | (QueryLog.feedback == "down"))
        .order_by(QueryLog.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {"id": l.id, "question": l.question, "answer": l.answer,
         "confidence": l.confidence, "feedback": l.feedback, "created_at": l.created_at}
        for l in logs
    ]
