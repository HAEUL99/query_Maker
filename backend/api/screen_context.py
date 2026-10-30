"""HFSR 화면 컨텍스트 기반 미니 챗봇 및 DNA 컬럼 매핑 서비스 로직입니다."""

from __future__ import annotations

import logging
from typing import Any

from backend.config import get_settings
from backend.mapping.column_matcher import DnaColumn, MappingResult, match_columns
from backend.vectorstore.chroma_store import SchemaVectorStore

logger = logging.getLogger(__name__)

# 화면 챗봇용 시스템 프롬프트
_SCREEN_CHAT_SYSTEM = """\
당신은 금융 시스템의 화면 데이터 분석 도우미입니다.
사용자가 현재 보고 있는 화면 데이터와 필터 조건을 바탕으로 질문에 답변합니다.

[주의사항]
- 반드시 제공된 화면 데이터 범위 안에서만 답변하세요.
- 화면에 없는 데이터나 외부 지식은 사용하지 마세요
- 숫자를 언급할 때는 반드시 화면에서 가져온 값임을 명시하세요.
- 계산이 필요하면 화면 데이터의 수치를 직접 활용하세요.
- 불필요한 SQL은 생성하지 마세요.
"""


def build_screen_context_text(
    screen_id: str,
    screen_name: str,
    active_tab: str,
    filters: dict[str, str],
    columns: list[str],
    rows: list[list[str]],
    total_row: list[str] | None = None,
) -> str:
    """화면 데이터를 텍스트로 직렬화합니다 (LLM 컨텍스트용)."""
    lines: list[str] = [
        f"=== 화면: {screen_name} ({screen_id}) ===",
        f"현재 탭: {active_tab}",
    ]

    if filters:
        filter_str = ", ".join(f"{k}={v}" for k, v in filters.items())
        lines.append(f"필터 조건: {filter_str}")

    lines.append("")
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")

    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")

    if total_row:
        lines.append("| " + " | ".join(str(c) for c in total_row) + " |")

    lines.append(f"\n총 {len(rows)}건")
    return "\n".join(lines)


def call_screen_chat(
    screen_context: str,
    question: str,
    history: list[dict[str, str]],
) -> str:
    """Gemini를 호출해 화면 데이터 기반 답변을 생성합니다."""
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
    except ImportError:
        return "google-genai 패키지가 설치되지 않았습니다."

    settings = get_settings()
    client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    # 시스템 + 화면 컨텍스트를 첫 번째 user 메시지로 주입
    full_context = (
        _SCREEN_CHAT_SYSTEM
        + "\n\n[현재 화면 데이터]\n"
        + screen_context
    )

    contents: list[Any] = []

    # 히스토리 삽입
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=msg.get("content", ""))],
            )
        )

    # 현재 질문 (화면 컨텍스트를 앞에 붙인 첫 질문이면 함께 주입)
    if not history:
        user_text = f"{full_context}\n\n[질문]\n{question}"
    else:
        user_text = question

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=user_text)],
        )
    )

    import time

    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=full_context if history else None,
                    temperature=0.3,
                    max_output_tokens=1024,
                ),
            )
            return response.text or "답변을 생성하지 못했습니다."
        except Exception as exc:
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 2 ** attempt * 5
                logger.warning("Gemini 429, %s초 후 재시도 (%d/4)", wait, attempt + 1)
                time.sleep(wait)
            else:
                logger.exception("Gemini 호출 실패")
                return f"오류가 발생했습니다: {exc}"

    return "API 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요."


def get_dna_columns(store: SchemaVectorStore) -> list[DnaColumn]:
    """관리자 풀(admin)에서 DNA 테이블 컬럼 목록을 가져옵니다."""
    tables = store.list_tables(schema_pool="admin")
    dna_cols: list[DnaColumn] = []
    for t in tables:
        table_name = t.get("table_name", "")
        ts = store.get_table(table_name, schema_pool="admin")
        if ts is None:
            continue
        for col in ts.columns:
            dna_cols.append(
                DnaColumn(
                    table_name=table_name,
                    col_name=col.name,
                    col_ko=(col.korean_name or "").strip(),
                )
            )
    return dna_cols


def run_screen_mapping(
    hfsr_cols: list[dict],
    store: SchemaVectorStore,
) -> list[MappingResult]:
    """HFSR 컬럼 목록을 DNA 풀과 매핑합니다."""
    settings = get_settings()
    dna_cols = get_dna_columns(store)

    use_openai = bool(settings.OPENAI_API_KEY)
    openai_mapper = None
    if use_openai:
        try:
            from backend.mapping.openai_mapper import OpenAIMapper
            openai_mapper = OpenAIMapper(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_MAPPING_MODEL,
            )
            logger.info("OpenAI 매핑 활성화: %s", settings.OPENAI_MAPPING_MODEL)
        except Exception as exc:
            logger.warning("OpenAI 매퍼 초기화 실패, 편집거리만 사용: %s", exc)
            use_openai = False

    return match_columns(
        hfsr_cols,
        dna_cols,
        use_openai=use_openai,
        openai_mapper=openai_mapper,
    )
