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

    class Config:
        env_file = ".env"


settings = Settings()
