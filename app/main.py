from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.routers import content, query, kakao, admin, stt, guides, kakao_dify

app = FastAPI(
    title="제조 노하우 RAG 챗봇 API",
    description="전문가 노하우 입수 → RAG 검색 → 카카오톡/관리자 웹 서비스",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 운영 환경에서는 관리자 웹 도메인으로 제한
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(content.router)
app.include_router(query.router)
app.include_router(kakao.router)
app.include_router(admin.router)
app.include_router(stt.router)
app.include_router(guides.router)
app.include_router(kakao_dify.router)


@app.on_event("startup")
def on_startup():
    # 최초 실행 시 테이블 생성 (운영에서는 Alembic 마이그레이션 권장)
    Base.metadata.create_all(bind=engine)
    # 참고: 임베딩 모델을 여기서 미리 로딩(warm-up)하면 첫 요청 지연은 줄어들지만,
    # Render 무료 요금제(512MB)에서는 그 자체로 메모리 초과(OOM)를 일으켜 서버가
    # 아예 못 뜰 수 있다 (실제로 겪은 문제). 그래서 지연 로딩(첫 실제 사용 시점) 방식을
    # 유지한다. 더 큰 메모리의 유료 플랜으로 옮기면 그때 다시 warm-up을 켜는 걸 권장.


@app.get("/health")
def health():
    return {"status": "ok"}
