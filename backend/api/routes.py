"""Text-to-SQL RAG REST API 라우트입니다."""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.api.auth_admin import (
    constant_time_equal_password,
    create_admin_token,
    verify_admin_token,
)
from backend.config import get_settings
from backend.generator.sql_generator import SQLGenerator
from backend.models import TableSchema
from backend.parser.excel_parser import parse_file, validate_references
from backend.schema_naming import pool_table_name_violation
from backend.vectorstore.chroma_store import SchemaPool, SchemaVectorStore

logger = logging.getLogger(__name__)

store = SchemaVectorStore()
generator = SQLGenerator()

router = APIRouter(prefix="/api", tags=["api"])


def _sas_customer_augment_table_names(query: str) -> list[str]:
    """SAS 예시 질의 등에서 핵심 팩트·차원 테이블이 검색에서 빠지면 스키마를 직접 넣습니다."""
    q = query or ""

    if any(x in q for x in ("성별", "남성", "여성")) and any(
        x in q for x in ("고객", "구매", "매출", "금액", "평균", "수", "건수")
    ):
        return ["TBL_CUSTDIM", "TBL_SALEFACT"]

    has_product = any(
        x in q
        for x in (
            "상품",
            "제품",
            "품목",
            "상품명",
            "제품명",
            "PROD_ID",
        )
    )
    has_sales = any(
        x in q
        for x in (
            "판매",
            "매출",
            "단가",
            "건수",
            "수량",
            "매출액",
        )
    )
    rank_time_ctx = any(
        x in q for x in ("상위", "인기", "개월", "최근", "순위")
    )
    if has_product and (has_sales or rank_time_ctx):
        return ["TBL_SALEFACT", "TBL_PRODUCTDIM"]

    trend = any(
        x in q
        for x in ("월별", "연도별", "일별", "추이", "집계", "총매출")
    )
    if trend and any(x in q for x in ("매출", "판매", "매출액")):
        return ["TBL_SALEFACT"]

    if "직급" in q and "연봉" in q:
        return ["TBL_EMPDIM"]

    return []


def _oracle_admin_augment_table_names(query: str) -> list[str]:
    """관리자 Oracle 예시 질의에 맞춰 TB_* 핵심 테이블을 컨텍스트 앞에 둡니다."""
    q = query or ""
    if (
        any(k in q for k in ("예산", "실적률"))
        or ("실적" in q and "예산" in q)
        or ("부서" in q and "예산" in q)
    ) and not any(
        k in q for k in ("판매", "카테고리", "상품", "매출상위")
    ):
        return ["TB_BUDGETFACT"]
    if "카테고리" in q or ("수량" in q and "판매" in q):
        return ["TB_PRODUCTDIM", "TB_SALEFACT"]
    if any(
        k in q
        for k in (
            "고객",
            "매출",
            "구매",
            "지난달",
            "신규",
            "이번달",
            "평균",
        )
    ):
        return ["TB_CUSTDIM", "TB_SALEFACT"]
    return []


def _require_admin_bearer(authorization: str | None) -> None:
    """Authorization: Bearer 토큰으로 관리자 여부를 검증합니다."""
    settings = get_settings()
    pw = (settings.ADMIN_PASSWORD or "").strip()
    if not pw:
        raise HTTPException(
            status_code=503,
            detail="관리자 기능이 비활성화되어 있습니다. .env에 ADMIN_PASSWORD를 설정하세요.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="관리자 인증이 필요합니다.")
    token = authorization.split(" ", 1)[1].strip()
    secret = settings.admin_token_secret()
    if not verify_admin_token(token, secret):
        raise HTTPException(
            status_code=401,
            detail="유효하지 않거나 만료된 관리자 토큰입니다.",
        )


# --- Pydantic 모델 ---


class LoginRequest(BaseModel):
    """관리자 로그인 요청입니다."""

    password: str


class LoginResponse(BaseModel):
    """관리자 로그인 응답입니다."""

    access_token: str
    token_type: str = "bearer"


class QueryRequest(BaseModel):
    """자연어 질의 요청 본문입니다."""

    query: str
    dialect: Literal["oracle", "sas"]
    domain: str | None = None
    top_k: int | None = None
    schema_pool: Literal["customer", "admin"] = "customer"
    """Oracle 관리자 모드에서만 의미 있는 프로필(select_only: 조회만, admin_dml: INSERT/UPDATE/DELETE/MERGE 허용)."""
    oracle_profile: Literal["select_only", "admin_dml"] = "select_only"


class QueryResponse(BaseModel):
    """SQL 생성 응답입니다."""

    sql: str | None
    explanation: str
    used_tables: list[str]
    confidence: str
    clarification_needed: str | None
    dialect: str
    schema_pool: str
    oracle_profile: str | None
    search_results: list[dict[str, Any]]
    tokens: dict[str, int]


class IndexResponse(BaseModel):
    """엑셀 인덱싱 결과입니다."""

    status: str
    indexed: int
    tables: list[str]
    warnings: list[str]
    errors: list[str]
    schema_pool: str


class TableListResponse(BaseModel):
    """테이블 목록 응답입니다."""

    tables: list[dict[str, Any]]
    total: int


class StatsResponse(BaseModel):
    """벡터스토어 통계 응답입니다."""

    total_tables: int
    by_domain: dict[str, int]
    model: str
    collection: str
    schema_pool: str


def _table_schema_to_detail(ts: TableSchema) -> dict[str, Any]:
    """테이블 스키마를 API용 dict로 직렬화합니다."""
    cols: list[dict[str, Any]] = []
    for c in ts.columns:
        cols.append(
            {
                "name": c.name,
                "korean_name": c.korean_name,
                "data_type": c.data_type,
                "is_pk": c.is_pk,
                "is_fk": c.is_fk,
                "fk_reference": c.fk_reference,
                "nullable": c.nullable,
                "description": c.description,
                "is_indexed": c.is_indexed,
            }
        )
    return {
        "table_name": ts.table_name,
        "korean_name": ts.korean_name,
        "domain": ts.domain,
        "description": ts.description,
        "source_file": ts.source_file,
        "columns": cols,
    }


# --- 엔드포인트 ---


@router.post("/auth/login", response_model=LoginResponse)
def post_auth_login(body: LoginRequest) -> LoginResponse:
    """관리자 비밀번호가 맞으면 Bearer 토큰을 발급합니다."""
    settings = get_settings()
    pw = (settings.ADMIN_PASSWORD or "").strip()
    if not pw:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_PASSWORD가 설정되어 있지 않습니다.",
        )
    if not constant_time_equal_password(pw, body.password):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    token = create_admin_token(settings.admin_token_secret())
    return LoginResponse(access_token=token)


@router.post("/query", response_model=QueryResponse)
def post_query(
    body: QueryRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> QueryResponse:
    """자연어 질의로 관련 테이블을 검색한 뒤 SQL을 생성합니다."""
    pool: SchemaPool = body.schema_pool
    oracle_profile: Literal["select_only", "admin_dml"] = body.oracle_profile

    if body.dialect == "sas":
        if pool != "customer":
            raise HTTPException(
                status_code=400,
                detail="SAS PROC SQL은 고객 스키마 풀(schema_pool=customer)만 사용할 수 있습니다.",
            )
        oracle_profile = "select_only"
    else:
        _require_admin_bearer(authorization)
        if pool != "admin":
            raise HTTPException(
                status_code=400,
                detail="Oracle SQL은 관리자 스키마 풀(schema_pool=admin)만 사용할 수 있습니다.",
            )

    results = store.search(
        body.query,
        top_k=body.top_k,
        domain=body.domain,
        schema_pool=pool,
    )
    if not results and body.domain is not None:
        results = store.search(
            body.query,
            top_k=body.top_k,
            domain=None,
            schema_pool=pool,
        )
    if not results and pool == "admin":
        admin_rows = store.list_tables(domain=None, schema_pool="admin")
        if admin_rows:
            logger.info(
                "관리자 풀: 벡터 검색 무결과 → 풀 내 %s개 테이블 스키마로 컨텍스트 보강",
                len(admin_rows),
            )
            results = store.search_results_from_all_tables(
                schema_pool="admin",
                max_tables=40,
            )
    if not results:
        empty_hint = ""
        if pool == "admin":
            n_admin = len(store.list_tables(schema_pool="admin"))
            if n_admin == 0:
                empty_hint = (
                    " 관리자 스키마 풀에 인덱싱된 테이블이 없습니다. "
                    "관리자 탭에서 업로드 대상을「관리자 풀」로 두고 정의서를 올려 주세요."
                )
        raise HTTPException(
            status_code=404,
            detail=(
                "질의와 유사한 테이블을 벡터 검색에서 찾지 못했습니다."
                " 도메인 필터·질의 표현을 바꿔 보거나, 해당 풀에 정의서가 올라가 있는지 확인하세요."
                + empty_hint
            ),
        )

    if pool == "customer" and body.dialect == "sas":
        aug = _sas_customer_augment_table_names(body.query)
        if aug:
            results = store.augment_search_replace_tables(
                results, aug, schema_pool=pool
            )

    if pool == "admin" and body.dialect == "oracle":
        aug_o = _oracle_admin_augment_table_names(body.query)
        if aug_o:
            results = store.augment_search_replace_tables(
                results, aug_o, schema_pool="admin"
            )

    gen = generator.generate(
        body.query,
        body.dialect,
        results,
        oracle_profile=oracle_profile,
    )

    search_results = [
        {"table": r.table_name, "score": round(r.score, 3)} for r in results
    ]

    return QueryResponse(
        sql=gen.sql,
        explanation=gen.explanation,
        used_tables=gen.used_tables,
        confidence=str(gen.confidence),
        clarification_needed=gen.clarification_needed,
        dialect=gen.dialect,
        schema_pool=pool,
        oracle_profile=oracle_profile if body.dialect == "oracle" else None,
        search_results=search_results,
        tokens={
            "input": gen.input_tokens,
            "output": gen.output_tokens,
        },
    )


@router.post("/index", response_model=IndexResponse)
async def post_index(
    authorization: Annotated[str | None, Header()] = None,
    schema_pool: Annotated[Literal["customer", "admin"], Form()] = "customer",
    files: list[UploadFile] = File(..., description="인덱싱할 .xlsx 파일 목록"),
) -> IndexResponse:
    """(관리자 전용) 업로드된 엑셀을 지정 스키마 풀에 인덱싱합니다."""
    _require_admin_bearer(authorization)

    if not files:
        raise HTTPException(status_code=400, detail="업로드된 파일이 없습니다.")

    pool: SchemaPool = schema_pool
    schemas: list[TableSchema] = []
    errors: list[str] = []
    temp_paths: list[Path] = []

    try:
        for upload in files:
            name = upload.filename or ""
            if not name.lower().endswith(".xlsx"):
                errors.append(f"{name or '(이름없음)'}: .xlsx 파일만 업로드할 수 있습니다.")
                continue

            suffix = Path(name).suffix or ".xlsx"
            tmp = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}{suffix}"
            temp_paths.append(tmp)

            try:
                with tmp.open("wb") as out:
                    shutil.copyfileobj(upload.file, out)
            except Exception as exc:
                errors.append(f"{name}: 임시 저장 실패 — {exc}")
                continue

            try:
                schemas.extend(parse_file(tmp))
            except ValueError as exc:
                errors.append(f"{name}: 파싱 실패 — {exc}")
            except Exception as exc:
                logger.exception("엑셀 파싱 오류: %s", name)
                errors.append(f"{name}: 파싱 중 오류 — {exc}")

        if not schemas:
            return IndexResponse(
                status="failed",
                indexed=0,
                tables=[],
                warnings=[],
                errors=errors,
                schema_pool=pool,
            )

        settings_nm = get_settings()
        naming_errs: list[str] = []
        for s in schemas:
            src = Path(s.source_file).name
            bad = pool_table_name_violation(s.table_name, pool, settings_nm)
            if bad:
                naming_errs.append(f"{src} [{s.table_name}]: {bad}")
        if naming_errs:
            return IndexResponse(
                status="failed",
                indexed=0,
                tables=[],
                warnings=[],
                errors=errors + naming_errs,
                schema_pool=pool,
            )

        idx_result = store.index_schemas(schemas, reset=False, schema_pool=pool)
        warnings = validate_references(schemas)

        indexed = int(idx_result.get("indexed", 0))
        idx_errors = list(idx_result.get("errors") or [])
        all_errors = errors + [str(e) for e in idx_errors]

        table_names = [s.table_name for s in schemas]
        if indexed > 0 and not all_errors:
            status = "ok"
        elif indexed > 0:
            status = "partial"
        else:
            status = "failed"

        return IndexResponse(
            status=status,
            indexed=indexed,
            tables=table_names,
            warnings=warnings,
            errors=all_errors,
            schema_pool=pool,
        )
    finally:
        for upload in files:
            try:
                await upload.close()
            except Exception:
                pass
        for p in temp_paths:
            try:
                if p.is_file():
                    p.unlink()
            except OSError:
                logger.warning("임시 파일 삭제 실패: %s", p)


@router.post("/index/reset")
def post_index_reset(
    authorization: Annotated[str | None, Header()] = None,
    schema_pool: Literal["customer", "admin"] = Query(
        "customer",
        description="초기화할 스키마 풀",
    ),
) -> dict[str, str]:
    """(관리자 전용) 지정 풀의 벡터 인덱스를 비웁니다."""
    _require_admin_bearer(authorization)
    store.reset(schema_pool=schema_pool)
    return {
        "status": "ok",
        "message": f"인덱스가 초기화되었습니다 ({schema_pool}).",
    }


@router.get("/tables", response_model=TableListResponse)
def get_tables(
    domain: str | None = None,
    schema_pool: Literal["customer", "admin"] = Query("customer"),
    authorization: Annotated[str | None, Header()] = None,
) -> TableListResponse:
    """인덱싱된 테이블 메타데이터 목록을 반환합니다. schema_pool=admin 은 관리자 토큰 필요."""
    if schema_pool == "admin":
        _require_admin_bearer(authorization)
    tables = store.list_tables(domain=domain, schema_pool=schema_pool)
    return TableListResponse(tables=tables, total=len(tables))


@router.get("/tables/{table_name}")
def get_table_detail(
    table_name: str,
    schema_pool: Literal["customer", "admin"] = Query("customer"),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """테이블명으로 단일 테이블 상세 정보를 반환합니다."""
    if schema_pool == "admin":
        _require_admin_bearer(authorization)
    ts = store.get_table(table_name, schema_pool=schema_pool)
    if ts is None:
        raise HTTPException(
            status_code=404,
            detail=f"테이블을 찾을 수 없습니다: {table_name}",
        )
    return _table_schema_to_detail(ts)


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    schema_pool: Literal["customer", "admin"] = Query("customer"),
    authorization: Annotated[str | None, Header()] = None,
) -> StatsResponse:
    """벡터스토어 집계 통계를 반환합니다. admin 풀은 관리자 토큰 필요."""
    if schema_pool == "admin":
        _require_admin_bearer(authorization)
    raw = store.get_stats(schema_pool=schema_pool)
    return StatsResponse(
        total_tables=int(raw.get("total", 0)),
        by_domain=dict(raw.get("by_domain") or {}),
        model=str(raw.get("model", "")),
        collection=str(raw.get("collection", "")),
        schema_pool=str(raw.get("schema_pool", schema_pool)),
    )


@router.get("/schema/naming")
def get_schema_naming() -> dict[str, Any]:
    """고객(TBL_*)·관리자(TB_*) 테이블 명명 규칙 및 검증 설정을 반환합니다."""
    s = get_settings()
    return {
        "validation_enabled": s.TABLE_NAME_POOL_VALIDATION,
        "customer_regex": s.TABLE_NAME_REGEX_CUSTOMER,
        "admin_regex": s.TABLE_NAME_REGEX_ADMIN,
        "customer_hint": (
            "고객 풀: TBL_ 뒤는 밑줄 없이 한 덩어리 "
            "(예: TBL_CUSTDIM.xlsx, TBL_WFGWFL0514.xlsx)"
        ),
        "admin_hint": (
            "관리자 풀: TB_ 뒤는 밑줄 없이 한 덩어리 "
            "(예: TB_FNMGT014.xlsx, TB_BUDGETFACT.xlsx)"
        ),
    }


@router.get("/admin/stats/summary")
def get_admin_stats_summary(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """(관리자 전용) 고객·관리자 풀 통계를 한 번에 반환합니다."""
    _require_admin_bearer(authorization)
    return store.get_stats_all()
