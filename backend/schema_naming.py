"""고객(TBL_*)·관리자(TB_*) 스키마 풀별 테이블 명명 규칙 검증."""

from __future__ import annotations

import re
from typing import Literal

from backend.config import Settings

SchemaPool = Literal["customer", "admin"]


def canonical_pool_table_name(table_name: str) -> str:
    """
    TBL_/TB_ 접두 뒤의 밑줄 등을 제거해 한 덩어리 식별자로 만듭니다.

    예: TBL_BUDGET_FACT → TBL_BUDGETFACT, TB_BUDGET_FACT → TB_BUDGETFACT
    접두가 없으면 대문자만 반환합니다.
    """
    name = (table_name or "").strip().upper()
    if name.startswith("TBL_"):
        body = re.sub(r"[^A-Z0-9]", "", name[4:])
        return f"TBL_{body}" if body else name
    if name.startswith("TB_"):
        body = re.sub(r"[^A-Z0-9]", "", name[3:])
        return f"TB_{body}" if body else name
    return name


def canonicalize_fk_reference(fk_ref: str) -> str:
    """`테이블.컬럼` 형태 FK의 테이블 부분만 풀별 규칙에 맞게 정규화합니다."""
    raw = (fk_ref or "").strip()
    if "." not in raw:
        return raw
    t, _dot, rest = raw.partition(".")
    t_canon = canonical_pool_table_name(t.strip().upper())
    return f"{t_canon}.{rest}" if rest else t_canon


def pool_table_name_violation(
    table_name: str,
    pool: SchemaPool,
    settings: Settings,
) -> str | None:
    """
    규칙 위반 시 사람이 읽을 오류 문구를 반환하고, 통과 시 None.

    `TABLE_NAME_POOL_VALIDATION`이 False이면 항상 None.
    """
    if not settings.TABLE_NAME_POOL_VALIDATION:
        return None
    name = canonical_pool_table_name((table_name or "").strip().upper())
    if pool == "customer":
        pat = (settings.TABLE_NAME_REGEX_CUSTOMER or "").strip()
        label = "고객 풀(TBL_ 뒤 밑줄 없이 붙임, 예: TBL_CUSTDIM)"
    else:
        pat = (settings.TABLE_NAME_REGEX_ADMIN or "").strip()
        label = "관리자 풀(TB_ 뒤 밑줄 없이 붙임, 예: TB_FNMGT014)"
    if not pat:
        return None
    try:
        ok = re.fullmatch(pat, name, flags=re.IGNORECASE) is not None
    except re.error:
        return f"서버 설정의 정규식이 잘못되었습니다({pool})."
    if ok:
        return None
    return (
        f"테이블명 '{name}'이(가) {label} 명명 규칙에 맞지 않습니다. "
        f"엑셀 파일명 또는 «테이블명» 열 값을 규칙에 맞게 바꾼 뒤 다시 올려 주세요."
    )
