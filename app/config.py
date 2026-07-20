from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/knowhow_rag"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384

    top_k: int = 5
    similarity_threshold: float = 0.3

    kakao_skill_secret: str = "change-me"

    # 현장 공통 가이드/사규 문서 전용 - Claude 프롬프트 캐싱(cache_control)
    # 목적: 자주 반복 재사용되는 대용량 정적 문서를 캐싱해 입력 토큰 비용을 절감.
    # 같은 Anthropic API 키/클라이언트를 그대로 쓰며, 별도 캐시 리소스 관리가 필요 없다
    # (요청마다 동일한 문서 블록을 cache_control과 함께 보내면 Anthropic 서버가 자동으로 캐시 적중 처리).
    guide_cache_ttl: str = "1h"  # "5m"(기본, 무료) 또는 "1h"(쓰기 비용 2배지만 오래 유지)

    # Dify로 만든 챗봇을 카카오톡과 연결할 때 사용 (자체 RAG 챗봇과는 별개 경로)
    dify_api_base: str = "https://api.dify.ai/v1"  # 셀프호스팅이면 그 서버 주소로 교체
    dify_api_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
