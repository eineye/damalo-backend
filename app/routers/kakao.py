"""
카카오 i 오픈빌더 스킬서버.
오픈빌더 콘솔 > 스킬 > URL 등록 시 아래 엔드포인트를 등록합니다:
  https://<도메인>/kakao/webhook/{tenant_id}
공장(테넌트)마다 별도의 스킬 URL(=별도 tenant_id)을 등록해 지식베이스를 격리합니다.

카카오 요청/응답 포맷 문서: https://i.kakao.com/docs/skill-response-format

중요: 카카오 스킬의 응답 제한시간은 5초로 고정되어 있다(조정 불가). RAG 검색+LLM 호출은
보통 5초를 넘기기 때문에, 봇을 "AI 챗봇"으로 전환 신청(챗봇 관리자센터 > 설정 > AI 챗봇 관리)해서
콜백(callback) 기능을 켜야 한다. 전환/승인이 끝나면 요청에 callbackUrl이 함께 들어오는데,
이 경우 즉시 useCallback 응답을 보내고, 실제 처리는 백그라운드에서 진행한 뒤
callbackUrl로 결과를 다시 POST한다 (콜백 URL 유효시간 1분).
전환 전(테스트 단계)에는 callbackUrl이 없으므로 기존처럼 동기 방식으로 응답한다.
"""
import httpx
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.db import get_db, SessionLocal
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


def _process_and_callback(tenant_id: str, utterance: str, user_key: str, callback_url: str):
    """백그라운드에서 RAG 처리 후 콜백 URL로 결과 전송.
    요청-응답 사이클이 끝난 뒤 실행되므로, 요청에 딸려온 DB 세션을 재사용하지 않고
    새 세션을 직접 연다 (FastAPI 백그라운드 태스크의 표준 패턴)."""
    db = SessionLocal()
    try:
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

        payload = _kakao_text_response(result["answer"], log.id)
        try:
            httpx.post(callback_url, json=payload, timeout=30.0)
        except Exception:
            pass  # 콜백 URL 유효시간(1분)이 지났거나 네트워크 오류 - 재시도 불가, 로그만 남기고 무시
    finally:
        db.close()


@router.post("/webhook/{tenant_id}")
async def kakao_webhook(
    tenant_id: str,
    payload: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    utterance = payload.get("userRequest", {}).get("utterance", "").strip()
    user_key = payload.get("userRequest", {}).get("user", {}).get("id")
    callback_url = payload.get("userRequest", {}).get("callbackUrl")

    # 퀵리플라이로 들어온 피드백 처리 (빠른 작업이라 콜백 없이 동기 처리)
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

    if callback_url:
        # AI 챗봇 전환 완료 - 콜백 방식 (5초 제한 없음)
        background_tasks.add_task(_process_and_callback, tenant_id, utterance, user_key, callback_url)
        return {"version": "2.0", "useCallback": True}

    # 콜백 미승인 상태 - 기존 동기 방식 (5초 안에 못 끝내면 타임아웃 날 수 있음)
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
