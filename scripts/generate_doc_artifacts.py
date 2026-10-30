#!/usr/bin/env python3
"""doc/ 폴더에 아키텍처·워크플로우 Word 산출물(.doc)을 생성합니다."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent.parent
DOC_DIR = ROOT / "doc"


def _set_doc_defaults(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "맑은 고딕"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")
    style.font.size = Pt(11)


def _add_title(doc: Document, text: str, subtitle: str = "") -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(18)
    if subtitle:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r2 = p2.add_run(subtitle)
        r2.font.size = Pt(11)
        r2.italic = True
    doc.add_paragraph()


def _heading(doc: Document, text: str, level: int = 1) -> None:
    doc.add_heading(text, level=level)


def _bullet(doc: Document, text: str, level: int = 0) -> None:
    p = doc.add_paragraph(text, style="List Bullet")
    if level:
        p.paragraph_format.left_indent = Inches(0.25 * level)


def build_architecture_doc() -> Document:
    doc = Document()
    _set_doc_defaults(doc)
    _add_title(
        doc,
        "Schema·Query (query-maker)",
        "아키텍처 구성도",
    )

    _heading(doc, "1. 개요")
    doc.add_paragraph(
        "본 시스템은 엑셀 테이블 정의서를 벡터 DB(ChromaDB)에 색인하고, "
        "자연어 질의를 통해 SAS PROC SQL(고객 풀) 또는 Oracle SQL(관리자 풀)을 생성하는 "
        "Text-to-SQL RAG 애플리케이션입니다. "
        "추가로 HFSR 화면 목업·화면 컨텍스트 챗봇, HFSR→DNA 컬럼 매핑, "
        "JSP/Pro*C/DBIO SQL 기반 화면-테이블 매핑 기능을 제공합니다."
    )

    _heading(doc, "2. 시스템 계층 구조")
    table = doc.add_table(rows=6, cols=3)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "계층"
    hdr[1].text = "구성 요소"
    hdr[2].text = "역할"
    rows = [
        (
            "표현 계층",
            "React + Vite SPA (frontend/)",
            "질의·관리자 UI, HFSR 목업(MockupPage), API 호출",
        ),
        (
            "API 계층",
            "FastAPI (backend/main.py, backend/api/routes.py)",
            "REST API, JWT 관리자 인증, CORS",
        ),
        (
            "도메인 계층",
            "parser / vectorstore / generator / mapping",
            "엑셀·DBIO 파싱, 검색·색인, SQL·챗·매핑 생성",
        ),
        (
            "외부 연동",
            "Google Gemini, OpenAI(선택)",
            "임베딩·LLM SQL·화면 챗, 컬럼 의미 매핑",
        ),
        (
            "저장 계층",
            "ChromaDB (chroma_db/), 엑셀·mock_up 파일",
            "스키마·화면매핑 벡터 영속, 정의서·소스 보관",
        ),
    ]
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            table.rows[i].cells[j].text = val

    _heading(doc, "3. 논리 아키텍처 (구성도)")
    doc.add_paragraph(
        "아래는 주요 컴포넌트 간 데이터·호출 관계를 나타낸 논리 구성도입니다."
    )
    diagram = doc.add_paragraph()
    diagram.add_run(
        "\n"
        "  [사용자 브라우저]\n"
        "        |\n"
        "        v\n"
        "  +------------------+     HTTP      +------------------------+\n"
        "  | React Frontend   | <-----------> | FastAPI Backend        |\n"
        "  | App.jsx          |   :5173/:8000 | routes.py              |\n"
        "  | MockupPage.jsx   |               | screen_context.py      |\n"
        "  +------------------+               +-----------+------------+\n"
        "                                               |\n"
        "           +----------------+------------------+----------------+\n"
        "           |                |                  |                |\n"
        "           v                v                  v                v\n"
        "  +---------------+ +---------------+ +---------------+ +--------------+\n"
        "  | excel_parser  | | chroma_store  | | sql_generator | | column_matcher|\n"
        "  | dbio_parser   | | (3 collections)| | (Gemini)      | | openai_mapper |\n"
        "  +-------+-------+ +-------+-------+ +-------+-------+ +------+-------+\n"
        "          |                 |                 |                |\n"
        "          v                 v                 v                v\n"
        "  [data/excel]      [chroma_db/]      [Gemini API]     [OpenAI API]\n"
        "  [data/mock_up]                      (필수)           (선택)\n"
    ).font.name = "Courier New"
    diagram.runs[0].font.size = Pt(8)

    _heading(doc, "4. ChromaDB 컬렉션")
    t2 = doc.add_table(rows=4, cols=3)
    t2.style = "Table Grid"
    t2.rows[0].cells[0].text = "컬렉션"
    t2.rows[0].cells[1].text = "설정 키"
    t2.rows[0].cells[2].text = "용도"
    coll = [
        ("table_schemas_customer", "CHROMA_COLLECTION_CUSTOMER", "고객 풀 TBL_* 스키마, SAS 질의"),
        ("table_schemas_admin", "CHROMA_COLLECTION_ADMIN", "관리자 풀 TB_* 스키마, Oracle 질의"),
        ("screen_table_map", "(고정명)", "화면 ID·서비스·DBIO·테이블 연결, 질의 컨텍스트 보강"),
    ]
    for i, (a, b, c) in enumerate(coll, start=1):
        t2.rows[i].cells[0].text = a
        t2.rows[i].cells[1].text = b
        t2.rows[i].cells[2].text = c

    _heading(doc, "5. 주요 API 엔드포인트")
    t3 = doc.add_table(rows=11, cols=3)
    t3.style = "Table Grid"
    t3.rows[0].cells[0].text = "메서드"
    t3.rows[0].cells[1].text = "경로"
    t3.rows[0].cells[2].text = "설명"
    apis = [
        ("POST", "/api/query", "자연어 → SQL (SAS/Oracle, history·screen_maps 지원)"),
        ("POST", "/api/index", "정의서 업로드 색인 (관리자 Bearer)"),
        ("POST", "/api/index/dbio", "mock_up JSP/PC/SQL 파싱 후 화면 매핑 색인"),
        ("POST", "/api/screen-chat", "화면 그리드 데이터 기반 Gemini 미니 챗"),
        ("POST", "/api/screen-mapping", "HFSR 컬럼 한글명 → DNA 컬럼 매핑"),
        ("GET", "/api/tables", "풀별 테이블 목록"),
        ("DELETE", "/api/tables/{name}", "테이블 단건 삭제 (관리자)"),
        ("POST", "/api/auth/login", "관리자 JWT 발급"),
        ("GET", "/api/stats", "풀별 색인 통계"),
        ("GET", "/docs", "Swagger API 문서"),
    ]
    for i, row in enumerate(apis, start=1):
        for j, val in enumerate(row):
            t3.rows[i].cells[j].text = val

    _heading(doc, "6. 기술 스택 및 실행 환경")
    _bullet(doc, "Python 3.11+, FastAPI, uvicorn, ChromaDB, openpyxl, google-genai, openai(선택)")
    _bullet(doc, "Node.js 18+, React, Vite, concurrently (npm run dev)")
    _bullet(doc, "환경 변수: .env (GOOGLE_API_KEY 필수, ADMIN_PASSWORD, OPENAI_API_KEY 선택)")
    _bullet(doc, "로컬 기본 URL: 프론트 http://localhost:5173, API http://localhost:8000")

    _heading(doc, "7. 보안·운영 고려사항")
    _bullet(doc, ".env 및 API 키는 Git에 커밋하지 않음 (.gitignore)")
    _bullet(doc, "Oracle SQL·업로드·DBIO 색인은 관리자 JWT(Bearer) 필요")
    _bullet(doc, "SAS는 customer 풀만, Oracle은 admin 풀만 사용 (풀·방언 검증)")
    _bullet(doc, "oracle_profile: select_only(조회만) / admin_dml(DML 허용, DDL 차단)")

    doc.add_paragraph()
    p = doc.add_paragraph("문서 버전: 1.0  |  프로젝트: query-maker")
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    return doc


def build_workflow_doc() -> Document:
    doc = Document()
    _set_doc_defaults(doc)
    _add_title(doc, "Schema·Query (query-maker)", "워크플로우")

    _heading(doc, "1. 스키마 정의서 색인 워크플로우")
    steps = [
        "운영자 또는 스크립트가 data/excel/ 하위에 .xlsx 테이블 정의서를 준비한다.",
        "excel_parser가 파일명·시트를 파싱하여 TableSchema(컬럼·한글명·도메인 등)를 생성한다.",
        "풀(customer/admin)별 테이블명 규칙(TBL_* / TB_*)을 검증한다(TABLE_NAME_POOL_VALIDATION).",
        "스키마 텍스트를 Gemini 임베딩으로 벡터화한다.",
        "ChromaDB 해당 컬렉션에 upsert한다.",
        "CLI: scripts/index.py --dir ... --pool customer|admin [--reset]",
        "웹: 관리자 탭 로그인 → 정의서 업로드 POST /api/index",
    ]
    for i, s in enumerate(steps, start=1):
        doc.add_paragraph(f"{i}. {s}")

    _heading(doc, "2. Text-to-SQL 질의 워크플로우")
    doc.add_paragraph(
        "사용자가 질의 탭(고객/SAS) 또는 관리자 탭(Oracle)에서 자연어를 입력하면 다음 순서로 처리됩니다."
    )
    flow = [
        "프론트엔드가 POST /api/query에 query, dialect, schema_pool, history 등을 전송.",
        "백엔드가 screen_table_map에서 질의와 유사한 화면 매핑 검색(유사도 ≥ 0.6 시 테이블·문맥 주입).",
        "ChromaDB에서 top_k 유사 테이블 스키마 검색.",
        "Oracle인 경우 관리자 Bearer 검증 및 oracle_profile 적용.",
        "SQLGenerator(Gemini)가 스키마 컨텍스트 + 대화 history로 SQL·설명·clarifications 생성.",
        "응답: sql, explanation, search_results, screen_maps, tokens.",
        "프론트가 결과 카드에 SQL·매칭 화면 정보를 표시; 후속 턴은 history로 SQL 수정·추가 질문 처리.",
    ]
    for i, s in enumerate(flow, start=1):
        doc.add_paragraph(f"{i}. {s}")

    _heading(doc, "3. DBIO 화면-테이블 매핑 워크플로우")
    steps3 = [
        "data/mock_up/jsp/*.jsp에서 serviceNm, 화면명 추출.",
        "동일 서비스명의 data/mock_up/pc/*.pc에서 dbio_exec DBIO 파일명 추출.",
        "data/mock_up/sql/{DBIO}.sql PROC_BODY 구간에서 TB_/TBL_ 테이블명 추출.",
        "관리자가 POST /api/index/dbio 호출 → parse_all() 결과를 screen_table_map에 색인.",
        "이후 /api/query 시 화면명·업무 질의와 연관된 테이블이 자동으로 검색 컨텍스트에 반영.",
    ]
    for i, s in enumerate(steps3, start=1):
        doc.add_paragraph(f"{i}. {s}")

    _heading(doc, "4. HFSR 화면 미니 챗봇 워크플로우")
    steps4 = [
        "메인 UI에서 HFSR 버튼 → MockupPage(수납 마감자료 조회 SFNRCV767) 팝업 표시.",
        "사용자가 현재 탭·필터·그리드 행/열 데이터를 컨텍스트로 질문 입력.",
        "POST /api/screen-chat: build_screen_context_text로 표 데이터 직렬화.",
        "Gemini가 화면 데이터 범위 내에서만 답변(외부 지식·임의 SQL 생성 금지).",
        "대화 history 유지로 연속 질의 가능.",
    ]
    for i, s in enumerate(steps4, start=1):
        doc.add_paragraph(f"{i}. {s}")

    _heading(doc, "5. HFSR → DNA 컬럼 매핑 워크플로우")
    steps5 = [
        "목업 화면에서 «매핑» 실행 → 화면 컬럼 한글명 목록을 POST /api/screen-mapping으로 전송.",
        "관리자 풀(Chroma)에서 DNA 테이블·컬럼 한글명 목록 로드.",
        "1단계: Levenshtein 유사도 ≥ 0.85 → edit_distance로 확정 매핑.",
        "2단계: 0.5~0.85 구간 → OPENAI_API_KEY 설정 시 GPT로 의미 판정(미설정 시 low_confidence).",
        "3단계: < 0.5 → unmatched. 결과를 UI 테이블로 표시(confirmed / low_confidence / unmatched).",
    ]
    for i, s in enumerate(steps5, start=1):
        doc.add_paragraph(f"{i}. {s}")

    _heading(doc, "6. 관리자 운영 워크플로우")
    steps6 = [
        ".env에 ADMIN_PASSWORD 설정.",
        "POST /api/auth/login → JWT 저장.",
        "Oracle SQL 생성(dialect=oracle, schema_pool=admin), 정의서 업로드, 인덱스 reset.",
        "DELETE /api/tables/{name}으로 단일 테이블 제거.",
        "GET /api/admin/stats/summary로 고객·관리자 풀 통계 일괄 조회.",
    ]
    for i, s in enumerate(steps6, start=1):
        doc.add_paragraph(f"{i}. {s}")

    _heading(doc, "7. 로컬 개발 실행 흐름")
    _bullet(doc, "cd query_Maker && source .venv/bin/activate && pip install -r requirements.txt")
    _bullet(doc, "cp .env.example .env 후 GOOGLE_API_KEY 설정")
    _bullet(doc, "PYTHONPATH=. python scripts/bootstrap_demo_index.py (최초 색인)")
    _bullet(doc, "npm install && cd frontend && npm install && cd .. && npm run dev")
    _bullet(doc, "브라우저: http://localhost:5173 / API 문서: http://localhost:8000/docs")

    doc.add_paragraph()
    p = doc.add_paragraph("문서 버전: 1.0  |  프로젝트: query-maker")
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    return doc


def main() -> None:
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    arch_docx = DOC_DIR / "_arch_temp.docx"
    flow_docx = DOC_DIR / "_flow_temp.docx"
    arch_doc = DOC_DIR / "아키텍처 구성도.doc"
    flow_doc = DOC_DIR / "워크플로우.doc"

    build_architecture_doc().save(arch_docx)
    build_workflow_doc().save(flow_docx)

    import subprocess

    for src, dst in ((arch_docx, arch_doc), (flow_docx, flow_doc)):
        subprocess.run(
            ["textutil", "-convert", "doc", str(src), "-output", str(dst)],
            check=True,
        )
        src.unlink(missing_ok=True)

    print(f"Created: {arch_doc}")
    print(f"Created: {flow_doc}")


if __name__ == "__main__":
    main()
