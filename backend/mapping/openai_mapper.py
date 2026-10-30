"""OpenAI GPT를 이용한 HFSR→DNA 컬럼 의미 유사도 최종 판정 모듈입니다.

편집거리 유사도 0.5~0.85 구간에 해당하는 후보들에 대해
GPT에게 한글 컬럼명 의미를 비교해 달라고 요청합니다.
"""

from __future__ import annotations

import json
import logging

from .column_matcher import ColumnCandidate, MappingResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
당신은 금융 시스템의 데이터베이스 컬럼 매핑 전문가입니다.
HFSR 시스템의 컬럼 한글명과 DNA 시스템의 후보 컬럼 한글명을 비교해
의미가 가장 유사한 것을 판단해 주세요.
반드시 아래 JSON 형식으로만 답변하세요.
"""

_USER_TEMPLATE = """\
HFSR 컬럼: "{hfsr_ko}"

DNA 후보 목록:
{candidates_text}

위 후보 중 HFSR 컬럼과 의미가 가장 유사한 것을 선택하세요.
의미가 유사한 후보가 없으면 idx=-1로 응답하세요.

응답 형식 (JSON만):
{{"idx": <0부터 시작하는 선택 인덱스 또는 -1>, "reason": "<간단한 이유>"}}
"""


class OpenAIMapper:
    """GPT를 호출해 컬럼 매핑 최종 판정을 수행합니다."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        try:
            from openai import OpenAI  # type: ignore
            self._client = OpenAI(api_key=api_key)
        except ImportError:
            raise RuntimeError(
                "openai 패키지가 설치되지 않았습니다. pip install openai 를 실행하세요."
            )
        self._model = model

    def map_columns(
        self,
        pending: list[tuple[dict, list[ColumnCandidate]]],
    ) -> list[MappingResult]:
        """
        Parameters
        ----------
        pending:
            [(hcol_dict, [ColumnCandidate, ...]), ...]
        """
        results: list[MappingResult] = []
        for hcol, candidates in pending:
            hfsr_col = hcol.get("col_name", "")
            hfsr_ko = (hcol.get("col_ko") or "").strip()

            candidates_text = "\n".join(
                f"{i}. [{c.table_name}] {c.col_name}: {c.col_ko}"
                for i, c in enumerate(candidates)
            )
            user_msg = _USER_TEMPLATE.format(
                hfsr_ko=hfsr_ko,
                candidates_text=candidates_text,
            )

            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0,
                    max_tokens=200,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content or "{}"
                data = json.loads(raw)
                idx = int(data.get("idx", -1))
                reason = data.get("reason", "")
            except Exception as exc:
                logger.warning("OpenAI 매핑 실패 (%s): %s", hfsr_ko, exc)
                # fallback: 편집거리 1위 후보를 low_confidence로 반환
                top = candidates[0]
                results.append(MappingResult(
                    hfsr_col=hfsr_col,
                    hfsr_ko=hfsr_ko,
                    status="low_confidence",
                    dna_table=top.table_name,
                    dna_col=top.col_name,
                    dna_ko=top.col_ko,
                    score=top.score,
                    method="edit_distance",
                    candidates=candidates,
                    message=f"OpenAI 호출 실패, 편집거리 1위 사용. 사유: {exc}",
                ))
                continue

            if idx < 0 or idx >= len(candidates):
                results.append(MappingResult(
                    hfsr_col=hfsr_col,
                    hfsr_ko=hfsr_ko,
                    status="unmatched",
                    candidates=candidates,
                    method="openai",
                    message=f"GPT가 매핑 불가 판정. 사유: {reason}",
                ))
            else:
                chosen = candidates[idx]
                results.append(MappingResult(
                    hfsr_col=hfsr_col,
                    hfsr_ko=hfsr_ko,
                    status="confirmed",
                    dna_table=chosen.table_name,
                    dna_col=chosen.col_name,
                    dna_ko=chosen.col_ko,
                    score=chosen.score,
                    method="openai",
                    message=f"GPT 확정. 사유: {reason}",
                ))

        return results
