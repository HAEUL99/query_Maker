"""JSP → Pro*C → DBIO SQL 3단계 파싱으로 화면-테이블 매핑을 도출합니다.

파싱 대상 폴더:
  data/mock_up/jsp/  — 화면별 .jsp 파일 (서비스명 추출)
  data/mock_up/pc/   — 서비스별 .pc 파일  (DBIO 파일명 추출)
  data/mock_up/sql/  — DBIO .sql 파일      (테이블명 추출)

결과 예시:
  {
    "screen_id":   "SFNRCV767",
    "screen_name": "수납 마감자료 조회",
    "service":     "SFNRCV767SV",
    "dbio_file":   "DEFN_SFNRCV767VW_001_SP",
    "tables":      ["TB_FNSTS071", "TB_UVCDM002", ...],
  }
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_JSP_DIR = _REPO_ROOT / "data" / "mock_up" / "jsp"
_PC_DIR  = _REPO_ROOT / "data" / "mock_up" / "pc"
_SQL_DIR = _REPO_ROOT / "data" / "mock_up" / "sql"

# JSP: String serviceNm = "SFNRCV767SV";
_RE_SERVICE = re.compile(r'String\s+serviceNm\s*=\s*"([^"]+)"')
# JSP: <%-- Screen-Name: 수납 마감자료 조회 --%>
_RE_SCREEN_NAME = re.compile(r'<%--\s*Screen-Name:\s*(.+?)\s*--%>')

# PC: dbio_exec(ctx, "DEFN_SFNRCV767VW_001_SP", ...)
_RE_DBIO_EXEC = re.compile(r'dbio_exec\s*\(\s*\w+\s*,\s*"([^"]+)"')

# SQL: PROC_BODY 구간 마커
_RE_BODY_START = re.compile(r'/\*\s*@PROC_BODY_START\s*@\s*\*/')
_RE_BODY_END   = re.compile(r'/\*\s*@PROC_BODY_END\s*@\s*\*/')

# SQL PROC_BODY 내 테이블명: TB_ 또는 TBL_ 로 시작하는 단어
_RE_TABLE = re.compile(r'\b(TB[L]?_[A-Z0-9_]+)\b')


class ScreenMap(TypedDict):
    """화면-테이블 매핑 결과."""
    screen_id:   str
    screen_name: str
    service:     str
    dbio_file:   str
    tables:      list[str]


def _extract_proc_body(sql_text: str) -> str:
    """SQL 파일에서 PROC_BODY 구간만 추출합니다."""
    m_start = _RE_BODY_START.search(sql_text)
    m_end   = _RE_BODY_END.search(sql_text)
    if m_start and m_end and m_start.end() < m_end.start():
        return sql_text[m_start.end():m_end.start()]
    # 마커가 없으면 전체 사용
    return sql_text


def _parse_tables_from_sql(sql_path: Path) -> list[str]:
    """SQL 파일의 PROC_BODY 구간에서 테이블명을 추출합니다."""
    try:
        text = sql_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("SQL 파일 읽기 실패: %s — %s", sql_path, exc)
        return []

    body = _extract_proc_body(text)
    found = _RE_TABLE.findall(body)
    # 중복 제거 + 순서 유지
    seen: set[str] = set()
    tables: list[str] = []
    for t in found:
        if t not in seen:
            seen.add(t)
            tables.append(t)
    return tables


def _parse_pc(pc_path: Path) -> str | None:
    """PC 파일에서 dbio_exec 호출의 DBIO 파일명을 추출합니다."""
    try:
        text = pc_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("PC 파일 읽기 실패: %s — %s", pc_path, exc)
        return None

    m = _RE_DBIO_EXEC.search(text)
    if m:
        return m.group(1).strip()
    logger.warning("PC 파일에서 dbio_exec 패턴을 찾지 못했습니다: %s", pc_path.name)
    return None


def _parse_jsp(jsp_path: Path) -> tuple[str | None, str]:
    """JSP 파일에서 (service_name, screen_name)을 추출합니다."""
    try:
        text = jsp_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("JSP 파일 읽기 실패: %s — %s", jsp_path, exc)
        return None, ""

    service_name: str | None = None
    m_svc = _RE_SERVICE.search(text)
    if m_svc:
        service_name = m_svc.group(1).strip()
    else:
        logger.warning("JSP 파일에서 serviceNm 패턴을 찾지 못했습니다: %s", jsp_path.name)

    screen_name = ""
    m_nm = _RE_SCREEN_NAME.search(text)
    if m_nm:
        screen_name = m_nm.group(1).strip()

    return service_name, screen_name


def parse_all() -> list[ScreenMap]:
    """data/mock_up/{jsp,pc,sql} 폴더를 순회하여 화면-테이블 매핑 목록을 반환합니다."""
    if not _JSP_DIR.is_dir():
        logger.warning("JSP 폴더가 없습니다: %s", _JSP_DIR)
        return []

    results: list[ScreenMap] = []

    for jsp_path in sorted(_JSP_DIR.glob("*.jsp")):
        screen_id = jsp_path.stem  # SFNRCV767.jsp → SFNRCV767

        service_name, screen_name = _parse_jsp(jsp_path)
        if not service_name:
            logger.warning("서비스명을 추출하지 못해 건너뜁니다: %s", jsp_path.name)
            continue

        # PC 파일 탐색 (서비스명.pc)
        pc_path = _PC_DIR / f"{service_name}.pc"
        if not pc_path.is_file():
            logger.warning(
                "PC 파일을 찾지 못했습니다: %s (서비스: %s)", pc_path, service_name
            )
            continue

        dbio_file = _parse_pc(pc_path)
        if not dbio_file:
            continue

        # SQL 파일 탐색 (DBIO파일명.sql)
        sql_path = _SQL_DIR / f"{dbio_file}.sql"
        if not sql_path.is_file():
            logger.warning("SQL 파일을 찾지 못했습니다: %s", sql_path)
            continue

        tables = _parse_tables_from_sql(sql_path)
        if not tables:
            logger.warning("테이블명을 추출하지 못했습니다: %s", sql_path.name)

        entry: ScreenMap = {
            "screen_id":   screen_id,
            "screen_name": screen_name or screen_id,
            "service":     service_name,
            "dbio_file":   dbio_file,
            "tables":      tables,
        }
        results.append(entry)
        logger.info(
            "파싱 완료: %s → %s → %s → 테이블 %s개",
            screen_id, service_name, dbio_file, len(tables),
        )

    return results
