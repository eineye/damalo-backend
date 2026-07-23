import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, JSON, Enum, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.config import settings
from app.db import Base


def gen_uuid():
    return str(uuid.uuid4())


class Tenant(Base):
    """공장(고객사) 단위 - 지식베이스를 서로 격리하기 위한 멀티테넌시 기준"""
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(200), nullable=False)
    kakao_channel_id = Column(String(200), nullable=True)  # 이 테넌트에 연결된 카카오 채널
    created_at = Column(DateTime, default=datetime.utcnow)

    contents = relationship("ExpertContent", back_populates="tenant")


class ExpertContent(Base):
    """전문가가 입력한 원본 노하우 (음성/텍스트/숏폼)"""
    __tablename__ = "expert_contents"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)

    author_name = Column(String(100), nullable=False)
    content_type = Column(Enum("voice", "text", "video", "document", name="content_type"), nullable=False)

    raw_text = Column(Text, nullable=False)          # STT 결과 또는 직접 입력한 텍스트
    media_url = Column(String(500), nullable=True)   # 원본 음성/영상 파일 링크 (S3 등)

    process_tag = Column(String(100), nullable=True)   # 공정명 (예: "베어링 교체")
    equipment_tag = Column(String(100), nullable=True)  # 설비명 (예: "3호기 CNC")
    risk_level = Column(Enum("low", "medium", "high", name="risk_level"), default="low")

    status = Column(Enum("pending", "approved", "rejected", name="review_status"),
                     default="pending", nullable=False)  # 관리자 검수 상태
    reviewed_by = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="contents")
    chunks = relationship("ContentChunk", back_populates="content", cascade="all, delete-orphan")


class ContentChunk(Base):
    """RAG 검색 단위로 쪼갠 청크 + 임베딩 벡터"""
    __tablename__ = "content_chunks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    content_id = Column(UUID(as_uuid=False), ForeignKey("expert_contents.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)  # 검색 필터 성능용 비정규화

    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(settings.embedding_dim), nullable=False)

    content = relationship("ExpertContent", back_populates="chunks")


class CompanyGuide(Base):
    """현장 공통 가이드 / 사규 등 정적 대용량 문서.
    개별 노하우(ExpertContent)와 달리 청킹·임베딩하지 않고,
    질의응답 시 Claude 프롬프트 캐싱(cache_control)으로 통째로 재사용해
    반복 질문마다 드는 입력 토큰 비용을 절감한다."""
    __tablename__ = "company_guides"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)

    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)  # 가이드/사규 전문 (내용이 바뀌면 캐시가 자동으로 미스 처리됨)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DifySession(Base):
    """카카오톡 사용자 ↔ Dify 대화(conversation_id) 매핑.
    Dify는 대화 맥락을 conversation_id로 관리하므로, 같은 사용자가 이어서 질문할 때
    이걸 다시 넘겨줘야 대화가 끊기지 않는다."""
    __tablename__ = "dify_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    kakao_user_key = Column(String(200), nullable=False)
    dify_conversation_id = Column(String(200), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QueryLog(Base):
    """카카오톡 사용자 질의응답 로그 - 관리자 대시보드 통계/피드백 루프에 사용"""
    __tablename__ = "query_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)

    kakao_user_key = Column(String(200), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    matched_chunk_ids = Column(JSON, default=list)  # 답변 근거로 사용된 청크 id 목록
    confidence = Column(Float, nullable=True)        # 최상위 검색 유사도 점수
    feedback = Column(Enum("up", "down", name="feedback_type"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
