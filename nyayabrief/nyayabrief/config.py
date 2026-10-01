from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Puts GEMINI_API_KEY / GROQ_API_KEY from .env into os.environ (litellm reads them from there).
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://nyaya:nyaya@localhost:5432/nyayabrief"
    llm_chain: str = "gemini/gemini-3.1-flash-lite,groq/llama-3.3-70b-versatile"
    classify_chain: str = ""  # empty -> use llm_chain
    embed_model: str = "gemini/gemini-embedding-001"
    embeddings_enabled: bool = True
    embed_dim: int = 768
    llm_min_interval_sec: float = 4.0
    admin_password: str = ""  # empty -> Admin tab hidden (viewer deployment)
    prompt_version: str = "v1"  # bump when prompts/schema change -> re-extracts
    classify_batch_size: int = 8
    keep_issues: int = 3  # keep only the newest N newspapers; older ones are deleted after each upload


@lru_cache
def get_settings() -> Settings:
    return Settings()
