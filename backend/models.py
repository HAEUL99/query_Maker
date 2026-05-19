"""테이블 스키마·검색·생성 결과를 표현하는 데이터 클래스 모듈입니다."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ColumnSchema:
    """단일 컬럼의 메타데이터를 나타냅니다."""

    name: str
    korean_name: str
    data_type: str
    is_pk: bool
    is_fk: bool
    fk_reference: str
    nullable: bool
    description: str
    is_indexed: bool = False


@dataclass
class TableSchema:
    """하나의 테이블 정의와 소속 컬럼 목록을 나타냅니다."""

    table_name: str
    korean_name: str
    domain: str
    description: str
    source_file: str
    columns: list[ColumnSchema] = field(default_factory=list)

    def to_chunk_text(self) -> str:
        """임베딩·검색용으로 테이블과 컬럼 정보를 한 덩어리의 텍스트로 직렬화합니다."""
        lines: list[str] = [
            f"[테이블] {self.table_name} ({self.korean_name})",
            f"도메인: {self.domain}",
            f"설명: {self.description}",
            "컬럼:",
        ]
        for col in self.columns:
            tags: list[str] = []
            if col.is_pk:
                tags.append("[PK]")
            if col.is_fk and col.fk_reference:
                tags.append(f"[FK→{col.fk_reference}]")
            if col.is_indexed:
                tags.append("[INDEX]")
            if not col.nullable:
                tags.append("[NOT NULL]")
            tag_str = " ".join(tags)
            suffix = f" {tag_str}" if tag_str else ""
            lines.append(
                f"  - {col.name} ({col.data_type}) / {col.korean_name}{suffix}: {col.description}"
            )
        return "\n".join(lines)


@dataclass
class SearchResult:
    """벡터 검색으로 찾은 테이블 청크 한 건을 나타냅니다."""

    table_name: str
    score: float
    chunk_text: str
    metadata: dict[str, Any]


@dataclass
class GenerationResult:
    """LLM이 생성한 SQL과 부가 정보를 나타냅니다."""

    sql: str | None
    explanation: str
    used_tables: list[str]
    confidence: Literal["high", "medium", "low"]
    clarification_needed: str | None
    dialect: Literal["oracle", "sas"]
    input_tokens: int
    output_tokens: int
