"""자연어 질의를 Oracle SQL 또는 SAS PROC SQL로 변환하는 Gemini 기반 생성기입니다."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Literal

from backend.config import get_settings
from backend.generator.prompts import (
    ORACLE_ADMIN_DML_SYSTEM_PROMPT,
    ORACLE_SYSTEM_PROMPT,
    SAS_SYSTEM_PROMPT,
)
from backend.models import ClarificationItem, GenerationResult, SearchResult

logger = logging.getLogger(__name__)

_QUOTA_EXHAUSTED_MSG = (
    "Gemini API 일일 사용 한도(quota)를 초과했습니다. "
    "https://ai.dev/rate-limit 에서 현재 사용량을 확인하거나, "
    "잠시 후 다시 시도해 주세요."
)
_RATE_LIMITED_MSG = (
    "Gemini API 분당 요청 한도(rate limit)에 도달했습니다. "
    "잠시 후 자동으로 재시도합니다..."
)


def _is_quota_exhausted(exc: Exception) -> bool:
    """일일 할당량 초과(quota) 여부를 확인합니다."""
    msg = str(exc).lower()
    return "quota" in msg and "exceeded" in msg


def _is_rate_limited(exc: Exception) -> bool:
    """429 rate limit 오류 여부를 확인합니다."""
    msg = str(exc)
    return "429" in msg or "resource_exhausted" in msg.lower()


def _is_transient_llm_unavailable(exc: Exception) -> bool:
    """503 등 일시적 LLM 장애(재시도 가능) 여부."""
    msg = str(exc).lower()
    return (
        "503" in msg
        or "unavailable" in msg
        or "high demand" in msg
        or "overloaded" in msg
    )

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

_SQL_EDIT_FOLLOW_UP = """[이번 턴 안내]
대화 기록에 직전에 생성한 SQL이 있습니다. 사용자의 이번 메시지는 대부분 **직전 SQL에 대한 추가·수정 요청**입니다.
- 수정·추가 요청이면: 직전 SQL의 의도(조회 조건·기간)를 유지한 채, 사용자가 지정한 **테이블(TB_*)·컬럼·조건**을 반영한 **완성된 SQL 전체**를 다시 작성하세요.
- 사용자가 다른 TB_* 테이블명을 지정하거나 «~말고», «연체 테이블» 등으로 바로잡으면, **이전에 잘못 쓴 테이블(예: TB_FNMGT014)은 버리고** 지시한 테이블만 사용하세요. 연체 조회는 **TB_FNDLY003**(연체등록일자 ARRE_RGST_DT 등)을 사용합니다.
- 명백히 다른 주제의 새 질의면: 새 SQL을 작성하세요.

"""

_CLARIFICATION_ANSWER_FOLLOW_UP = """[이번 턴 안내]
직전 턴에서 사용자에게 **추가 질문(clarifications)** 을 했고 아직 SQL이 없습니다. 사용자의 이번 메시지는 그 질문에 대한 **답변**입니다(객관식 선택 또는 [clarification 답변] 형식).
- 답변과 이전 대화·<schema_context>를 종합해 **완성된 SQL**을 작성하세요.
- 답변만으로도 여전히 애매하면 sql=null, clarifications 로 **남은 것만** 다시 질문하세요.
- SQL 수정 요청이 아닙니다.

"""


def _last_assistant_content(history: list[dict] | None) -> str:
    if not history:
        return ""
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            return str(msg.get("content") or "")
    return ""


def _history_awaiting_clarification_answer(history: list[dict] | None) -> bool:
    last = _last_assistant_content(history)
    return "[추가 질문]" in last or "[아직 SQL 없음" in last


def _history_last_assistant_had_sql(history: list[dict] | None) -> bool:
    last = _last_assistant_content(history)
    return last.startswith("SQL:\n") or last.lstrip().startswith("SQL:\n")


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

    @staticmethod
    def _normalize_clarifications(raw: Any) -> list[ClarificationItem]:
        """JSON clarifications 배열을 검증·정규화합니다(최대 3문항)."""
        if not isinstance(raw, list):
            return []
        out: list[ClarificationItem] = []
        for idx, item in enumerate(raw[:3]):
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or "").strip() or f"q{idx + 1}"
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            kind_raw = str(item.get("kind") or "single").strip().lower()
            kind: Literal["single", "text"] = (
                "text" if kind_raw == "text" else "single"
            )
            opts_raw = item.get("options") or []
            if not isinstance(opts_raw, list):
                opts_raw = []
            options = [str(o).strip() for o in opts_raw if str(o).strip()]
            if kind == "single":
                if len(options) < 2:
                    kind = "text"
                    options = []
                elif len(options) > 5:
                    options = options[:5]
            else:
                options = []
            out.append(
                ClarificationItem(
                    id=cid,
                    question=question,
                    kind=kind,
                    options=options,
                )
            )
        return out

    def _call_gemini(
        self,
        contents: str | list,
        *,
        system_instruction: str | None = None,
    ) -> Any:
        """Gemini API를 호출합니다. 429·503 등 일시 오류 시 최대 3회 재시도합니다."""
        max_retries = 3
        base_wait = 10  # seconds

        config_kwargs: dict[str, Any] = {
            "temperature": 0,
            "response_mime_type": "application/json",
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        for attempt in range(max_retries + 1):
            try:
                return self.genai_client.models.generate_content(
                    model=self.settings.LLM_MODEL,
                    contents=contents,
                    config=self._types.GenerateContentConfig(**config_kwargs),
                )
            except Exception as exc:
                if _is_quota_exhausted(exc):
                    # 일일 한도 초과 — 재시도해도 의미 없으므로 즉시 raise
                    raise RuntimeError(_QUOTA_EXHAUSTED_MSG) from exc

                if _is_rate_limited(exc) and attempt < max_retries:
                    wait = base_wait * (2 ** attempt)
                    logger.warning(
                        "Gemini API 429 rate limit (시도 %d/%d). %d초 후 재시도...",
                        attempt + 1,
                        max_retries,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                if _is_transient_llm_unavailable(exc) and attempt < max_retries:
                    wait = base_wait * (2 ** attempt)
                    logger.warning(
                        "Gemini API 일시 장애 503/UNAVAILABLE (시도 %d/%d). %d초 후 재시도...",
                        attempt + 1,
                        max_retries,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                raise

        raise RuntimeError("Gemini API 재시도 한도 초과")

    def generate(
        self,
        query: str,
        dialect: Literal["oracle", "sas"],
        search_results: list[SearchResult],
        *,
        oracle_profile: Literal["select_only", "admin_dml"] = "select_only",
        history: list[dict] | None = None,
    ) -> GenerationResult:
        """자연어 질의를 Oracle SQL 또는 SAS PROC SQL로 변환합니다."""
        try:
            chunk_texts = self._assemble_chunk_texts(search_results)

            follow_up_block = ""
            if history:
                if _history_awaiting_clarification_answer(history):
                    follow_up_block = _CLARIFICATION_ANSWER_FOLLOW_UP
                elif _history_last_assistant_had_sql(history):
                    follow_up_block = _SQL_EDIT_FOLLOW_UP

            user_message = f"""{follow_up_block}<schema_context>
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

            if history:
                # 멀티턴 대화: 이전 대화 이력을 Gemini contents 리스트로 구성
                contents: str | list = []
                for msg in history[-10:]:  # 최대 최근 10개 메시지만 포함
                    role = "user" if msg.get("role") == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
                contents.append({"role": "user", "parts": [{"text": user_message}]})
                response = self._call_gemini(contents, system_instruction=system_prompt)
            else:
                # 단일 턴: 기존 방식 유지
                full_prompt = system_prompt + "\n\n" + user_message
                response = self._call_gemini(full_prompt)

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
            clarifications = self._normalize_clarifications(
                data.get("clarifications")
            )

            if sql is not None:
                clarifications = []
            elif not clarifications and clarification_needed:
                clarifications = [
                    ClarificationItem(
                        id="clarify_1",
                        question=clarification_needed,
                        kind="text",
                        options=[],
                    )
                ]

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
                clarifications=clarifications,
            )
        except Exception as exc:
            logger.error("SQL 생성 중 오류: %s", exc, exc_info=True)
            explanation = str(exc)
            if _is_quota_exhausted(exc):
                explanation = _QUOTA_EXHAUSTED_MSG
            elif _is_transient_llm_unavailable(exc):
                explanation = (
                    "Gemini 모델이 일시적으로 과부하 상태입니다(503). "
                    "잠시 후 같은 질의를 다시 보내 주세요."
                )
            elif _is_rate_limited(exc):
                explanation = _RATE_LIMITED_MSG + f"\n\n원인: {exc}"
            else:
                explanation = f"오류: {explanation}"
            return GenerationResult(
                sql=None,
                explanation=explanation,
                confidence="low",
                used_tables=[],
                clarification_needed=None,
                dialect=dialect,
                input_tokens=0,
                output_tokens=0,
                clarifications=[],
            )
