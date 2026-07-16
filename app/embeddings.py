"""
임베딩 모델 래퍼.
운영 환경에서는 이 모델을 상시 로드해두고 재사용합니다 (요청마다 로드 X).
한국어 산업 용어 인식률이 낮으면 도메인 용어집으로 파인튜닝하거나
Ko-SBERT 계열(jhgan/ko-sroberta-multitask) 등으로 교체 검토하세요.
"""
from functools import lru_cache
from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


def embed_text(text: str) -> list[float]:
    model = get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.tolist()
