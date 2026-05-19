"""엑셀 스키마를 파싱해 Chroma 벡터 인덱스에 넣는 CLI입니다."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.WARNING)


def _short_fk_warning(msg: str) -> str:
    """validate_references 한 줄 메시지를 짧은 한 줄로 바꿉니다."""
    m = re.match(
        r"\[([A-Z0-9_]+)\.([A-Z0-9_]+)\] FK가 참조하는 테이블 "
        r"'([A-Z0-9_]+)'이\(가\) 스키마 목록에 없습니다\.",
        msg,
    )
    if m:
        return f"{m.group(1)}.{m.group(2)} → {m.group(3)} (참조 테이블 없음)"
    return msg


def _collect_xlsx_paths_from_dir(dir_path: Path) -> list[Path]:
    if not dir_path.is_dir():
        print(f"[오류] 디렉터리가 없습니다: {dir_path}", file=sys.stderr)
        sys.exit(1)
    paths = sorted(p for p in dir_path.glob("*.xlsx") if p.is_file())
    if not paths:
        print(f"[오류] .xlsx 파일이 없습니다: {dir_path}", file=sys.stderr)
        sys.exit(1)
    return paths


def _parse_files_with_progress(paths: list[Path]):
    """파일별로 파싱하고 진행 로그를 남깁니다. (스키마 목록, 실패 메시지 목록)"""
    from backend.models import TableSchema
    from backend.parser.excel_parser import parse_file

    schemas: list[TableSchema] = []
    failures: list[str] = []
    total = len(paths)

    for i, path in enumerate(paths, start=1):
        print(f"[{i}/{total}] 파싱 중... {path.name}")
        try:
            batch = parse_file(path)
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
            print(f"✗ 파싱 실패: {path.name} — {exc}")
            continue
        n_tables = len(batch)
        n_cols = sum(len(s.columns) for s in batch)
        print(f"✓ 파싱 완료: {n_tables}개 테이블, {n_cols}개 컬럼(합계)")
        schemas.extend(batch)

    return schemas, failures


def _domain_summary_line(by_domain: dict[str, int]) -> str:
    parts: list[str] = []
    for name in sorted(by_domain.keys()):
        if name == "":
            continue
        parts.append(f"{name} {by_domain[name]}개")
    if "" in by_domain:
        parts.append(f"(도메인 없음) {by_domain['']}개")
    return ", ".join(parts) if parts else "(없음)"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="엑셀 스키마 디렉터리 또는 파일 목록을 벡터 DB에 인덱싱합니다.",
    )
    mx = parser.add_mutually_exclusive_group(required=True)
    mx.add_argument(
        "--list",
        action="store_true",
        help="인덱싱된 테이블 목록만 출력하고 종료합니다.",
    )
    mx.add_argument("--dir", type=str, metavar="PATH", help="엑셀(.xlsx)이 있는 디렉터리")
    mx.add_argument(
        "--files",
        nargs="+",
        metavar="XLSX",
        help="인덱싱할 .xlsx 파일 경로(여러 개)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="인덱스를 비운 뒤 다시 넣습니다(기존 컬렉션 초기화).",
    )
    parser.add_argument(
        "--pool",
        choices=("customer", "admin"),
        default="customer",
        help="스키마 풀: customer=고객(SAS 등), admin=관리자 Oracle 메타",
    )
    args = parser.parse_args()

    from backend.parser.excel_parser import validate_references
    from backend.vectorstore.chroma_store import SchemaVectorStore

    store = SchemaVectorStore()

    pool = args.pool

    if args.list:
        tables = store.list_tables(schema_pool=pool)
        if not tables:
            print("(인덱싱된 테이블이 없습니다.)")
            return
        for t in tables:
            tn = t.get("table_name", "")
            print(f"- {tn}  (domain={t.get('domain', '')!r})")
        print(f"총 {len(tables)}개")
        return

    if args.dir:
        base = Path(args.dir)
        if not base.is_absolute():
            base = (_ROOT / base).resolve()
        paths = _collect_xlsx_paths_from_dir(base)
    else:
        paths = []
        for f in args.files:
            p = Path(f)
            if not p.is_absolute():
                p = (_ROOT / p).resolve()
            if not p.is_file():
                print(f"[오류] 파일을 찾을 수 없습니다: {p}", file=sys.stderr)
                sys.exit(1)
            if not p.suffix.lower() == ".xlsx":
                print(f"[오류] .xlsx만 지원합니다: {p}", file=sys.stderr)
                sys.exit(1)
            paths.append(p)
        paths.sort(key=lambda x: x.name)

    schemas, parse_failures = _parse_files_with_progress(paths)
    if parse_failures and not schemas:
        for line in parse_failures:
            print(f"[오류] {line}", file=sys.stderr)
        sys.exit(1)

    from backend.config import get_settings
    from backend.schema_naming import pool_table_name_violation

    settings_nm = get_settings()
    for s in schemas:
        bad = pool_table_name_violation(s.table_name, pool, settings_nm)
        if bad:
            print(
                f"[오류] {Path(s.source_file).name}: {bad}",
                file=sys.stderr,
            )
            sys.exit(1)

    warnings = validate_references(schemas)
    for w in warnings:
        short = _short_fk_warning(w)
        print(f"⚠ FK 경고: {short}")

    if not schemas:
        print("[오류] 인덱싱할 스키마가 없습니다.", file=sys.stderr)
        sys.exit(1)

    n = len(schemas)
    if args.reset:
        store.reset(schema_pool=pool)

    print(f"임베딩 생성 중... (풀={pool}, 테이블 {n}개)")
    idx = store.index_schemas(schemas, reset=False, schema_pool=pool)
    if idx.get("errors"):
        for err in idx["errors"]:
            print(f"[오류] {err}", file=sys.stderr)
        sys.exit(1)

    print("✓ 인덱싱 완료")
    print("─────────────────")

    stats = store.get_stats(schema_pool=pool)
    total = int(stats.get("total", 0))
    by_domain = dict(stats.get("by_domain") or {})
    embed_model = str(stats.get("model", ""))

    print(f"총 테이블: {total}개")
    print(f"도메인별: {_domain_summary_line(by_domain)}")
    print(f"임베딩 모델: {embed_model}")
    print("─────────────────")

    if parse_failures:
        print("경고: 일부 파일 파싱에 실패했습니다(위 ✗ 로그 참고).", file=sys.stderr)


if __name__ == "__main__":
    main()
