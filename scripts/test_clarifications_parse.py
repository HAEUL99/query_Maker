"""clarifications JSON 정규화·휴리스틱 단위 테스트 (API 호출 없음)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.generator.sql_generator import SQLGenerator
from backend.models import ColumnSchema, GenerationResult, TableSchema


def _col(name: str, korean: str, dtype: str = "DATE") -> ColumnSchema:
    return ColumnSchema(
        name=name,
        korean_name=korean,
        data_type=dtype,
        is_pk=False,
        is_fk=False,
        fk_reference="",
        nullable=True,
        description="",
    )


def _gen(**kwargs) -> GenerationResult:
    base = dict(
        sql="SELECT 1 FROM DUAL",
        explanation="추측 SQL",
        used_tables=[],
        confidence="medium",
        clarification_needed=None,
        dialect="oracle",
        input_tokens=1,
        output_tokens=1,
        clarifications=[],
    )
    base.update(kwargs)
    return GenerationResult(**base)


def test_normalize_clarifications_single() -> None:
    raw = [
        {
            "id": "date_column",
            "question": "기준 컬럼?",
            "kind": "single",
            "options": ["A", "B"],
        }
    ]
    items = SQLGenerator._normalize_clarifications(raw)
    assert len(items) == 1
    assert items[0].kind == "single"
    assert items[0].options == ["A", "B"]


def test_normalize_clarifications_single_becomes_text_if_one_option() -> None:
    raw = [
        {
            "id": "x",
            "question": "?",
            "kind": "single",
            "options": ["only"],
        }
    ]
    items = SQLGenerator._normalize_clarifications(raw)
    assert items[0].kind == "text"
    assert items[0].options == []


def test_history_awaiting_clarification() -> None:
    from backend.generator.sql_generator import (
        _history_awaiting_clarification_answer,
        _history_last_assistant_had_sql,
    )

    hist = [
        {"role": "user", "content": "연체 조회"},
        {
            "role": "assistant",
            "content": "[추가 질문]\n- (date_column) 기준?\n[아직 SQL 없음 — 사용자 답변 대기]",
        },
    ]
    assert _history_awaiting_clarification_answer(hist)
    assert not _history_last_assistant_had_sql(hist)

    hist2 = hist + [
        {"role": "user", "content": "[clarification 답변]\ndate_column: A"},
        {"role": "assistant", "content": "SQL:\nSELECT 1 FROM DUAL"},
    ]
    assert _history_last_assistant_had_sql(hist2)


def test_date_heuristic_oracle_fndly() -> None:
    from backend.generator.clarification_heuristics import (
        run_clarification_heuristics,
    )
    from backend.vectorstore.chroma_store import SchemaVectorStore

    store = SchemaVectorStore()
    ts = store.get_table("TB_FNDLY003", schema_pool="admin")
    assert ts is not None

    out = run_clarification_heuristics(
        query="2026.9월 이전 연체 건 조회",
        history=[],
        table_schemas=[ts],
        gen=_gen(sql="SELECT 1 FROM TB_FNDLY003", used_tables=["TB_FNDLY003"]),
        dialect="oracle",
    )
    assert out.sql is None
    assert len(out.clarifications) >= 2
    assert out.clarifications[0].id == "date_column"
    assert not any("LAST_CHNG_DTTM" in (o or "") for c in out.clarifications for o in c.options)


def test_date_heuristic_sas_fd0503() -> None:
    from backend.generator.clarification_heuristics import (
        run_clarification_heuristics,
    )
    from backend.vectorstore.chroma_store import SchemaVectorStore

    store = SchemaVectorStore()
    ts = store.get_table("TBL_WFGWFD0503", schema_pool="customer")
    if ts is None:
        ts = TableSchema(
            table_name="TBL_WFGWFD0503",
            korean_name="연체관리대장",
            domain="FN",
            description="",
            source_file="",
            columns=[
                _col("ARRE_RGST_DATE", "연체등록일자"),
                _col("ARRE_ARGM_DATE", "연체정리일자"),
                _col("NOTC_DATE", "통지일자"),
                _col("LAST_CHNG_DTTM", "최종변경일시"),
            ],
        )

    out = run_clarification_heuristics(
        query="연체등록일이 2018년 6월 이전인 건",
        history=[],
        table_schemas=[ts],
        gen=_gen(sql="PROC SQL; SELECT * FROM TBL_WFGWFD0503; QUIT;", dialect="sas"),
        dialect="sas",
    )
    assert out.sql is None
    assert out.clarifications[0].id == "date_column"
    assert not any("LAST_CHNG_DTTM" in (o or "") for c in out.clarifications for o in c.options)


def test_skip_on_clarification_answer_turn() -> None:
    from backend.generator.clarification_heuristics import (
        run_clarification_heuristics,
    )

    ts = TableSchema(
        table_name="TB_FNDLY003",
        korean_name="연체",
        domain="FN",
        description="",
        source_file="",
        columns=[_col("ARRE_RGST_DT", "연체등록일자"), _col("NOTC_DATE", "통지일자")],
    )
    gen = _gen(sql="SELECT 1 FROM TB_FNDLY003")
    out = run_clarification_heuristics(
        query="[clarification 답변]\ndate_column: ARRE_RGST_DT",
        history=[],
        table_schemas=[ts],
        gen=gen,
        dialect="oracle",
    )
    assert out.sql == gen.sql


def test_table_choice_special_bond() -> None:
    from backend.generator.clarification_heuristics import (
        run_clarification_heuristics,
    )

    a = TableSchema(
        table_name="TB_FNBAD025",
        korean_name="특수채권기본사항",
        domain="FN",
        description="",
        source_file="",
        columns=[_col("LOAN_ID", "대출ID", "VARCHAR2")],
    )
    b = TableSchema(
        table_name="TBL_WFGWFP0525",
        korean_name="특수채권기본사항",
        domain="FN",
        description="",
        source_file="",
        columns=[_col("LOAN_ID", "대출ID", "VARCHAR2")],
    )
    # 기간 표현 없이 특수채권만 → table_choice (날짜 detector 미해당)
    out = run_clarification_heuristics(
        query="특수채권 목록 뽑아줘",
        history=[],
        table_schemas=[a, b],
        gen=_gen(),
        dialect="oracle",
    )
    assert out.sql is None
    assert out.clarifications[0].id == "table_choice"
    assert len(out.clarifications[0].options) == 2


def test_loan_key_id_only() -> None:
    from backend.generator.clarification_heuristics import (
        run_clarification_heuristics,
    )

    ts = TableSchema(
        table_name="TBL_WFGWFL0514",
        korean_name="대출기본",
        domain="FN",
        description="",
        source_file="",
        columns=[
            _col("LOAN_ID", "대출ID", "VARCHAR2"),
            _col("LOAN_SQNO", "대출일련번호", "VARCHAR2"),
        ],
    )
    out = run_clarification_heuristics(
        query="대출번호 LOAN_ID가 ABC인 건 조회",
        history=[],
        table_schemas=[ts],
        gen=_gen(sql="SELECT * FROM TBL_WFGWFL0514 WHERE LOAN_ID = 'ABC'"),
        dialect="sas",
    )
    assert out.sql is None
    assert out.clarifications[0].id == "loan_id_sqno"


def test_dml_scope_broad_update() -> None:
    from backend.generator.clarification_heuristics import (
        run_clarification_heuristics,
    )

    ts = TableSchema(
        table_name="TB_FNBAD025",
        korean_name="특수채권",
        domain="FN",
        description="",
        source_file="",
        columns=[_col("SPBD_FRST_RGDT", "특수채권최초등록일자")],
    )
    out = run_clarification_heuristics(
        query="특수채권등록일자가 오늘인 데이터의 등록일자를 내일로 변경",
        history=[],
        table_schemas=[ts],
        gen=_gen(
            sql=(
                "UPDATE TB_FNBAD025 SET SPBD_FRST_RGDT = TO_CHAR(SYSDATE+1,'YYYYMMDD') "
                "WHERE SPBD_FRST_RGDT = TO_CHAR(SYSDATE,'YYYYMMDD')"
            )
        ),
        dialect="oracle",
        oracle_profile="admin_dml",
    )
    assert out.sql is None
    assert out.clarifications[0].id == "dml_scope"


def main() -> None:
    test_normalize_clarifications_single()
    test_normalize_clarifications_single_becomes_text_if_one_option()
    test_history_awaiting_clarification()
    test_date_heuristic_oracle_fndly()
    test_date_heuristic_sas_fd0503()
    test_skip_on_clarification_answer_turn()
    test_table_choice_special_bond()
    test_loan_key_id_only()
    test_dml_scope_broad_update()
    print("✓ clarifications parse tests passed")


if __name__ == "__main__":
    main()
