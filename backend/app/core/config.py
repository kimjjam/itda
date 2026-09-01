from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    blob_read_write_token: str
    kosis_api_key: str
    exim_exchange_api_key: str
    llm_api_key: str
    llm_model: str
    llm_api_base_url: str
    frontend_origin: str
    request_timeout_seconds: float = 8.0
    external_cache_ttl_seconds: int = 1800
    max_upload_bytes: int = 10 * 1024 * 1024

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def document_storage_configured(self) -> bool:
        return bool(self.database_url and self.blob_read_write_token)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model and self.llm_api_base_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", ""),
        blob_read_write_token=os.getenv("BLOB_READ_WRITE_TOKEN", ""),
        kosis_api_key=os.getenv("KOSIS_API_KEY", ""),
        exim_exchange_api_key=os.getenv("EXIM_EXCHANGE_API_KEY", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_api_base_url=os.getenv("LLM_API_BASE_URL", "").rstrip("/"),
        frontend_origin=os.getenv(
            "FRONTEND_ORIGIN",
            "http://localhost:5173,http://127.0.0.1:5173",
        ),
    )
