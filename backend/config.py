"""애플리케이션 설정을 로드하고 싱글턴으로 제공하는 모듈입니다."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """`.env` 파일 및 환경 변수에서 읽어 오는 런타임 설정입니다."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GOOGLE_API_KEY: str
    EMBEDDING_MODEL: str
    LLM_MODEL: str
    CHROMA_PERSIST_DIR: str
    """레거시: 설정 시 고객용 컬렉션 이름으로 사용(하위 호환)."""
    CHROMA_COLLECTION: str | None = None
    CHROMA_COLLECTION_CUSTOMER: str = "table_schemas_customer"
    CHROMA_COLLECTION_ADMIN: str = "table_schemas_admin"
    TOP_K_RESULTS: int = 8
    MAX_TOKENS_CONTEXT: int = 6000
    """관리자 로그인 비밀번호(비어 있으면 관리자 API 비활성)."""
    ADMIN_PASSWORD: str = ""
    """관리자 토큰 HMAC용 비밀(미설정 시 ADMIN_PASSWORD를 사용)."""
    ADMIN_JWT_SECRET: str = ""
    """True이면 인덱싱 시 풀별 테이블명(파일명) 정규식을 검사합니다."""
    TABLE_NAME_POOL_VALIDATION: bool = True
    """고객 풀: TBL_ 뒤는 밑줄 없이 한 덩어리(예: TBL_CUSTDIM, TBL_WFGWFL0514)."""
    TABLE_NAME_REGEX_CUSTOMER: str = r"^TBL_[A-Z0-9]+$"
    """관리자 풀: TB_ 뒤는 밑줄 없이 한 덩어리(예: TB_FNMGT014, TB_BUDGETFACT)."""
    TABLE_NAME_REGEX_ADMIN: str = r"^TB_[A-Z0-9]+$"

    def customer_collection_name(self) -> str:
        """고객용 스키마가 저장되는 Chroma 컬렉션 이름입니다."""
        if self.CHROMA_COLLECTION and self.CHROMA_COLLECTION.strip():
            return self.CHROMA_COLLECTION.strip()
        return self.CHROMA_COLLECTION_CUSTOMER

    def admin_token_secret(self) -> str:
        """관리자 Bearer 토큰 서명에 쓰는 비밀값입니다."""
        s = (self.ADMIN_JWT_SECRET or "").strip()
        if s:
            return s
        return self.ADMIN_PASSWORD or "change-me"


@lru_cache()
def get_settings() -> Settings:
    """캐시된 `Settings` 인스턴스를 반환합니다. 프로세스 내에서 동일 객체를 재사용합니다."""
    return Settings()
