import re
from anthropic import Anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.embeddings import embed_text, embed_batch
from app.models import ContentChunk, ExpertContent

_client = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

SYSTEM_PROMPT = """당신은 제조 현장의 숙련 기술자 노하우를 초보자에게 안내하는 도우미입니다.
반드시 아래 [참고 자료]에 있는 내용만 근거로 답변하세요.
- [참고 자료]에 없는 내용은 추측하지 말고 "관련 정보가 없습니다. 담당 관리자에게 문의하세요"라고 답하세요.
- 고전압, 화학물질, 추락 위험 등 안전과 관련된 질문에는 반드시 "정식 안전교육 자료와 담당자 확인을 우선하세요"라는 안내를 함께 포함하세요.
- 답변은 현장에서 바로 쓸 수 있도록 간결하고 단계적으로 작성하세요.
- 답변 끝에 어떤 자료(작성자/공정명)를 참고했는지 간단히 밝히세요.
"""


def chunk_text(text: str, max_chars: int = 400, overlap: int = 50) -> list[str]:
    """문장 단위로 나눈 뒤 max_chars 기준으로 묶는 단순 청킹.
    실제 운영에서는 공정 단계/Q&A 단위 등 의미 단위 청킹을 권장합니다."""
    sentences = re.split(r"(?<=[.!?다요])\s+", text.strip())
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_chars and current:
            chunks.append(current.strip())
            current = current[-overlap:] + s
        else:
            current += (" " if current else "") + s
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]


def ingest_content(db: Session, content: ExpertContent) -> int:
    """승인된(또는 신규) 콘텐츠를 청크로 쪼개고 임베딩하여 저장. 저장된 청크 수 반환."""
    pieces = chunk_text(content.raw_text)
    vectors = embed_batch(pieces)

    for text, vector in zip(pieces, vectors):
        db.add(ContentChunk(
            content_id=content.id,
            tenant_id=content.tenant_id,
            chunk_text=text,
            embedding=vector,
        ))
    db.commit()
    return len(pieces)


def retrieve(db: Session, tenant_id: str, question: str, top_k: int | None = None):
    """질문 임베딩 -> pgvector 코사인 유사도 검색.
    승인된(status=approved) 콘텐츠의 청크만 검색 대상으로 조인."""
    top_k = top_k or settings.top_k
    q_vector = embed_text(question)

    stmt = (
        select(
            ContentChunk,
            ExpertContent,
            ContentChunk.embedding.cosine_distance(q_vector).label("distance"),
        )
        .join(ExpertContent, ContentChunk.content_id == ExpertContent.id)
        .where(ExpertContent.tenant_id == tenant_id)
        .where(ExpertContent.status == "approved")
        .order_by("distance")
        .limit(top_k)
    )
    rows = db.execute(stmt).all()

    results = []
    for chunk, content, distance in rows:
        similarity = 1 - distance
        if similarity < settings.similarity_threshold:
            continue
        results.append({
            "chunk_id": chunk.id,
            "text": chunk.chunk_text,
            "similarity": round(float(similarity), 3),
            "author": content.author_name,
            "process_tag": content.process_tag,
            "risk_level": content.risk_level,
        })
    return results


def generate_answer(question: str, retrieved: list[dict]) -> dict:
    """검색된 컨텍스트를 근거로 LLM 답변 생성."""
    if not retrieved:
        return {
            "answer": "관련 정보가 아직 등록되어 있지 않습니다. 담당 관리자에게 문의해 주세요.",
            "sources": [],
        }

    context_block = "\n\n".join(
        f"[자료 {i+1}] (작성자: {r['author']}, 공정: {r.get('process_tag') or '미분류'})\n{r['text']}"
        for i, r in enumerate(retrieved)
    )

    if _client is None:
        # ANTHROPIC_API_KEY 미설정 시 검색 결과만이라도 반환 (개발용 폴백)
        return {
            "answer": "[LLM 미연결 - 개발 모드] 관련 자료:\n" + context_block,
            "sources": retrieved,
        }

    message = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"[참고 자료]\n{context_block}\n\n[질문]\n{question}",
        }],
    )
    answer_text = "".join(
        block.text for block in message.content if block.type == "text"
    )
    return {"answer": answer_text, "sources": retrieved}
GUIDE_SYSTEM_PROMPT = """당신은 사내 공통 가이드/사규 문서를 안내하는 도우미입니다.
아래 [문서]에 있는 내용만 근거로 답변하세요. 문서에 없는 내용은 "문서에서 찾을 수 없습니다"라고 답하세요.
답변은 간결하게, 관련 조항이나 절차명을 함께 언급하세요.
"""


def answer_guide_question(guide_content: str, question: str) -> dict:
    """현장 공통 가이드/사규 문서 질의응답 - Claude 프롬프트 캐싱 적용.

    같은 tenant의 같은 문서(guide_content)로 반복 질문이 들어오면,
    두 번째 호출부터는 문서 부분이 캐시에서 읽혀 입력 토큰 비용이 약 90% 절감된다.
    (문서가 1개 모델의 최소 캐시 토큰 기준(보통 1024~4096 토큰) 이상일 때만 실제로 캐싱됨 -
     그보다 짧은 문서는 cache_control을 붙여도 정상 응답은 되지만 캐시 효과는 없다.)
    """
    if _client is None:
        return {
            "answer": "[LLM 미연결 - 개발 모드] ANTHROPIC_API_KEY를 설정해주세요.",
            "usage": None,
        }

    # SDK 버전에 따라 1h TTL이 베타 헤더를 요구할 수 있어 안전하게 항상 포함시킴
    # (5m 기본 TTL만 쓸 경우엔 무시되어도 무해함)
    extra_headers = {"anthropic-beta": "extended-cache-ttl-2025-04-11"} if settings.guide_cache_ttl == "1h" else {}

    message = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=800,
        extra_headers=extra_headers,
        system=[
            {"type": "text", "text": GUIDE_SYSTEM_PROMPT},
            {
                "type": "text",
                "text": f"[문서]\n{guide_content}",
                "cache_control": {"type": "ephemeral", "ttl": settings.guide_cache_ttl},
            },
        ],
        messages=[{"role": "user", "content": question}],
    )
    answer_text = "".join(block.text for block in message.content if block.type == "text")

    usage = message.usage
    return {
        "answer": answer_text,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            # 캐시에서 읽은 토큰 (거의 무료, 정가의 0.1배) - 클수록 절감 효과가 큰 것
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            # 이번 요청에서 새로 캐시에 쓴 토큰 (정가의 1.25~2배, 최초 1회만 발생)
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        },
    }
