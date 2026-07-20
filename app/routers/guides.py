from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db
from app.models import CompanyGuide
from app.rag import answer_guide_question

router = APIRouter(prefix="/guides", tags=["guides"])


class GuideCreate(BaseModel):
    tenant_id: str
    title: str
    content: str  # 가이드/사규 전문 텍스트


class GuideAsk(BaseModel):
    question: str


@router.post("")
def create_guide(payload: GuideCreate, db: Session = Depends(get_db)):
    """현장 공통 가이드/사규 문서 등록. 개별 노하우와 달리 청킹·임베딩 없이 원문 그대로 저장."""
    guide = CompanyGuide(**payload.model_dump())
    db.add(guide)
    db.commit()
    db.refresh(guide)
    return {"id": guide.id, "title": guide.title}


@router.get("")
def list_guides(tenant_id: str, db: Session = Depends(get_db)):
    guides = db.query(CompanyGuide).filter(CompanyGuide.tenant_id == tenant_id).all()
    return [{"id": g.id, "title": g.title, "updated_at": g.updated_at} for g in guides]


@router.post("/{guide_id}/ask")
def ask_guide(guide_id: str, payload: GuideAsk, db: Session = Depends(get_db)):
    """가이드 문서 기반 질의응답. 같은 문서로 반복 질문 시 Claude 프롬프트 캐싱으로
    두 번째 호출부터 문서 부분의 입력 토큰 비용이 크게 절감된다 (응답의 usage에서 확인 가능)."""
    guide = db.query(CompanyGuide).filter(CompanyGuide.id == guide_id).first()
    if not guide:
        raise HTTPException(status_code=404, detail="guide not found")

    result = answer_guide_question(guide.content, payload.question)
    return {"answer": result["answer"], "usage": result["usage"]}
