"""자연어 질의를 Oracle SQL 또는 SAS PROC SQL로 변환하는 Gemini 기반 생성기입니다."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from backend.config import get_settings
from backend.generator.prompts import (
    ORACLE_ADMIN_DML_SYSTEM_PROMPT,
    ORACLE_SYSTEM_PROMPT,
    SAS_SYSTEM_PROMPT,
)
from backend.models import GenerationResult, SearchResult

logger = logging.getLogger(__name__)

# 일반 사용자·SAS·Oracle 조회 전용: DML/DDL 모두 차단
_SELECT_ONLY_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|MERGE|CREATE|ALTER)\b",
    re.IGNORECASE,
)
# 관리자 Oracle DML: 스키마 변경(DDL)만 차단
_DDL_FORBIDDEN = re.compile(
    r"\b(CREATE|ALTER|DROP|TRUNCATE)\b",
    re.IGNORECASE,
)


class SQLGenerator:
    """스키마 검색 결과와 사용자 질의를 바탕으로 SQL 생성 API를 호출합니다."""

    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self.settings = get_settings()
        self.genai_client = genai.Client(api_key=self.settings.GOOGLE_API_KEY)

    def _estimate_tokens(self, text: str) -> int:
        """텍스트의 토큰 수를 추정합니다."""
        return len(text) // 4

    @staticmethod
    def _parse_json_from_text(raw: str) -> dict[str, Any]:
        """모델 응답 문자열을 JSON 객체로 파싱합니다."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise

    def _assemble_chunk_texts(self, search_results: list[SearchResult]) -> str:
        """
        검색 결과의 청크를 이어붙이되, 추정 토큰이 `MAX_TOKENS_CONTEXT`를 넘지 않도록
        점수가 높은 항목부터 순서대로 포함합니다.
        """
        max_tok = self.settings.MAX_TOKENS_CONTEXT
        if not search_results:
            return ""

        ordered = sorted(search_results, key=lambda r: r.score, reverse=True)
        parts: list[str] = []
        for r in ordered:
            piece = r.chunk_text or ""
            if self._estimate_tokens(piece) > max_tok:
                piece = piece[: max_tok * 4]

            candidate = "\n\n".join(parts + [piece]) if parts else piece
            if self._estimate_tokens(candidate) <= max_tok:
                parts.append(piece)
            else:
                break

        return "\n\n".join(parts)

    def _normalize_sql(self, sql_raw: Any) -> str | None:
        """JSON의 sql 필드를 `str | None`으로 정규화합니다."""
        if sql_raw is None:
            return None
        s = str(sql_raw).strip()
        if not s or s.lower() == "null":
            return None
        return s

    @staticmethod
    def _normalize_clarification_needed(val: Any) -> str | None:
        """JSON의 clarification_needed를 추가 질문 문자열(`str | None`)로 정규화합니다."""
        if val is None or val is False:
            return None
        if val is True:
            return None
        if isinstance(val, str):
            t = val.strip()
            if not t or t.lower() == "null":
                return None
            return t
        return None

    def generate(
        self,
        query: str,
        dialect: Literal["oracle", "sas"],
        search_results: list[SearchResult],
        *,
        oracle_profile: Literal["select_only", "admin_dml"] = "select_only",
    ) -> GenerationResult:
        """자연어 질의를 Oracle SQL 또는 SAS PROC SQL로 변환합니다."""
        try:
            chunk_texts = self._assemble_chunk_texts(search_results)

            user_message = f"""<schema_context>
{chunk_texts}
</schema_context>

사용자 질의: {query}"""

            if dialect == "oracle":
                system_prompt = (
                    ORACLE_ADMIN_DML_SYSTEM_PROMPT
                    if oracle_profile == "admin_dml"
                    else ORACLE_SYSTEM_PROMPT
                )
            else:
                system_prompt = SAS_SYSTEM_PROMPT
            full_prompt = system_prompt + "\n\n" + user_message

            response = self.genai_client.models.generate_content(
                model=self.settings.LLM_MODEL,
                contents=full_prompt,
                config=self._types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text or ""

            data = self._parse_json_from_text(raw)

            sql = self._normalize_sql(data.get("sql"))
            explanation = str(data.get("explanation", "") or "").strip()
            used_tables = data.get("used_tables") or []
            if not isinstance(used_tables, list):
                used_tables = []
            used_tables = [str(x) for x in used_tables]

            conf = data.get("confidence", "medium")
            if isinstance(conf, str):
                conf = conf.strip().lower()
            if conf not in ("high", "medium", "low"):
                conf = "medium"
            confidence: Literal["high", "medium", "low"] = conf  # type: ignore[assignment]

            clarification_needed = self._normalize_clarification_needed(
                data.get("clarification_needed")
            )

            if sql is not None:
                if dialect == "oracle" and oracle_profile == "admin_dml":
                    if _DDL_FORBIDDEN.search(sql):
                        sql = None
                        explanation = f"[DDL 차단] {explanation}"
                elif _SELECT_ONLY_FORBIDDEN.search(sql):
                    sql = None
                    explanation = f"[보안차단] {explanation}"

            um = response.usage_metadata
            input_tokens = (um.prompt_token_count or 0) if um else 0
            output_tokens = (um.candidates_token_count or 0) if um else 0

            return GenerationResult(
                sql=sql,
                explanation=explanation,
                used_tables=used_tables,
                confidence=confidence,
                clarification_needed=clarification_needed,
                dialect=dialect,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
            )
        except Exception as exc:
            logger.error("SQL 생성 중 오류: %s", exc, exc_info=True)
            return GenerationResult(
                sql=None,
                explanation=f"오류: {exc}",
                confidence="low",
                used_tables=[],
                clarification_needed=None,
                dialect=dialect,
                input_tokens=0,
                output_tokens=0,
            )
