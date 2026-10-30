"""HFSR 컬럼 한글명 ↔ DNA 컬럼 한글명 유사도 기반 매핑 모듈입니다.

1단계: Levenshtein 편집거리 유사도 ≥ 0.85 → 확정 매핑 (API 호출 없음)
2단계: 0.5 ~ 0.85 구간 → OpenAI GPT 의미 기반 최종 판정
미달(< 0.5): 매핑 불가 처리
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

# 확정 매핑 임계값 (편집거리 유사도)
_CONFIRM_THRESHOLD = 0.85
# GPT 판단 의뢰 최소 임계값
_CANDIDATE_THRESHOLD = 0.5
# GPT 판단 시 후보로 넘길 최대 개수
_MAX_CANDIDATES = 5


@dataclass
class ColumnCandidate:
    """DNA 후보 컬럼 정보입니다."""
    table_name: str
    col_name: str
    col_ko: str
    score: float


@dataclass
class MappingResult:
    """단일 HFSR 컬럼의 매핑 결과입니다."""
    hfsr_col: str
    hfsr_ko: str
    status: Literal["confirmed", "low_confidence", "no_dna_schema", "unmatched"]
    dna_table: str | None = None
    dna_col: str | None = None
    dna_ko: str | None = None
    score: float = 0.0
    method: Literal["edit_distance", "openai", "none"] = "none"
    candidates: list[ColumnCandidate] = field(default_factory=list)
    message: str = ""


def _levenshtein(s: str, t: str) -> int:
    """두 문자열의 Levenshtein 편집거리를 계산합니다."""
    if s == t:
        return 0
    if not s:
        return len(t)
    if not t:
        return len(s)
    m, n = len(s), len(t)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if s[i - 1] == t[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def _edit_similarity(a: str, b: str) -> float:
    """편집거리 기반 유사도 [0, 1]를 반환합니다."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = _levenshtein(a.strip(), b.strip())
    max_len = max(len(a.strip()), len(b.strip()))
    return 1.0 - dist / max_len


@dataclass
class DnaColumn:
    """DNA 풀 컬럼 정보입니다."""
    table_name: str
    col_name: str
    col_ko: str


def match_columns(
    hfsr_cols: list[dict],
    dna_cols: list[DnaColumn],
    *,
    use_openai: bool = False,
    openai_mapper=None,
) -> list[MappingResult]:
    """
    HFSR 컬럼 목록을 DNA 컬럼 목록과 매핑합니다.

    Parameters
    ----------
    hfsr_cols:
        [{"col_name": str, "col_ko": str}, ...]
    dna_cols:
        DnaColumn 리스트
    use_openai:
        True이면 편집거리 미확정 구간을 OpenAI로 재판정합니다.
    openai_mapper:
        OpenAIMapper 인스턴스 (use_openai=True 시 필요).
    """
    if not dna_cols:
        return [
            MappingResult(
                hfsr_col=c["col_name"],
                hfsr_ko=c["col_ko"],
                status="no_dna_schema",
                message="DNA 풀에 등록된 테이블 정의서가 없습니다.",
            )
            for c in hfsr_cols
        ]

    results: list[MappingResult] = []
    pending_openai: list[tuple[dict, list[ColumnCandidate]]] = []

    for hcol in hfsr_cols:
        hfsr_ko = (hcol.get("col_ko") or "").strip()
        hfsr_col = hcol.get("col_name", "")

        if not hfsr_ko:
            results.append(MappingResult(
                hfsr_col=hfsr_col,
                hfsr_ko=hfsr_ko,
                status="unmatched",
                message="HFSR 컬럼 한글명이 없어 매핑을 건너뜁니다.",
            ))
            continue

        scored: list[ColumnCandidate] = []
        for dc in dna_cols:
            dna_ko = (dc.col_ko or "").strip()
            if not dna_ko:
                continue
            sim = _edit_similarity(hfsr_ko, dna_ko)
            scored.append(ColumnCandidate(
                table_name=dc.table_name,
                col_name=dc.col_name,
                col_ko=dna_ko,
                score=sim,
            ))

        scored.sort(key=lambda x: x.score, reverse=True)
        top = scored[0] if scored else None

        if top and top.score >= _CONFIRM_THRESHOLD:
            results.append(MappingResult(
                hfsr_col=hfsr_col,
                hfsr_ko=hfsr_ko,
                status="confirmed",
                dna_table=top.table_name,
                dna_col=top.col_name,
                dna_ko=top.col_ko,
                score=top.score,
                method="edit_distance",
            ))

        elif top and top.score >= _CANDIDATE_THRESHOLD:
            candidates = [c for c in scored[:_MAX_CANDIDATES] if c.score >= _CANDIDATE_THRESHOLD]
            if use_openai and openai_mapper:
                pending_openai.append((hcol, candidates))
            else:
                results.append(MappingResult(
                    hfsr_col=hfsr_col,
                    hfsr_ko=hfsr_ko,
                    status="low_confidence",
                    dna_table=candidates[0].table_name,
                    dna_col=candidates[0].col_name,
                    dna_ko=candidates[0].col_ko,
                    score=candidates[0].score,
                    method="edit_distance",
                    candidates=candidates,
                    message=f"유사도가 낮아 자동 확정하지 않았습니다 (최고 {candidates[0].score:.2f}).",
                ))
        else:
            results.append(MappingResult(
                hfsr_col=hfsr_col,
                hfsr_ko=hfsr_ko,
                status="unmatched",
                candidates=scored[:3],
                message="유사도가 너무 낮아 매핑을 건너뜁니다.",
            ))

    if pending_openai and use_openai and openai_mapper:
        openai_results = openai_mapper.map_columns(pending_openai)
        results.extend(openai_results)

    return results
