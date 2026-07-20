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


@app.get("/health")
def health():
    return {"status": "ok"}
