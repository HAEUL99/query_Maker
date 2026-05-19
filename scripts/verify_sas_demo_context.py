#!/usr/bin/env python3
"""SAS 예시 질의에 필요한 컬럼이 샘플 엑셀·get_table·보강 청크에 있는지 검증합니다."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    from backend.api.routes import _sas_customer_augment_table_names
    from backend.parser.excel_parser import parse_file
    from backend.vectorstore.chroma_store import (
        SchemaVectorStore,
        _schema_with_canonical_names,
    )

    sample = _ROOT / "data" / "excel" / "sample_customer"
    file_checks: list[tuple[str, str, str]] = [
        ("TBL_CUSTDIM.xlsx", "GENDER_CD", "성별·고객"),
        ("TBL_SALEFACT.xlsx", "PROD_ID", "상품·매출"),
        ("TBL_EMPDIM.xlsx", "JOB_GRADE", "직급·연봉"),
    ]
    for fn, needle, label in file_checks:
        p = sample / fn
        assert p.is_file(), f"[{label}] 샘플 없음: {p}"
        sch = _schema_with_canonical_names(parse_file(p)[0])
        blob = sch.to_chunk_text()
        assert needle in blob, f"[{label}] {fn} 청크에 {needle} 없음"

    sas_examples = [
        "올해 월별 총매출 추이",
        "상품별 판매건수와 평균단가",
        "성별 고객 수와 평균구매금액",
        "최근 3개월 상위 5개 상품",
        "직급별 평균 연봉",
    ]
    for q in sas_examples:
        aug = _sas_customer_augment_table_names(q)
        assert aug, f"보강 테이블 없음: {q!r}"

    store = SchemaVectorStore()
    for t in ("TBL_CUSTDIM", "TBL_SALEFACT", "TBL_EMPDIM"):
        ts = store.get_table(t, schema_pool="customer")
        if ts is None:
            print(
                f"(건너뜀) Chroma에 {t} 없음 — 로컬 인덱스 없이 샘플·보강 로직만 검증됨",
                file=sys.stderr,
            )
            continue
        txt = ts.to_chunk_text()
        if t == "TBL_CUSTDIM":
            assert "GENDER_CD" in txt, f"get_table({t}) 청크에 GENDER_CD 없음"
        if t == "TBL_SALEFACT":
            assert "PROD_ID" in txt, f"get_table({t}) 청크에 PROD_ID 없음"
        if t == "TBL_EMPDIM":
            assert "JOB_GRADE" in txt and "ANNUAL_SAL" in txt, (
                f"get_table({t}) 청크에 직급/연봉 없음"
            )

    q = "성별 고객 수와 평균구매금액"
    aug = _sas_customer_augment_table_names(q)
    merged = store.augment_search_replace_tables([], aug, schema_pool="customer")
    blob = "\n\n".join((r.chunk_text or "") for r in merged)
    assert "GENDER_CD" in blob, "보강 청크 전체에 GENDER_CD 없음"
    assert "SALE_AMT" in blob or "CUST_ID" in blob, "보강 청크에 매출/고객 조인 단서 없음"

    print("verify_sas_demo_context: ok")


if __name__ == "__main__":
    main()
