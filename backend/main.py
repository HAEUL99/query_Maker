"""Text-to-SQL RAG FastAPI 애플리케이션 진입점입니다."""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO)
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router as api_router
from backend.config import get_settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(rel_or_abs: str) -> Path:
    """설정값 경로를 프로젝트 루트 기준으로 해석합니다(절대 경로는 그대로)."""
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return (PROJECT_ROOT / p).resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """시작 시 필요한 디렉터리를 만들고 주요 설정을 로그로 남깁니다."""
    settings = get_settings()
    chroma_dir = _resolve_path(settings.CHROMA_PERSIST_DIR)
    chroma_dir.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "data" / "excel").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "data" / "excel" / "sample_customer").mkdir(
        parents=True, exist_ok=True
    )
    (PROJECT_ROOT / "data" / "excel" / "sample_admin").mkdir(
        parents=True, exist_ok=True
    )

    logger.info("LLM 모델: %s", settings.LLM_MODEL)
    logger.info("임베딩 모델: %s", settings.EMBEDDING_MODEL)
    logger.info("벡터 DB 경로: %s", chroma_dir)

    yield


APP = FastAPI(
    title="Text-to-SQL RAG API",
    version="1.0.0",
    lifespan=lifespan,
)

APP.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APP.include_router(api_router)


@APP.get("/")
def root() -> dict[str, str]:
    """서비스 메타 정보를 반환합니다."""
    return {
        "service": "Text-to-SQL RAG",
        "version": "1.0.0",
        "docs": "/docs",
    }


@APP.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """처리되지 않은 예외를 공통 형식으로 반환합니다(HTTP·검증 오류는 FastAPI 기본 처리)."""
    logger.exception("처리되지 않은 서버 오류: %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "내부 서버 오류", "detail": str(exc)},
    )


app = APP
