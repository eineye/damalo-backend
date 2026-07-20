"""
Dify(chat-messages API) 호출 클라이언트.
Dify 앱 화면 > 왼쪽 메뉴 'API 접근(API Access)'에서 발급받은 키를 DIFY_API_KEY로 설정하세요.
셀프호스팅 Dify라면 DIFY_API_BASE를 그 서버 주소(예: http://your-server/v1)로 바꾸세요.
"""
import httpx

from app.config import settings


def ask_dify(question: str, user_key: str, conversation_id: str | None = None) -> dict:
    """Dify 챗봇에 질문하고 답변 + 다음 턴에 이어 쓸 conversation_id를 반환."""
    if not settings.dify_api_key:
        return {"answer": "[Dify 미설정] DIFY_API_KEY 환경변수를 설정해주세요.", "conversation_id": conversation_id}

    try:
        resp = httpx.post(
            f"{settings.dify_api_base}/chat-messages",
            headers={
                "Authorization": f"Bearer {settings.dify_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "inputs": {},
                "query": question,
                "response_mode": "blocking",  # 카카오는 동기 응답이 필요하므로 streaming 대신 blocking 사용
                "conversation_id": conversation_id or "",
                "user": user_key or "kakao-anonymous",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "answer": data.get("answer", "답변을 받지 못했어요."),
            "conversation_id": data.get("conversation_id") or conversation_id,
        }
    except Exception as e:
        return {
            "answer": "죄송해요, 지금 답변을 가져오지 못했어요. 잠시 후 다시 시도해주세요.",
            "conversation_id": conversation_id,
        }
