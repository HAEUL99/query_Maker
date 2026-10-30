"""수납·대출 시연용 추가 DNA 고객풀 테이블 정의서(.xlsx)를 생성합니다.

기존 DW형 정의서(테이블정의서 시트)와 동일 형식으로
TBL_WFGWFR0510, TBL_WFGWCD0002, TBL_WFGWET0001, TBL_WFGWER0001 을 만듭니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from openpyxl import Workbook

_OUT_DIR = _ROOT / "data" / "excel" / "sample_customer"

_DW_HEADER = [
    "No.",
    "1차주제영역",
    "2차주제영역",
    "테이블명",
    "테이블한글명",
    "컬럼명",
    "컬럼한글명",
    "PK\n여부",
    "NULL\n여부",
    "타입",
    "길이",
    "소수점",
    "Default",
    "정의",
]

# (domain1, domain2, table, table_ko, columns)
# columns: (name_en, name_ko, pk, nullable, dtype, length, scale, desc)
_TABLE_SPECS: list[tuple[str, str, str, str, list[tuple]]] = [
    (
        "DW_융자",
        "DW_수납집계",
        "TBL_WFGWFR0510",
        "수납일별집계",
        [
            ("RECP_DATE", "영수일자", "Y", "N", "VARCHAR2", "8", "", "수납 영수 일자(YYYYMMDD)"),
            ("SUPT_OBJT_DVSN", "지원대상구분", "Y", "N", "VARCHAR2", "1", "", "지원대상 구분코드(개인/기업 등)"),
            ("LOAN_SUBJ_DVSN", "대출주체구분", "Y", "N", "VARCHAR2", "2", "", "대출주체 구분코드(신용/주택 등)"),
            ("RECV_BSNS_DVSN", "수납업무구분", "Y", "N", "VARCHAR2", "2", "", "수납 업무 구분(40=일반수납)"),
            ("LOAN_INCR_AMT", "대출발생금액", "N", "Y", "NUMBER", "24", "4", "일별 대출 발생 합계"),
            ("LOAN_REDU_AMT", "대출상환금액", "N", "Y", "NUMBER", "24", "4", "일별 대출 상환 합계"),
            ("INCM_INTE", "수입이자", "N", "Y", "NUMBER", "24", "4", "일별 수입이자 합계"),
            ("SURE_OCAT", "가수금발생", "N", "Y", "NUMBER", "24", "4", "일별 가수금 발생 합계"),
            ("SSPN_ARNG_AMT", "가수금정리", "N", "Y", "NUMBER", "24", "4", "일별 가수금 정리 합계"),
            ("MTGG_SURE_OCAT", "모기지발생", "N", "Y", "NUMBER", "24", "4", "일별 모기지 가수금 발생"),
            ("MTGG_SURE_ARAT", "모기지정리", "N", "Y", "NUMBER", "24", "4", "일별 모기지 가수금 정리"),
            ("LOAN_INCR_ERP", "대출발생_ERP", "N", "Y", "NUMBER", "24", "4", "ERP 반영 대출발생"),
            ("LOAN_REDU_ERP", "대출상환_ERP", "N", "Y", "NUMBER", "24", "4", "ERP 반영 대출상환"),
            ("INCM_INTE_ERP", "수입이자_ERP", "N", "Y", "NUMBER", "24", "4", "ERP 반영 수입이자"),
            ("SURE_OCAT_ERP", "가수금발생_ERP", "N", "Y", "NUMBER", "24", "4", "ERP 반영 가수금발생"),
            ("DNA_DAT_LDNG_DTTM", "DNA데이터적재일시", "N", "N", "DATE", "", "", "DNA DB 적재 일시"),
        ],
    ),
    (
        "DW_융자",
        "DW_공통코드",
        "TBL_WFGWCD0002",
        "공통코드",
        [
            ("CODE_ID", "코드ID", "Y", "N", "VARCHAR2", "30", "", "코드 그룹 ID(예: SUPT_OBJT_DVSN)"),
            ("CODE_VAL", "코드값", "Y", "N", "VARCHAR2", "20", "", "코드 값"),
            ("CODE_NAME", "코드명", "N", "Y", "VARCHAR2", "100", "", "코드 한글명"),
            ("SORT_ORD", "정렬순서", "N", "Y", "NUMBER", "5", "", "화면 표시 정렬 순서"),
            ("USE_YN", "사용여부", "N", "Y", "VARCHAR2", "1", "", "Y/N 사용 여부"),
            ("DNA_DAT_LDNG_DTTM", "DNA데이터적재일시", "N", "N", "DATE", "", "", "DNA DB 적재 일시"),
        ],
    ),
    (
        "DW_융자",
        "DW_영업일관리",
        "TBL_WFGWET0001",
        "영업일",
        [
            ("YMD", "일자", "Y", "N", "VARCHAR2", "8", "", "기준 일자(YYYYMMDD)"),
            ("HLDY_YN", "휴일여부", "N", "Y", "VARCHAR2", "1", "", "휴일 여부(Y/N)"),
            ("BIWK_OFDY_YN", "격주휴무여부", "N", "Y", "VARCHAR2", "1", "", "격주 휴무 여부"),
            ("WKDY_NM", "요일명", "N", "Y", "VARCHAR2", "10", "", "요일 한글명"),
            ("DNA_DAT_LDNG_DTTM", "DNA데이터적재일시", "N", "N", "DATE", "", "", "DNA DB 적재 일시"),
        ],
    ),
    (
        "DW_융자",
        "DW_ERP연계",
        "TBL_WFGWER0001",
        "ERP전문",
        [
            ("SLIP_DATE", "전표일자", "Y", "N", "VARCHAR2", "8", "", "ERP 전표 일자"),
            ("DLGS_TYPE_CODE", "전문유형코드", "Y", "N", "VARCHAR2", "10", "", "전문 유형(FN005/FS014 등)"),
            ("SEQ_NO", "일련번호", "Y", "N", "NUMBER", "10", "", "전문 일련번호"),
            ("CNCL_YN", "취소여부", "N", "Y", "VARCHAR2", "1", "", "취소 여부(1=취소)"),
            ("AMT", "금액", "N", "Y", "NUMBER", "24", "4", "전문 금액"),
            ("SUPT_OBJT_DVSN", "지원대상구분", "N", "Y", "VARCHAR2", "1", "", "지원대상 구분"),
            ("LOAN_SUBJ_DVSN", "대출주체구분", "N", "Y", "VARCHAR2", "2", "", "대출주체 구분"),
            ("DLGS_DATA", "전문데이터", "N", "Y", "VARCHAR2", "4000", "", "ERP 원본 전문 데이터"),
            ("DNA_DAT_LDNG_DTTM", "DNA데이터적재일시", "N", "N", "DATE", "", "", "DNA DB 적재 일시"),
        ],
    ),
]


def _write_dw_workbook(
    path: Path,
    *,
    title: str,
    written_date: str,
    domain1: str,
    domain2: str,
    table_name: str,
    table_ko: str,
    columns: list[tuple],
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "테이블정의서"
    ws.append(["테이블정의서"])
    ws.append(["작성자", None, None, None, "", None, "작성일", None, None, written_date])
    ws.append(list(_DW_HEADER))
    for i, col in enumerate(columns, start=1):
        name_en, name_ko, pk, nullable, dtype, length, scale, desc = col
        ws.append(
            [
                i,
                domain1,
                domain2,
                table_name,
                table_ko,
                name_en,
                name_ko,
                pk,
                nullable,
                dtype,
                length,
                scale,
                "",
                desc,
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"  ✓ {path.name} → {table_name} ({len(columns)} cols)")


def main() -> None:
    specs_by_file: dict[str, tuple] = {
        "테이블정의서(DW_수납집계)_20260401.xlsx": _TABLE_SPECS[0],
        "테이블정의서(DW_공통코드)_20260401.xlsx": _TABLE_SPECS[1],
        "테이블정의서(DW_영업일)_20260401.xlsx": _TABLE_SPECS[2],
        "테이블정의서(DW_ERP연계)_20260401.xlsx": _TABLE_SPECS[3],
    }
    print(f"고객풀 추가 DNA 정의서 생성: {_OUT_DIR}")
    for filename, (d1, d2, tbl, tbl_ko, cols) in specs_by_file.items():
        _write_dw_workbook(
            _OUT_DIR / filename,
            title=filename,
            written_date="2026-04-01",
            domain1=d1,
            domain2=d2,
            table_name=tbl,
            table_ko=tbl_ko,
            columns=cols,
        )
    print("완료: 4개 테이블 정의서 생성")


if __name__ == "__main__":
    main()
