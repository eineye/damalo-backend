"""
카카오 i 오픈빌더 ↔ Dify 챗봇 중계.
자체 RAG 챗봇(app/routers/kakao.py, /kakao/webhook/{tenant_id})과는 완전히 별개 경로입니다.

오픈빌더 콘솔 > 스킬 > URL 등록 시:
  https://<도메인>/kakao-dify/webhook/{tenant_id}
공장(테넌트)마다 다른 Dify 앱을 쓰고 싶다면, tenant_id별로 다른 DIFY_API_KEY를 매핑하도록
확장하면 됩니다 (지금은 서버 전체에 하나의 DIFY_API_KEY만 사용).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DifySession
from app.dify_client import ask_dify

router = APIRouter(prefix="/kakao-dify", tags=["kakao-dify"])


def _kakao_text_response(text: str) -> dict:
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


@router.post("/webhook/{tenant_id}")
async def kakao_dify_webhook(tenant_id: str, payload: dict, db: Session = Depends(get_db)):
    utterance = payload.get("userRequest", {}).get("utterance", "").strip()
    user_key = payload.get("userRequest", {}).get("user", {}).get("id", "kakao-anonymous")

    session = (
        db.query(DifySession)
        .filter(DifySession.tenant_id == tenant_id, DifySession.kakao_user_key == user_key)
        .first()
    )

    result = ask_dify(utterance, user_key, session.dify_conversation_id if session else None)

    if session:
        session.dify_conversation_id = result["conversation_id"]
    else:
        session = DifySession(
            tenant_id=tenant_id,
            kakao_user_key=user_key,
            dify_conversation_id=result["conversation_id"],
        )
        db.add(session)
    db.commit()

    return _kakao_text_response(result["answer"])
