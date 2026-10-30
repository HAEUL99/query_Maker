"""Text-to-SQL RAG REST API 라우트입니다."""

from __future__ import annotations

import logging
import re
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
from backend.api.screen_context import (
    build_screen_context_text,
    call_screen_chat,
    run_screen_mapping,
)
from backend.config import get_settings
from backend.generator.clarification_heuristics import (
    run_clarification_heuristics,
    schemas_from_search_results,
)
from backend.generator.sql_generator import SQLGenerator
from backend.models import TableSchema
from backend.parser.dbio_parser import parse_all as dbio_parse_all
from backend.parser.excel_parser import parse_file, validate_references
from backend.schema_naming import canonical_pool_table_name, pool_table_name_violation
from backend.vectorstore.chroma_store import SchemaPool, SchemaVectorStore

logger = logging.getLogger(__name__)

store = SchemaVectorStore()
generator = SQLGenerator()

router = APIRouter(prefix="/api", tags=["api"])

_TB_NAME_RE = re.compile(r"\b(TB_[A-Z0-9]+)\b", re.IGNORECASE)


def _conversation_user_text(query: str, history: list["HistoryMessage"]) -> str:
    """대화에서 사용자 발화만 시간 순으로 이어 붙입니다(벡터 검색·테이블 추론용)."""
    parts: list[str] = []
    for msg in history:
        if msg.role == "user":
            t = (msg.content or "").strip()
            if t:
                parts.append(t)
    q = (query or "").strip()
    if q:
        parts.append(q)
    return " ".join(parts)


def _extract_admin_table_names(text: str) -> list[str]:
    """본문에 등장하는 TB_* 식별자(대소문자 무시)를 정규화해 중복 없이 반환합니다."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _TB_NAME_RE.finditer(text or ""):
        canon = canonical_pool_table_name(m.group(1))
        if canon.startswith("TB_") and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


def _excluded_admin_tables(text: str) -> set[str]:
    """«~말고», «~빼고» 등으로 사용자가 제외한 TB_* (한 발화 문자열 기준)."""
    drop: set[str] = set()
    seg = (text or "").strip()
    if not seg:
        return drop
    markers = ("말고", "빼고", "제외", "쓰지 말", "아닌")
    if not any(m in seg for m in markers):
        return drop
    for m in re.finditer(
        r"(tb_[a-z0-9]+)\s*(?:말고|빼(?:고)?|말야)\b",
        seg,
        re.IGNORECASE,
    ):
        drop.add(canonical_pool_table_name(m.group(1)))
    for m in re.finditer(
        r"(?:말고|빼고|제외|쓰지\s*말)\s*(?:.*?)(tb_[a-z0-9]+)\b",
        seg,
        re.IGNORECASE,
    ):
        drop.add(canonical_pool_table_name(m.group(1)))
    return drop


def _excluded_admin_tables_from_conversation(
    query: str, history: list["HistoryMessage"]
) -> set[str]:
    drop: set[str] = set()
    for msg in history:
        if msg.role == "user":
            drop |= _excluded_admin_tables(msg.content or "")
    drop |= _excluded_admin_tables(query or "")
    return drop


def _infer_admin_tables_from_korean(text: str) -> list[str]:
    """연체·특수채권 등 업무 키워드 → 관리자 풀 TB_* (정의서 샘플 기준)."""
    q = text or ""
    tables: list[str] = []
    if "연체" in q or "연체관리" in q:
        tables.append("TB_FNDLY003")
    if "특수채권" in q:
        tables.append("TB_FNBAD025")
    if "TB_FNBAD025" in q.upper() or "FNBAD025" in q.upper():
        tables.append("TB_FNBAD025")
    return tables


def _admin_tables_to_inject(query: str, history: list["HistoryMessage"]) -> list[str]:
    """멀티턴·키워드·명시 TB_*로 스키마 컨텍스트 앞에 둘 테이블 목록."""
    convo = _conversation_user_text(query, history)
    latest = (query or "").strip()
    exclude = _excluded_admin_tables_from_conversation(query, history)

    ordered: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        c = canonical_pool_table_name(name)
        if not c.startswith("TB_") or c in seen or c in exclude:
            return
        seen.add(c)
        ordered.append(c)

    # 최신 발화에 적힌 TB_*를 최우선(«tb_fndly003 테이블 말이야» 등)
    for name in _extract_admin_table_names(latest):
        add(name)
    for name in _extract_admin_table_names(convo):
        add(name)
    for name in _infer_admin_tables_from_korean(convo):
        add(name)
    for name in _oracle_admin_augment_table_names(convo):
        add(name)

    return ordered


def _filter_search_results(
    results: list[Any], exclude: set[str]
) -> list[Any]:
    if not exclude:
        return results
    return [
        r
        for r in results
        if canonical_pool_table_name(r.table_name) not in exclude
    ]


def _search_query_with_history(query: str, history: list["HistoryMessage"]) -> str:
    """추가 요청(멀티턴)일 때 벡터 검색이 맥락을 잃지 않도록 사용자 발화 전체를 사용합니다."""
    convo = _conversation_user_text(query, history)
    return convo if convo else (query or "").strip()


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


class HistoryMessage(BaseModel):
    """대화 히스토리 항목입니다."""

    role: Literal["user", "assistant"]
    content: str


class QueryRequest(BaseModel):
    """자연어 질의 요청 본문입니다."""

    query: str
    dialect: Literal["oracle", "sas"]
    domain: str | None = None
    top_k: int | None = None
    schema_pool: Literal["customer", "admin"] = "customer"
    """Oracle 관리자 모드에서만 의미 있는 프로필(select_only: 조회만, admin_dml: INSERT/UPDATE/DELETE/MERGE 허용)."""
    oracle_profile: Literal["select_only", "admin_dml"] = "select_only"
    history: list[HistoryMessage] = []


class ClarificationItemResponse(BaseModel):
    """구조화된 추가 질문 한 건."""

    id: str
    question: str
    kind: Literal["single", "text"] = "single"
    options: list[str] = []


class QueryResponse(BaseModel):
    """SQL 생성 응답입니다."""

    sql: str | None
    explanation: str
    used_tables: list[str]
    confidence: str
    clarification_needed: str | None
    clarifications: list[ClarificationItemResponse] = []
    dialect: str
    schema_pool: str
    oracle_profile: str | None
    search_results: list[dict[str, Any]]
    screen_maps: list[dict[str, Any]]
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

_QUERY_SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "querySample"
_SAEDOYAK_DEMO_SQL_FILES: dict[str, str] = {
    "sas_step1": "새도약기금 매각 대상건 산출_sas_step1.sql",
    "sas_step2": "새도약기금 매각 대상건 산출_sas_step2.sql",
    "oracle": "새도약기금 매각 대상건 산출.sql",
}


class SaedoyakDemoSqlResponse(BaseModel):
    sql: str
    source: str
    file_name: str


@router.get("/demo/saedoyak-sql", response_model=SaedoyakDemoSqlResponse)
def get_saedoyak_demo_sql(
    source: Literal["sas_step1", "sas_step2", "oracle"] = Query(
        ...,
        description="시연 SQL 파일 (디스크에서 매 요청 읽음)",
    ),
) -> SaedoyakDemoSqlResponse:
    """새도약기금 시연용 SQL을 querySample 파일에서 반환합니다."""
    file_name = _SAEDOYAK_DEMO_SQL_FILES.get(source)
    if not file_name:
        raise HTTPException(status_code=400, detail="지원하지 않는 source")
    path = _QUERY_SAMPLE_DIR / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"파일 없음: {file_name}")
    return SaedoyakDemoSqlResponse(
        sql=path.read_text(encoding="utf-8"),
        source=source,
        file_name=file_name,
    )


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

    search_query = _search_query_with_history(body.query, body.history)

    # 화면-테이블 매핑(HFSR SFNRCV767 등): 고객(SAS) 질의에만 사용. 관리자 Oracle TB_ 질의와 혼선·UI 노출 방지.
    screen_hits: list[dict[str, Any]] = []
    injected_tables_from_screen: list[str] = []
    screen_context_docs: list[str] = []
    if pool == "customer":
        screen_hits = store.search_screen_map(search_query, top_k=2)
        for hit in screen_hits:
            if hit.get("score", 0) >= 0.6:
                screen_context_docs.append(hit["document"])
                injected_tables_from_screen.extend(hit.get("tables", []))

    results = store.search(
        search_query,
        top_k=body.top_k,
        domain=body.domain,
        schema_pool=pool,
    )
    if not results and body.domain is not None:
        results = store.search(
            search_query,
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

    # 화면 매핑에서 추출된 테이블 스키마를 컨텍스트 앞에 주입
    if injected_tables_from_screen:
        results = store.augment_search_replace_tables(
            results, injected_tables_from_screen, schema_pool=pool
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
        aug = _sas_customer_augment_table_names(search_query)
        if aug:
            results = store.augment_search_replace_tables(
                results, aug, schema_pool=pool
            )

    if pool == "admin" and body.dialect == "oracle":
        exclude = _excluded_admin_tables_from_conversation(
            body.query, body.history
        )
        inject = _admin_tables_to_inject(body.query, body.history)
        aug_o = _oracle_admin_augment_table_names(search_query)
        merged = list(dict.fromkeys(inject + (aug_o or [])))
        if merged:
            results = store.augment_search_replace_tables(
                results, merged, schema_pool="admin"
            )
        if exclude:
            results = _filter_search_results(results, exclude)

    # 화면-테이블 매핑 정보를 쿼리 앞에 삽입하여 Gemini가 화면 맥락을 이해하도록 합니다.
    effective_query = body.query
    if pool == "admin" and body.dialect == "oracle" and body.history:
        inject_names = _admin_tables_to_inject(body.query, body.history)
        exclude = _excluded_admin_tables_from_conversation(
            body.query, body.history
        )
        hint_lines: list[str] = []
        if inject_names:
            hint_lines.append(
                f"- 우선 사용할 테이블: {', '.join(inject_names)}"
            )
        if exclude:
            hint_lines.append(
                f"- 사용하지 말 것: {', '.join(sorted(exclude))}"
            )
        if hint_lines:
            effective_query = (
                "[테이블 지시]\n"
                + "\n".join(hint_lines)
                + f"\n\n[현재 사용자 요청]\n{body.query}"
            )
    if screen_context_docs:
        screen_ctx = "\n".join(screen_context_docs)
        effective_query = f"[화면 정보]\n{screen_ctx}\n\n[질문]\n{body.query}"

    gen = generator.generate(
        effective_query,
        body.dialect,
        results,
        oracle_profile=oracle_profile,
        history=[{"role": h.role, "content": h.content} for h in body.history],
    )

    clar_schemas = schemas_from_search_results(
        store,
        results,
        schema_pool=pool,
    )
    gen = run_clarification_heuristics(
        query=body.query,
        history=body.history,
        table_schemas=clar_schemas,
        gen=gen,
        dialect=body.dialect,
        oracle_profile=oracle_profile,
    )

    search_results = [
        {"table": r.table_name, "score": round(r.score, 3)} for r in results
    ]
    matched_screens = [
        {
            "screen_id":   h["screen_id"],
            "screen_name": h["screen_name"],
            "tables":      h["tables"],
            "score":       round(h["score"], 3),
        }
        for h in screen_hits
        if h.get("score", 0) >= 0.6
    ]

    return QueryResponse(
        sql=gen.sql,
        explanation=gen.explanation,
        used_tables=gen.used_tables,
        confidence=str(gen.confidence),
        clarification_needed=gen.clarification_needed,
        clarifications=[
            ClarificationItemResponse(
                id=c.id,
                question=c.question,
                kind=c.kind,
                options=list(c.options),
            )
            for c in gen.clarifications
        ],
        dialect=gen.dialect,
        schema_pool=pool,
        oracle_profile=oracle_profile if body.dialect == "oracle" else None,
        search_results=search_results,
        screen_maps=matched_screens,
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


@router.delete("/tables/{table_name}")
def delete_table(
    table_name: str,
    schema_pool: Literal["customer", "admin"] = Query("customer"),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """(관리자 전용) 테이블 단건을 벡터스토어에서 삭제합니다."""
    _require_admin_bearer(authorization)
    deleted = store.delete_table(table_name, schema_pool=schema_pool)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"테이블을 찾을 수 없습니다: {table_name}",
        )
    return {"deleted": table_name, "schema_pool": schema_pool}


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


# --- DBIO 파싱 & 인덱싱 ---


class DbioIndexResponse(BaseModel):
    """DBIO 파싱·인덱싱 결과입니다."""

    status:   str
    indexed:  int
    screens:  list[dict[str, Any]]
    errors:   list[str]


@router.post("/index/dbio", response_model=DbioIndexResponse)
def post_index_dbio(
    authorization: Annotated[str | None, Header()] = None,
) -> DbioIndexResponse:
    """(관리자 전용) data/mock_up/{jsp,pc,sql} 폴더를 파싱해 화면-테이블 매핑을 인덱싱합니다."""
    _require_admin_bearer(authorization)

    try:
        screen_maps = dbio_parse_all()
    except Exception as exc:
        logger.exception("DBIO 파싱 중 오류")
        raise HTTPException(
            status_code=500,
            detail=f"DBIO 파싱 실패: {exc}",
        ) from exc

    if not screen_maps:
        return DbioIndexResponse(
            status="ok",
            indexed=0,
            screens=[],
            errors=["파싱 결과가 없습니다. data/mock_up/{jsp,pc,sql} 폴더를 확인하세요."],
        )

    idx_result = store.index_screen_map(screen_maps)
    indexed    = int(idx_result.get("indexed", 0))
    errors     = list(idx_result.get("errors") or [])

    screens_out = [
        {
            "screen_id":   sm["screen_id"],
            "screen_name": sm["screen_name"],
            "service":     sm["service"],
            "dbio_file":   sm["dbio_file"],
            "tables":      sm["tables"],
        }
        for sm in screen_maps
    ]

    return DbioIndexResponse(
        status="ok" if not errors else "partial",
        indexed=indexed,
        screens=screens_out,
        errors=errors,
    )


@router.get("/screen-maps")
def get_screen_maps(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """(관리자 전용) 인덱싱된 화면-테이블 매핑 목록과 통계를 반환합니다."""
    _require_admin_bearer(authorization)
    stats = store.get_screen_map_stats()
    return {"stats": stats}


@router.get("/screen-maps/search")
def get_screen_maps_search(
    q: str = Query(..., description="검색 질의 (예: 수납 마감자료 조회)"),
    top_k: int = Query(3, ge=1, le=10),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """화면-테이블 매핑을 자연어로 검색합니다."""
    _require_admin_bearer(authorization)
    results = store.search_screen_map(q, top_k=top_k)
    return {"results": results, "total": len(results)}


# --- HFSR 화면 미니 챗봇 및 DNA 컬럼 매핑 ---


class HfsrColumn(BaseModel):
    """HFSR 컬럼 정보입니다."""
    col_name: str
    col_ko: str = ""


class ScreenChatMessage(BaseModel):
    """화면 챗봇 대화 메시지입니다."""
    role: Literal["user", "assistant"]
    content: str


class ScreenChatRequest(BaseModel):
    """화면 데이터 기반 챗봇 질의 요청입니다."""
    screen_id: str = "SFNRCV767"
    screen_name: str = "수납 마감자료 조회"
    active_tab: str = "수납내역"
    filters: dict[str, str] = {}
    columns: list[str] = []
    rows: list[list[str]] = []
    total_row: list[str] | None = None
    question: str
    history: list[ScreenChatMessage] = []


class ScreenChatResponse(BaseModel):
    """화면 챗봇 응답입니다."""
    answer: str


class ScreenMappingRequest(BaseModel):
    """HFSR→DNA 컬럼 매핑 요청입니다."""
    hfsr_cols: list[HfsrColumn]


class ScreenMappingResponse(BaseModel):
    """HFSR→DNA 컬럼 매핑 응답입니다."""
    mappings: list[dict[str, Any]]
    dna_table_count: int
    openai_used: bool


@router.post("/screen-chat", response_model=ScreenChatResponse)
def post_screen_chat(body: ScreenChatRequest) -> ScreenChatResponse:
    """현재 화면 데이터를 컨텍스트로 Gemini에게 질문합니다."""
    ctx = build_screen_context_text(
        screen_id=body.screen_id,
        screen_name=body.screen_name,
        active_tab=body.active_tab,
        filters=body.filters,
        columns=body.columns,
        rows=body.rows,
        total_row=body.total_row,
    )
    answer = call_screen_chat(
        screen_context=ctx,
        question=body.question,
        history=[{"role": m.role, "content": m.content} for m in body.history],
    )
    return ScreenChatResponse(answer=answer)


@router.post("/screen-mapping", response_model=ScreenMappingResponse)
def post_screen_mapping(body: ScreenMappingRequest) -> ScreenMappingResponse:
    """HFSR 화면 컬럼 한글명을 관리자 풀(DNA)의 컬럼과 유사도 기반으로 매핑합니다."""
    settings = get_settings()
    hfsr_cols = [{"col_name": c.col_name, "col_ko": c.col_ko} for c in body.hfsr_cols]
    results = run_screen_mapping(hfsr_cols, store)

    dna_tables = set(
        r.dna_table for r in results if r.dna_table
    )

    openai_used = any(r.method == "openai" for r in results)

    mappings = [
        {
            "hfsr_col": r.hfsr_col,
            "hfsr_ko": r.hfsr_ko,
            "status": r.status,
            "dna_table": r.dna_table,
            "dna_col": r.dna_col,
            "dna_ko": r.dna_ko,
            "score": round(r.score, 3),
            "method": r.method,
            "message": r.message,
            "candidates": [
                {
                    "table_name": c.table_name,
                    "col_name": c.col_name,
                    "col_ko": c.col_ko,
                    "score": round(c.score, 3),
                }
                for c in r.candidates
            ],
        }
        for r in results
    ]

    return ScreenMappingResponse(
        mappings=mappings,
        dna_table_count=len(dna_tables),
        openai_used=openai_used,
    )
