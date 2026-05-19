"""테이블 정의 엑셀(단일 시트)을 `TableSchema`로 변환하는 모듈입니다."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import openpyxl

from backend.models import ColumnSchema, TableSchema
from backend.schema_naming import (
    canonical_pool_table_name,
    canonicalize_fk_reference,
)

logger = logging.getLogger(__name__)

_TRUE_MARKERS = frozenset({"Y", "O", "1", "TRUE"})

# 멀티 테이블 모드: 1행 헤더가 아래와 일치·유사하면 «테이블명» 열로 간주합니다.
_TABLE_NAME_HEADER_KEYS = frozenset(
    {
        "테이블명",
        "table_name",
        "tbl_nm",
        "tablename",
        "오브젝트명",
        "object_name",
        "objectname",
        "객체명",
        "물리테이블명",
        "물리명",
        "논리테이블명",
        "논리명",
        "영문테이블명",
        "테이블명(영문)",
        "테이블id",
        "tableid",
    }
)

# 헤더 정규화: 소문자·공백 제거 후 키 매칭
_FIELD_ALIASES: dict[str, frozenset[str]] = {
    "name_en": frozenset(
        {
            "컬럼명(en)",
            "column_en",
            "name_en",
            "col_en",
            "영문컬럼명",
            "columnname(en)",
        }
    ),
    "name_ko": frozenset(
        {
            "컬럼명(ko)",
            "column_ko",
            "name_ko",
            "col_ko",
            "한글컬럼명",
        }
    ),
    "data_type": frozenset({"타입", "type", "datatype", "dtype", "데이터타입"}),
    "pk": frozenset({"pk", "primary", "primarykey", "기본키"}),
    "fk": frozenset({"fk참조", "fk", "fk_ref", "fkreference", "외래키"}),
    "nullable": frozenset({"null허용", "nullable", "null", "널허용"}),
    "description": frozenset({"설명", "description", "desc", "비고"}),
    "indexed": frozenset({"인덱스", "indexed", "idx", "index"}),
}


def _parse_bool(cell: Any) -> bool:
    """PK/FK 플래그·NULL 허용 등 엑셀 셀 값을 불리언으로 해석합니다."""
    if cell is None:
        return False
    s = str(cell).strip()
    if not s:
        return False
    return s.upper() in _TRUE_MARKERS


def _str_cell(cell: Any) -> str:
    """셀 값을 앞뒤 공백을 제거한 문자열로 반환합니다. None이면 빈 문자열입니다."""
    if cell is None:
        return ""
    return str(cell).strip()


def _header_key(h: Any) -> str:
    s = _str_cell(h)
    return "".join(s.lower().split())


def _norm_header_cell(c: Any) -> str:
    """헤더 셀의 줄바꿈·공백을 제거해 비교합니다."""
    return "".join(_str_cell(c).split())


def _row_values(row: tuple[Any, ...], length: int = 7) -> list[Any]:
    """행 튜플을 고정 길이 리스트로 맞춥니다(부족한 열은 None)."""
    vals = list(row)
    while len(vals) < length:
        vals.append(None)
    return vals[:length]


def _cell_looks_like_pool_table_name(cell: Any) -> bool:
    """고객·관리자 풀 규칙에 맞는 TBL_/TB_ 식별자인지(셀 값)."""
    raw = _str_cell(cell).upper()
    if not raw:
        return False
    c = canonical_pool_table_name(raw)
    if c.startswith("TBL_") and len(c) > 4:
        return bool(re.fullmatch(r"TBL_[A-Z0-9]+", c))
    if c.startswith("TB_") and len(c) > 3:
        return bool(re.fullmatch(r"TB_[A-Z0-9]+", c))
    return False


def _find_table_name_column(headers: list[str]) -> int | None:
    for i, h in enumerate(headers):
        if _header_key(h) in _TABLE_NAME_HEADER_KEYS:
            return i
    for i, h in enumerate(headers):
        raw = _str_cell(h).replace(" ", "").replace("\u3000", "")
        if "테이블명" in raw:
            return i
        if "오브젝트명" in raw or "객체명" in raw:
            return i
        if "물리테이블" in raw:
            return i
        if "물리" in raw and "테이블" in raw and "명" in raw:
            return i
    return None


def _infer_table_name_column_from_data(rows: list[tuple[Any, ...]]) -> int | None:
    """
    헤더에 테이블명 열이 없을 때, 데이터 행에서 TBL_/TB_ 패턴이 반복되는 열을 찾습니다.
    (파일명은 쓰지 않고 셀 내용만으로 멀티 테이블 모드 진입)
    """
    if len(rows) < 2:
        return None
    data_rows = [r for r in rows[1:] if r is not None]
    if not data_rows:
        return None
    max_w = 0
    for r in rows[: min(300, len(rows))]:
        if r:
            max_w = max(max_w, len(tuple(r)))
    if max_w < 1:
        return None

    best_j: int | None = None
    best_score = 0
    for j in range(min(max_w, 32)):
        hits = 0
        scanned = 0
        for r in data_rows[:500]:
            tup = tuple(r)
            if j >= len(tup):
                continue
            scanned += 1
            cell = tup[j]
            if _str_cell(cell) == "##META##":
                continue
            if _cell_looks_like_pool_table_name(cell):
                hits += 1
        if hits == 0:
            continue
        # 대부분 행이 같은 열에서 풀 테이블명이면 채택
        if hits > best_score:
            best_score = hits
            best_j = j

    if best_j is None or best_score < 1:
        return None
    non_meta = sum(
        1
        for r in data_rows[:500]
        if r is not None and _str_cell(_cell_at(tuple(r), best_j)) != "##META##"
    )
    if non_meta == 0:
        return None
    # 해당 열이 데이터의 상당 부분에서 풀 테이블명으로 보일 때만 채택(레거시 A열=영문컬럼명과 구분)
    need = max(1, int(non_meta * 0.4 + 0.999))
    if best_score < need:
        return None
    return best_j


def _resolve_field_columns(
    headers: list[str], table_idx: int
) -> dict[str, int]:
    """
    멀티 테이블 시트에서 컬럼 정의 필드별 열 인덱스를 구합니다.
    헤더 이름으로 찾지 못하면 «테이블명» 열 바로 오른쪽 8열을 레거시 순서로 사용합니다.
    """
    n = len(headers)
    keys = [_header_key(h) for h in headers]
    out: dict[str, int] = {}

    for field, aliases in _FIELD_ALIASES.items():
        pos: int | None = None
        for i, k in enumerate(keys):
            if k in aliases:
                pos = i
                break
        out[field] = pos  # type: ignore[assignment]

    missing = [f for f, p in out.items() if p is None]
    if not missing:
        return out  # type: ignore[return-value]

    # 순차 배치: 테이블명 다음 8열 = 레거시 A~H와 동일 순서
    if table_idx + 8 <= n:
        order = [
            "name_en",
            "name_ko",
            "data_type",
            "pk",
            "fk",
            "nullable",
            "description",
            "indexed",
        ]
        for j, field in enumerate(order):
            out[field] = table_idx + 1 + j
        return out

    raise ValueError(
        "멀티 테이블 형식: «테이블명» 열 다음에 컬럼 정의 8열이 없거나, "
        "헤더(컬럼명(EN), 타입, …)를 찾을 수 없습니다."
    )


def _cell_at(row: tuple[Any, ...], idx: int | None) -> Any:
    if idx is None or idx < 0:
        return None
    vals = list(row)
    return vals[idx] if idx < len(vals) else None


def _parse_column_from_row(
    row: tuple[Any, ...], col_idx: dict[str, int]
) -> ColumnSchema | None:
    name_en = _str_cell(_cell_at(row, col_idx["name_en"]))
    if not name_en:
        return None
    fk_ref_raw = _str_cell(_cell_at(row, col_idx["fk"]))
    is_fk = bool(fk_ref_raw)
    fk_reference = (
        canonicalize_fk_reference(fk_ref_raw) if is_fk else ""
    )
    return ColumnSchema(
        name=name_en,
        korean_name=_str_cell(_cell_at(row, col_idx["name_ko"])),
        data_type=_str_cell(_cell_at(row, col_idx["data_type"])),
        is_pk=_parse_bool(_cell_at(row, col_idx["pk"])),
        is_fk=is_fk,
        fk_reference=fk_reference,
        nullable=_parse_bool(_cell_at(row, col_idx["nullable"])),
        description=_str_cell(_cell_at(row, col_idx["description"])),
        is_indexed=_parse_bool(_cell_at(row, col_idx["indexed"])),
    )


def _parse_multi_table_sheet(
    rows: list[tuple[Any, ...]],
    path: Path,
    headers: list[str],
    table_idx: int,
) -> list[TableSchema]:
    """1행에 «테이블명» 열이 있는 형식. 한 파일에 여러 테이블 행 가능."""
    col_idx = _resolve_field_columns(headers, table_idx)
    meta_by_table: dict[str, tuple[str | None, str | None, str | None]] = {}
    columns_by_table: dict[str, list[ColumnSchema]] = defaultdict(list)

    for row in rows[1:]:
        if row is None:
            continue
        tbl_cell = _str_cell(_cell_at(row, table_idx))
        if not tbl_cell:
            continue

        if tbl_cell == "##META##":
            # ##META## | 대상테이블명 | 한글테이블명 | 도메인 | 설명 (테이블명 열 기준 오른쪽)
            target = _str_cell(_cell_at(row, table_idx + 1))
            if not target:
                continue
            tkey = canonical_pool_table_name(target.upper())
            ko = _str_cell(_cell_at(row, table_idx + 2)) or None
            dom = _str_cell(_cell_at(row, table_idx + 3)) or None
            desc = _str_cell(_cell_at(row, table_idx + 4)) or None
            meta_by_table[tkey] = (ko, dom, desc)
            continue

        tkey = canonical_pool_table_name(tbl_cell.upper())
        col = _parse_column_from_row(row, col_idx)
        if col:
            columns_by_table[tkey].append(col)

    if not columns_by_table:
        raise ValueError(
            "멀티 테이블 형식: 데이터 행이 없거나 «테이블명» 열이 비어 있습니다."
        )

    src = str(path.resolve())
    out: list[TableSchema] = []
    for tkey in sorted(columns_by_table.keys()):
        cols = columns_by_table[tkey]
        if not cols:
            continue
        ko, dom, desc = meta_by_table.get(
            tkey,
            (None, None, None),
        )
        out.append(
            TableSchema(
                table_name=tkey,
                korean_name=ko if ko else tkey,
                domain=dom if dom else "기타",
                description=desc if desc is not None else "",
                source_file=src,
                columns=cols,
            )
        )

    if not out:
        raise ValueError("멀티 테이블 형식: 유효한 테이블이 없습니다.")
    return out


def _parse_legacy_sheet(rows: list[tuple[Any, ...]], path: Path) -> list[TableSchema]:
    """파일명으로 테이블명을 정하고, «테이블명» 열이 헤더에 없을 때 사용합니다."""
    path = Path(path)
    table_name = canonical_pool_table_name(path.stem.upper())

    meta_korean: str | None = None
    meta_domain: str | None = None
    meta_description: str | None = None
    meta_found = False
    columns: list[ColumnSchema] = []

    for row in rows[1:]:
        a, b, c, d, e, f, g, h = _row_values(
            tuple(row) if row is not None else tuple(),
            8,
        )

        col_a = _str_cell(a)
        if col_a == "##META##":
            meta_found = True
            meta_korean = _str_cell(b) or None
            meta_domain = _str_cell(c) or None
            meta_description = _str_cell(d) or None
            continue

        if not col_a:
            continue

        name_en = col_a
        korean_name = _str_cell(b)
        data_type = _str_cell(c)
        is_pk = _parse_bool(d)
        fk_ref_raw = _str_cell(e)
        is_fk = bool(fk_ref_raw)
        fk_reference = (
            canonicalize_fk_reference(fk_ref_raw)
            if is_fk
            else ""
        )
        nullable = _parse_bool(f)
        description = _str_cell(g)
        is_indexed = _parse_bool(h)

        columns.append(
            ColumnSchema(
                name=name_en,
                korean_name=korean_name,
                data_type=data_type,
                is_pk=is_pk,
                is_fk=is_fk,
                fk_reference=fk_reference,
                nullable=nullable,
                description=description,
                is_indexed=is_indexed,
            )
        )

    if meta_found:
        korean_tbl = meta_korean if meta_korean else table_name
        domain_tbl = meta_domain if meta_domain else "기타"
        desc_tbl = meta_description if meta_description is not None else ""
    else:
        korean_tbl = table_name
        domain_tbl = "기타"
        desc_tbl = ""

    return [
        TableSchema(
            table_name=table_name,
            korean_name=korean_tbl,
            domain=domain_tbl,
            description=desc_tbl,
            source_file=str(path.resolve()),
            columns=columns,
        )
    ]


def _sheet_has_dw_wide_header(ws: Any) -> bool:
    """DW 스타일: 한 행에 «테이블명»·«컬럼명» 헤더가 함께 있는지."""
    for row in ws.iter_rows(min_row=1, max_row=50, values_only=True):
        if not row:
            continue
        joined = "".join(_str_cell(c) for c in row)
        if "테이블명" in joined and "컬럼명" in joined:
            return True
    return False


def _select_schema_sheet(wb: openpyxl.Workbook) -> str:
    """
    표지·이력 시트가 앞에 오는 정의서는 «테이블정의서» 등 데이터 시트를 고릅니다.
    """
    names = wb.sheetnames
    if "테이블정의서" in names and _sheet_has_dw_wide_header(wb["테이블정의서"]):
        return "테이블정의서"
    for name in names:
        if _sheet_has_dw_wide_header(wb[name]):
            return name
    return names[0]


def _dw_compose_type(row: tuple[Any, ...], col_map: dict[str, int]) -> str:
    """DW 정의서의 타입·길이·소수점 열을 하나의 data_type 문자열로 합니다."""
    dt = _str_cell(_cell_at(row, col_map.get("dtype"))).upper()
    ln = _str_cell(_cell_at(row, col_map.get("length"))) if "length" in col_map else ""
    sc = _str_cell(_cell_at(row, col_map.get("scale"))) if "scale" in col_map else ""
    if not dt:
        return ""
    if dt in ("DATE", "TIMESTAMP", "TIMESTAMP(6)", "CLOB", "BLOB", "LONG"):
        return dt
    if dt == "NUMBER":
        if ln and sc:
            return f"NUMBER({ln},{sc})"
        if ln:
            return f"NUMBER({ln})"
        return "NUMBER"
    if ln and dt in ("VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR", "NVARCHAR"):
        return f"{dt}({ln})"
    if ln:
        return f"{dt}({ln})"
    return dt


def _parse_dw_wide_format(
    rows: list[tuple[Any, ...]], path: Path
) -> list[TableSchema] | None:
    """
    한화·DW류 정의서: No / 주제영역 / 테이블명·테이블한글명 / 컬럼명·컬럼한글명 / PK·NULL / 타입·길이…
    같은 행에 테이블명과 컬럼 정의가 반복됩니다.
    """
    header_idx: int | None = None
    col_map: dict[str, int] = {}

    for ri, row in enumerate(rows[:80]):
        if not row:
            continue
        joined = "".join(_str_cell(c) for c in row)
        if "테이블명" not in joined or "컬럼명" not in joined:
            continue
        # 멀티 테이블(컬럼명(EN)/(KO)만 있고 «컬럼명» 단독 열이 없는) 형식은 제외
        if not any(_norm_header_cell(c) == "컬럼명" for c in row if c is not None):
            continue
        col_map.clear()
        for i, c in enumerate(row):
            key = _norm_header_cell(c)
            if key == "테이블명":
                col_map["table"] = i
            elif key == "테이블한글명":
                col_map["table_ko"] = i
            elif key == "컬럼명":
                col_map["name_en"] = i
            elif key.startswith("컬럼명("):
                if "KO" in key.upper() or "한글" in key:
                    col_map["name_ko"] = i
                else:
                    col_map["name_en"] = i
            elif key == "컬럼한글명":
                col_map["name_ko"] = i
            elif key.startswith("PK") and "여부" in key:
                col_map["pk"] = i
            elif "NULL" in key.upper() and "여부" in key:
                col_map["nullable"] = i
            elif key == "타입":
                col_map["dtype"] = i
            elif key == "길이":
                col_map["length"] = i
            elif key == "소수점":
                col_map["scale"] = i
            elif key == "1차주제영역":
                col_map["d1"] = i
            elif key == "2차주제영역":
                col_map["d2"] = i
        if "table" in col_map and "name_en" in col_map and "dtype" in col_map:
            header_idx = ri
            break

    if header_idx is None:
        return None

    columns_by_table: dict[str, list[ColumnSchema]] = defaultdict(list)
    table_ko: dict[str, str] = {}
    table_domain: dict[str, str] = {}

    for row in rows[header_idx + 1 :]:
        if not row:
            continue
        raw_tbl = _str_cell(_cell_at(row, col_map["table"]))
        if not raw_tbl or raw_tbl.startswith("#"):
            continue
        tkey = canonical_pool_table_name(raw_tbl.upper())
        name_en = _str_cell(_cell_at(row, col_map["name_en"]))
        if not name_en:
            continue

        if tkey not in table_ko and "table_ko" in col_map:
            table_ko[tkey] = _str_cell(_cell_at(row, col_map["table_ko"])) or tkey
        if tkey not in table_domain and "d1" in col_map:
            d1 = _str_cell(_cell_at(row, col_map["d1"]))
            d2 = (
                _str_cell(_cell_at(row, col_map["d2"]))
                if "d2" in col_map
                else ""
            )
            table_domain[tkey] = (
                f"{d1} / {d2}".strip().strip("/").strip()
                if d2
                else (d1 or "기타")
            )

        dt_str = _dw_compose_type(row, col_map)
        pk_cell = _cell_at(row, col_map.get("pk"))
        null_cell = _cell_at(row, col_map.get("nullable"))
        is_pk = _parse_bool(pk_cell) if pk_cell is not None else False
        nullable = (
            _parse_bool(null_cell) if null_cell is not None else True
        )

        columns_by_table[tkey].append(
            ColumnSchema(
                name=name_en,
                korean_name=_str_cell(_cell_at(row, col_map.get("name_ko"))),
                data_type=dt_str,
                is_pk=is_pk,
                is_fk=False,
                fk_reference="",
                nullable=nullable,
                description="",
                is_indexed=False,
            )
        )

    if not columns_by_table:
        return None

    src = str(path.resolve())
    out: list[TableSchema] = []
    for tkey in sorted(columns_by_table.keys()):
        cols = columns_by_table[tkey]
        if not cols:
            continue
        out.append(
            TableSchema(
                table_name=tkey,
                korean_name=table_ko.get(tkey) or tkey,
                domain=table_domain.get(tkey) or "기타",
                description="",
                source_file=src,
                columns=cols,
            )
        )
    return out if out else None


def parse_file(file_path: str | Path) -> list[TableSchema]:
    """
    단일 엑셀 파일을 읽어 `TableSchema` 목록으로 변환합니다.

    **레거시 형식** (테이블명 열을 찾지 못한 경우)
    - 파일명(확장자 제외)으로 `table_name` 결정.
    - 2행부터: A열 `##META##` 선택, 그 외 컬럼 정의(A~G 필수, H 인덱스 선택).

    **멀티 테이블 형식** (테이블명 열이 있거나, 데이터에서 TBL_/TB_ 열이 추론됨)
    - 1행: `테이블명`·`오브젝트명`·`물리테이블명` 등 헤더, 또는 헤더 없이 데이터만으로도
      TBL_/TB_ 패턴이 반복되는 열을 자동 추론.
    - 각 데이터 행의 «테이블명» 열 값으로 테이블을 구분 (한 파일에 복수 테이블 가능).
    - `##META##` 행: 해당 열에 `##META##`, 오른쪽 열에 대상 테이블명·한글명·도메인·설명.
    - 컬럼 정의는 헤더 이름으로 열을 찾거나, «테이블명» 바로 오른쪽 8열을 레거시와 동일 순서로 해석합니다.

    **DW·한화형 넓은 정의서** (시트 «테이블정의서» 등, 표지가 앞에 있는 파일)
    - 첫 시트가 아닌 `테이블정의서` 시트를 자동 선택합니다.
    - 헤더 행에 `테이블명`·정확히 `컬럼명`·`컬럼한글명`·`타입`·`PK여부`·`NULL여부`·길이 등이 있는 형식을 지원합니다.
    """
    path = Path(file_path)
    if not path.is_file():
        raise ValueError(f"엑셀 파일을 찾을 수 없습니다: {path}")

    wb: openpyxl.Workbook | None = None

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(
            f"엑셀 파일을 열 수 없습니다(형식 오류 등): {path.name}"
        ) from exc

    try:
        if not wb.sheetnames:
            raise ValueError(f"시트가 없는 엑셀 파일입니다: {path.name}")

        sheet_name = _select_schema_sheet(wb)
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(min_row=1, values_only=True))
        if not rows:
            raise ValueError(f"빈 시트입니다: {path.name}")

        dw_schemas = _parse_dw_wide_format(rows, path)
        if dw_schemas is not None:
            return dw_schemas

        headers = [_str_cell(c) for c in rows[0]]
        table_col = _find_table_name_column(headers)
        if table_col is None:
            table_col = _infer_table_name_column_from_data(rows)

        if table_col is not None:
            return _parse_multi_table_sheet(rows, path, headers, table_col)
        return _parse_legacy_sheet(rows, path)
    finally:
        wb.close()


def parse_directory(
    dir_path: str | Path, pattern: str = "*.xlsx"
) -> list[TableSchema]:
    """
    디렉터리에서 패턴에 맞는 엑셀 파일을 찾아 각각 `TableSchema`로 파싱합니다.

    개별 파일 파싱에 실패한 경우 경고만 남기고 나머지 파일 처리를 계속합니다.
    """
    base = Path(dir_path)
    if not base.is_dir():
        logger.warning("디렉터리가 없거나 폴더가 아닙니다: %s", base)
        return []

    results: list[TableSchema] = []
    for excel_path in sorted(base.glob(pattern)):
        if not excel_path.is_file():
            continue
        try:
            results.extend(parse_file(excel_path))
        except ValueError as exc:
            logger.warning(
                "엑셀 파싱 실패(건너뜀): %s — %s",
                excel_path.name,
                exc,
            )
        except Exception:
            logger.warning(
                "엑셀 파싱 중 예기치 않은 오류(건너뜀): %s",
                excel_path.name,
                exc_info=True,
            )

    return results


def validate_references(schemas: list[TableSchema]) -> list[str]:
    """
    컬럼의 FK 참조 문자열(`테이블명.컬럼명`)이 알려진 테이블 목록과 맞는지 검사합니다.

    참조 테이블명이 `schemas`에 없으면 경고 문구를 모아 반환합니다.
    """
    table_names = {s.table_name for s in schemas}
    warnings: list[str] = []

    for schema in schemas:
        for col in schema.columns:
            ref = (col.fk_reference or "").strip()
            if not ref:
                continue

            if "." not in ref:
                warnings.append(
                    f"[{schema.table_name}.{col.name}] FK 참조 형식이 "
                    f"'테이블명.컬럼명'이 아닙니다: {ref!r}"
                )
                continue

            ref_table, _, rest = ref.partition(".")
            ref_table = canonical_pool_table_name(ref_table.strip().upper())
            if not ref_table:
                warnings.append(
                    f"[{schema.table_name}.{col.name}] FK 참조에 테이블명이 없습니다: {ref!r}"
                )
                continue
            if not rest.strip():
                warnings.append(
                    f"[{schema.table_name}.{col.name}] FK 참조에 컬럼명이 없습니다: {ref!r}"
                )
                continue

            if ref_table not in table_names:
                warnings.append(
                    f"[{schema.table_name}.{col.name}] FK가 참조하는 테이블 "
                    f"'{ref_table}'이(가) 스키마 목록에 없습니다."
                )

    return warnings
