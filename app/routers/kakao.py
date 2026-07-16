"""
카카오 i 오픈빌더 스킬서버.
오픈빌더 콘솔 > 스킬 > URL 등록 시 아래 엔드포인트를 등록합니다:
  https://<도메인>/kakao/webhook/{tenant_id}
공장(테넌트)마다 별도의 스킬 URL(=별도 tenant_id)을 등록해 지식베이스를 격리합니다.

카카오 요청/응답 포맷 문서: https://i.kakao.com/docs/skill-response-format
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import QueryLog
from app.rag import retrieve, generate_answer

router = APIRouter(prefix="/kakao", tags=["kakao"])


def _kakao_text_response(text: str, query_log_id: str) -> dict:
    """단순 텍스트 + 피드백 버튼(퀵리플라이) 형태의 카카오 응답 포맷."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": [
                {"label": "👍 도움됐어요", "action": "block",
                 "messageText": f"__feedback_up__{query_log_id}"},
                {"label": "👎 도움 안됐어요", "action": "block",
                 "messageText": f"__feedback_down__{query_log_id}"},
            ],
        },
    }


@router.post("/webhook/{tenant_id}")
async def kakao_webhook(tenant_id: str, payload: dict, db: Session = Depends(get_db)):
    utterance = payload.get("userRequest", {}).get("utterance", "").strip()
    user_key = payload.get("userRequest", {}).get("user", {}).get("id")

    # 퀵리플라이로 들어온 피드백 처리
    if utterance.startswith("__feedback_up__") or utterance.startswith("__feedback_down__"):
        is_up = utterance.startswith("__feedback_up__")
        log_id = utterance.split("__")[-1]
        log = db.query(QueryLog).filter(QueryLog.id == log_id).first()
        if log:
            log.feedback = "up" if is_up else "down"
            db.commit()
        return {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": "피드백 감사합니다! 🙌"}}]},
        }

    retrieved = retrieve(db, tenant_id, utterance)
    result = generate_answer(utterance, retrieved)

    log = QueryLog(
        tenant_id=tenant_id,
        kakao_user_key=user_key,
        question=utterance,
        answer=result["answer"],
        matched_chunk_ids=[r["chunk_id"] for r in retrieved],
        confidence=retrieved[0]["similarity"] if retrieved else 0.0,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return _kakao_text_response(result["answer"], log.id)
