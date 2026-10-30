"""샘플 엑셀 → 인덱싱 → 검색 → SQL 생성까지 한 번에 검증합니다.

사용법 (반드시 query-maker 디렉터리에서):

  cd /path/to/query-maker
  PYTHONPATH=. python scripts/verify_e2e.py

전제:
  - `.env`에 유효한 GOOGLE_API_KEY
  - 임베딩/LLM 모델명이 해당 키에서 사용 가능한 값 (예: 임베딩 models/gemini-embedding-001)
  - `data/excel/sample_customer/`에 샘플 xlsx (없으면 `python scripts/create_sample_data.py` 로 생성)
"""

from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트 = query-maker (scripts/의 부모)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    from backend.generator.sql_generator import SQLGenerator
    from backend.parser.excel_parser import parse_directory
    from backend.vectorstore.chroma_store import SchemaVectorStore

    sample_dir = _ROOT / "data" / "excel" / "sample_customer"
    if not sample_dir.is_dir():
        print(f"[실패] 샘플 폴더 없음: {sample_dir}")
        print("  meta/scripts/create_sample_data.py 를 실행해 샘플 xlsx를 만든 뒤 다시 시도하세요.")
        sys.exit(1)

    print("1) 엑셀 파싱 …")
    schemas = parse_directory(sample_dir)
    if not schemas:
        print(f"[실패] 파싱된 스키마가 없습니다. {sample_dir} 에 .xlsx가 있는지 확인하세요.")
        sys.exit(1)
    print(f"   → 테이블 {len(schemas)}개")

    print("2) Chroma 인덱싱(reset=True) …")
    store = SchemaVectorStore()
    idx = store.index_schemas(schemas, reset=True, schema_pool="customer")
    print(f"   → {idx}")
    if idx.get("indexed", 0) == 0:
        print("[실패] 인덱싱된 문서가 없습니다. .env 의 EMBEDDING_MODEL·API 키·네트워크를 확인하세요.")
        sys.exit(1)

    print("3) 벡터 검색 …")
    q = "지난달 매출 상위 10명 고객"
    results = store.search(q, schema_pool="customer")
    print(f"   → 후보 {len(results)}개 (상위 3개 테이블명)")
    for r in results[:3]:
        print(f"      - {r.table_name}  score={r.score:.3f}")

    print("4) SQL 생성 (Oracle) …")
    generator = SQLGenerator()
    result = generator.generate(
        "지난달 매출 상위 10명 고객명과 금액",
        "oracle",
        results,
        oracle_profile="select_only",
    )
    print("=== Oracle ===")
    print(f"confidence: {result.confidence}")
    print(f"used_tables: {result.used_tables}")
    print(f"clarification_needed: {result.clarification_needed!r}")
    print(f"clarifications: {len(result.clarifications)} items")
    for c in result.clarifications:
        print(f"  - [{c.id}] {c.question!r} kind={c.kind} options={c.options}")
    print(f"input_tokens: {result.input_tokens}  output_tokens: {result.output_tokens}")
    print(f"SQL:\n{result.sql}")
    print(f"설명: {result.explanation}")

    if result.sql is None and result.explanation.startswith("오류:"):
        print("\n[참고] API 오류(쿼터 429, 키 오류 등)면 설명에 상세가 있습니다.")
        print("  https://ai.google.dev/gemini-api/docs/rate-limits")
        sys.exit(2)

    print("\n✓ 파이프라인 검증 완료 (인덱싱·검색·생성 호출까지 성공)")
    sys.exit(0)


if __name__ == "__main__":
    main()
