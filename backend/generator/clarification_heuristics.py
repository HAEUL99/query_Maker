"""검색된 스키마 기준으로 애매한 질의를 구조화 추가 질문으로 바꿉니다."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from backend.models import ClarificationItem, GenerationResult, TableSchema

if TYPE_CHECKING:
    from backend.vectorstore.chroma_store import SchemaVectorStore

_VAGUE_PERIOD = re.compile(
    r"(\d+[.\s년]*\d*\s*월|월\s*이전|월\s*이후|월\s*말|월\s*초|이전|이후|말까지|초까지)",
    re.IGNORECASE,
)
_MONTH_BEFORE_PATTERNS = (
    re.compile(r"(\d{4})\.(\d{1,2})월?이전"),
    re.compile(r"(\d{4})년(\d{1,2})월이전"),
    re.compile(r"(\d{4})-(\d{1,2})월?이전"),
    re.compile(r"(\d{4})[.\s년]*(\d{1,2})\s*월\s*이전"),
)

# 기간 후보에서 빼는 적재·감사 일시
_DATE_COL_SKIP = (
    "LAST_CHNG_DTTM",
    "DNA_DAT_LDNG_DTTM",
    "DW_LOAD_DATE",
)

# 인덱스에 있는 FN 테이블만 (검색 결과에 있을 때만 객관식에 포함)
_KEYWORD_TABLES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("연체관리", "연체"), ("TB_FNDLY003", "TBL_WFGWFD0503")),
    (("특수채권",), ("TB_FNBAD025", "TBL_WFGWFP0525")),
    (("개인회생", "회생"), ("TBL_WFGWFP0575",)),
    (("파산면책", "면책"), ("TBL_WFGWFP0555", "TBL_WFGWFP0605")),
]

_LOAN_INTENT = re.compile(
    r"(대출번호|특정\s*건|해당\s*대출|이\s*대출|대출\s*ID|LOAN_ID)",
    re.IGNORECASE,
)
_LOAN_CONCAT = re.compile(
    r"LOAN_ID\s*\|\|\s*LOAN_SQNO|LOAN_SQNO\s*\|\|\s*LOAN_ID",
    re.IGNORECASE,
)


def _conversation_text(query: str, history: list) -> str:
    parts: list[str] = []
    for msg in history:
        role = getattr(msg, "role", None) or msg.get("role")
        if role != "user":
            continue
        content = getattr(msg, "content", None) or msg.get("content") or ""
        if str(content).strip():
            parts.append(str(content).strip())
    q = (query or "").strip()
    if q:
        parts.append(q)
    return " ".join(parts)


def _user_answered_clarification(query: str, history: list) -> bool:
    if "[clarification 답변]" in (query or ""):
        return True
    for msg in history:
        role = getattr(msg, "role", None) or msg.get("role")
        if role != "user":
            continue
        content = getattr(msg, "content", None) or msg.get("content") or ""
        if "[clarification 답변]" in content:
            return True
    return False


def _parse_year_month_before(convo: str) -> tuple[str, str] | None:
    text = (convo or "").replace(" ", "")
    for pat in _MONTH_BEFORE_PATTERNS:
        m = pat.search(text)
        if m:
            y = m.group(1)
            mo = m.group(2)
            if len(mo) == 1:
                mo = f"0{mo}"
            return y, mo
    return None


def _date_column_options(schema: TableSchema) -> list[str]:
    """기간 조건 후보 컬럼(영문명 + 한글). 적재·변경 일시는 제외."""
    opts: list[str] = []
    seen: set[str] = set()
    for col in schema.columns:
        name = (col.name or "").strip().upper()
        if not name or name in seen or name in _DATE_COL_SKIP:
            continue
        ko = (col.korean_name or "").strip()
        dtype = (col.data_type or "").upper()
        looks_date = (
            name.endswith("_DT")
            or name.endswith("_DATE")
            or "DATE" in dtype
            or "TIMESTAMP" in dtype
            or "일자" in ko
            or "일시" in ko
        )
        if not looks_date:
            continue
        seen.add(name)
        label = f"{name} ({ko})" if ko else name
        opts.append(label)
    return opts


def _boundary_options(convo: str) -> list[str]:
    parsed = _parse_year_month_before(convo)
    if parsed:
        y, mo = parsed
    else:
        y, mo = "2026", "09"
    ym = f"{y}-{mo}"
    month_int = int(mo)
    return [
        f"{ym}-01 미만 (해당 월 1일 전, 미포함)",
        f"{y}년 {month_int}월 1일 0시 이전 (TO_DATE '{ym}-01')",
        f"{y}년 {month_int}월 말까지 포함 여부를 직접 지정 (예: 8/31 이하)",
    ]


def _schema_has_columns(schema: TableSchema, *names: str) -> bool:
    have = {(c.name or "").strip().upper() for c in schema.columns}
    return all(n.upper() in have for n in names)


def _ask(
    gen: GenerationResult,
    *,
    summary: str,
    explanation: str,
    clarifications: list[ClarificationItem],
) -> GenerationResult:
    return GenerationResult(
        sql=None,
        explanation=explanation,
        used_tables=[],
        confidence="low",
        clarification_needed=summary,
        dialect=gen.dialect,
        input_tokens=gen.input_tokens,
        output_tokens=gen.output_tokens,
        clarifications=clarifications[:3],
    )


def _pick_date_schema(
    convo: str, table_schemas: list[TableSchema]
) -> tuple[TableSchema, list[str]] | None:
    scored: list[tuple[TableSchema, list[str]]] = []
    for schema in table_schemas:
        opts = _date_column_options(schema)
        if len(opts) >= 2:
            scored.append((schema, opts))
    if not scored:
        return None

    def prefer(*needles: str) -> tuple[TableSchema, list[str]] | None:
        for schema, opts in scored:
            tn = schema.table_name.upper()
            if any(n.upper() in tn for n in needles):
                return schema, opts
        return None

    if "연체" in convo:
        hit = prefer("FNDLY003", "FD0503")
        if hit:
            return hit
    if "특수채권" in convo:
        hit = prefer("FNBAD025", "FP0525")
        if hit:
            return hit
    return scored[0]


def detect_ambiguous_date(
    convo: str,
    table_schemas: list[TableSchema],
    gen: GenerationResult,
) -> GenerationResult | None:
    """기간만 있고 날짜 컬럼이 2개 이상이면 질문. SQL이 있어도 덮어씀."""
    if not _VAGUE_PERIOD.search(convo):
        return None
    picked = _pick_date_schema(convo, table_schemas)
    if picked is None:
        return None
    schema, date_opts = picked
    parsed = _parse_year_month_before(convo)
    summary = "기간 조건을 맞추려면 아래 항목을 선택해 주세요."
    if parsed:
        y, mo = parsed
        summary = (
            f"{y}년 {int(mo)}월 이전 조건을 맞추려면 아래 항목을 선택해 주세요."
        )
    ko = (schema.korean_name or "").strip()
    tlabel = f"{schema.table_name}" + (f" ({ko})" if ko else "")
    return _ask(
        gen,
        summary=summary,
        explanation=(
            "기간 조건은 날짜 컬럼과 경계(포함·제외)에 따라 SQL이 달라져 "
            "추가 확인이 필요합니다. 선택 후 SQL을 생성합니다."
        ),
        clarifications=[
            ClarificationItem(
                id="date_column",
                question=f"{tlabel}에서 기간 조건에 쓸 날짜 컬럼은 무엇인가요?",
                kind="single",
                options=date_opts[:5],
            ),
            ClarificationItem(
                id="date_boundary",
                question="질문에 있는 기간의 정확한 포함/제외 기준은?",
                kind="single",
                options=_boundary_options(convo),
            ),
        ],
    )


def detect_ambiguous_table(
    convo: str,
    table_schemas: list[TableSchema],
    gen: GenerationResult,
) -> GenerationResult | None:
    """키워드가 검색된 테이블 2개 이상에 매핑되면 객관식."""
    by_name = {s.table_name.upper(): s for s in table_schemas}
    for keywords, candidates in _KEYWORD_TABLES:
        if not any(k in convo for k in keywords):
            continue
        present: list[TableSchema] = []
        for cand in candidates:
            schema = by_name.get(cand.upper())
            if schema is not None:
                present.append(schema)
        if len(present) < 2:
            continue
        options: list[str] = []
        for schema in present[:5]:
            ko = (schema.korean_name or "").strip()
            options.append(
                f"{schema.table_name} ({ko})" if ko else schema.table_name
            )
        if len(options) < 2:
            continue
        return _ask(
            gen,
            summary="조회할 테이블을 선택해 주세요.",
            explanation=(
                "같은 업무 키워드에 해당하는 테이블이 여러 개라 "
                "어느 쪽을 쓸지 확인이 필요합니다."
            ),
            clarifications=[
                ClarificationItem(
                    id="table_choice",
                    question="어느 테이블을 사용할까요?",
                    kind="single",
                    options=options,
                )
            ],
        )
    return None


def _sql_loan_id_without_sqno(sql: str | None) -> bool:
    if not sql:
        return False
    if not re.search(r"\bLOAN_ID\b", sql, re.IGNORECASE):
        return False
    if re.search(r"\bLOAN_SQNO\b", sql, re.IGNORECASE):
        return False
    return True


def detect_loan_key(
    convo: str,
    table_schemas: list[TableSchema],
    gen: GenerationResult,
) -> GenerationResult | None:
    """LOAN_ID+LOAN_SQNO 세트가 불완전하면 질문."""
    has_pair = any(
        _schema_has_columns(s, "LOAN_ID", "LOAN_SQNO") for s in table_schemas
    )
    if not has_pair:
        return None

    incomplete_sql = _sql_loan_id_without_sqno(gen.sql)
    wants_one_loan = bool(_LOAN_INTENT.search(convo))
    has_concat = bool(_LOAN_CONCAT.search(convo) or _LOAN_CONCAT.search(gen.sql or ""))
    has_sqno_in_text = "LOAN_SQNO" in convo.upper() or "일련번호" in convo

    if incomplete_sql:
        pass
    elif wants_one_loan and not has_concat and not has_sqno_in_text:
        pass
    else:
        return None

    return _ask(
        gen,
        summary="대출 건은 LOAN_ID와 LOAN_SQNO를 함께 지정해야 합니다.",
        explanation=(
            "한 대출 건은 LOAN_ID와 LOAN_SQNO의 쌍입니다. "
            "연결값(LOAN_ID || LOAN_SQNO) 또는 일련번호를 알려 주시면 SQL에 반영합니다."
        ),
        clarifications=[
            ClarificationItem(
                id="loan_id_sqno",
                question=(
                    "조회할 대출 건의 LOAN_ID || LOAN_SQNO 값 "
                    "(또는 대출ID와 일련번호)을 입력해 주세요."
                ),
                kind="text",
                options=[],
            )
        ],
    )


def detect_dml_scope(
    convo: str,
    gen: GenerationResult,
    oracle_profile: str,
) -> GenerationResult | None:
    """관리자 DML에서 WHERE가 넓으면 범위 확인."""
    if oracle_profile != "admin_dml":
        return None
    sql = (gen.sql or "").lstrip()
    head = sql[:12].upper()
    if not (head.startswith("UPDATE") or head.startswith("DELETE")):
        return None
    if re.search(r"\bLOAN_ID\b", sql, re.IGNORECASE):
        return None
    if "WHERE" not in sql.upper():
        return None
    return _ask(
        gen,
        summary="수정·삭제 범위를 확인해 주세요.",
        explanation=(
            "WHERE가 날짜·상태 조건만 있으면 대상 건수가 커질 수 있습니다. "
            "전 건인지, 특정 대출 건인지 알려 주세요."
        ),
        clarifications=[
            ClarificationItem(
                id="dml_scope",
                question=(
                    "이 조건에 해당하는 모든 행을 바꿔도 될까요, "
                    "아니면 특정 대출 건(LOAN_ID || LOAN_SQNO)만 대상인가요?"
                ),
                kind="text",
                options=[],
            )
        ],
    )


def run_clarification_heuristics(
    *,
    query: str,
    history: list,
    table_schemas: list[TableSchema],
    gen: GenerationResult,
    dialect: Literal["oracle", "sas"],
    oracle_profile: str = "select_only",
) -> GenerationResult:
    """
    검색된 스키마로 detector를 순서대로 실행합니다.
    답변 턴([clarification 답변])은 스킵. LLM이 이미 질문만 냈으면 유지.
    """
    del dialect  # 풀·방언 공통
    if _user_answered_clarification(query, history):
        return gen
    if gen.sql is None and gen.clarifications:
        return gen

    convo = _conversation_text(query, history)
    for detect in (
        lambda: detect_ambiguous_date(convo, table_schemas, gen),
        lambda: detect_ambiguous_table(convo, table_schemas, gen),
        lambda: detect_loan_key(convo, table_schemas, gen),
        lambda: detect_dml_scope(convo, gen, oracle_profile),
    ):
        hit = detect()
        if hit is not None:
            return hit
    return gen


def apply_arrears_period_clarification(
    *,
    query: str,
    history: list,
    table_schemas: list[TableSchema],
    gen: GenerationResult,
    dialect: Literal["oracle", "sas"],
) -> GenerationResult:
    """하위 호환: 공통 파이프라인으로 위임."""
    return run_clarification_heuristics(
        query=query,
        history=history,
        table_schemas=table_schemas,
        gen=gen,
        dialect=dialect,
    )


def schemas_from_search_results(
    store: "SchemaVectorStore",
    results: list,
    *,
    schema_pool: str,
    table_names: list[str] | None = None,
) -> list[TableSchema]:
    """검색 결과·지정 테이블명에서 TableSchema 목록을 모읍니다."""
    names: list[str] = []
    if table_names:
        names.extend(table_names)
    for r in results:
        tn = getattr(r, "table_name", None) or ""
        if tn and tn not in names:
            names.append(tn)
    out: list[TableSchema] = []
    for name in names:
        ts = store.get_table(name, schema_pool=schema_pool)
        if ts is not None:
            out.append(ts)
    return out
