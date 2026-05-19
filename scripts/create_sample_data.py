"""`data/excel/sample_customer/`·`sample_admin/`에 데모용 .xlsx 스키마를 생성합니다.

고객(SAS) 풀: TBL_ 뒤는 밑줄 없이 붙임(예: TBL_CUSTDIM, TBL_WFGWFL0514)
관리자(Oracle) 풀: TB_ 뒤 동일(예: TB_FNMGT014, TB_BUDGETFACT)
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from openpyxl import Workbook

_LEGACY_CUSTOMER = (
    "TBL_CUST_DIM.xlsx",
    "TBL_SALE_FACT.xlsx",
    "TBL_PRODUCT_DIM.xlsx",
    "TBL_GL_FACT.xlsx",
    "TBL_EMP_DIM.xlsx",
    "TBL_BUDGET_FACT.xlsx",
)
_LEGACY_ADMIN = ("TB_BUDGET_FACT.xlsx",)


def _write_table(
    wb: Workbook,
    *,
    korean_name: str,
    domain: str,
    description: str,
    rows: list[tuple[str, str, str, str, str, str, str, str]],
) -> None:
    """첫 시트에 ##META## 행과 컬럼 정의를 씁니다."""
    ws = wb.active
    ws.title = "Schema"
    ws.append(
        [
            "컬럼명(EN)",
            "컬럼명(KO)",
            "타입",
            "PK",
            "FK참조",
            "NULL허용",
            "설명",
            "인덱스",
        ]
    )
    ws.append(["##META##", korean_name, domain, description])
    for r in rows:
        ws.append(list(r))


def main() -> None:
    sample_customer = _ROOT / "data" / "excel" / "sample_customer"
    sample_admin = _ROOT / "data" / "excel" / "sample_admin"
    sample_customer.mkdir(parents=True, exist_ok=True)
    sample_admin.mkdir(parents=True, exist_ok=True)

    for name in _LEGACY_CUSTOMER:
        p = sample_customer / name
        if p.is_file():
            p.unlink()
    for name in _LEGACY_ADMIN:
        p = sample_admin / name
        if p.is_file():
            p.unlink()

    # —— 고객 풀 TBL_* (접미 DIM/FACT 등 한 덩어리) ——
    wb1 = Workbook()
    _write_table(
        wb1,
        korean_name="고객 차원",
        domain="영업",
        description="고객 마스터(성별·지역 등)",
        rows=[
            ("CUST_ID", "고객ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("CUST_NAME", "고객명", "VARCHAR2(200)", "", "", "Y", "고객 이름", "Y"),
            (
                "GENDER_CD",
                "성별코드",
                "CHAR(1)",
                "",
                "",
                "Y",
                "성별 M/F/U(미상)",
                "Y",
            ),
            ("REGION", "지역", "VARCHAR2(50)", "", "", "Y", "지역 코드", "Y"),
        ],
    )
    wb1.save(sample_customer / "TBL_CUSTDIM.xlsx")

    wb2 = Workbook()
    _write_table(
        wb2,
        korean_name="매출 팩트",
        domain="영업",
        description="일별 매출 집계(고객·상품·금액·수량)",
        rows=[
            ("SALE_ID", "매출ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            (
                "CUST_ID",
                "고객ID",
                "NUMBER",
                "",
                "TBL_CUSTDIM.CUST_ID",
                "N",
                "FK 고객",
                "Y",
            ),
            (
                "PROD_ID",
                "상품ID",
                "NUMBER",
                "",
                "TBL_PRODUCTDIM.PROD_ID",
                "N",
                "FK 상품",
                "Y",
            ),
            ("SALE_AMT", "매출금액", "NUMBER(18,2)", "", "", "N", "매출 금액", ""),
            ("SALE_QTY", "판매수량", "NUMBER(12,2)", "", "", "N", "판매 수량(단가=금액/수량)", "Y"),
            ("SALE_DT", "매출일", "DATE", "", "", "N", "매출 일자", "Y"),
        ],
    )
    wb2.save(sample_customer / "TBL_SALEFACT.xlsx")

    wb3 = Workbook()
    _write_table(
        wb3,
        korean_name="상품 차원",
        domain="영업",
        description="상품 마스터",
        rows=[
            ("PROD_ID", "상품ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("PROD_NAME", "상품명", "VARCHAR2(200)", "", "", "Y", "상품명", "Y"),
        ],
    )
    wb3.save(sample_customer / "TBL_PRODUCTDIM.xlsx")

    wb4 = Workbook()
    _write_table(
        wb4,
        korean_name="총계정원장",
        domain="재무",
        description="분개 팩트",
        rows=[
            ("GL_ID", "전표ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("ACCT_CD", "계정코드", "VARCHAR2(20)", "", "", "N", "계정", "Y"),
            ("AMT", "금액", "NUMBER(18,2)", "", "", "Y", "금액", ""),
        ],
    )
    wb4.save(sample_customer / "TBL_GLFACT.xlsx")

    wb5 = Workbook()
    _write_table(
        wb5,
        korean_name="사원 차원",
        domain="인사",
        description="사원 마스터(직급·연봉·부서)",
        rows=[
            ("EMP_ID", "사원ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("EMP_NM", "사원명", "VARCHAR2(100)", "", "", "Y", "이름", "Y"),
            ("DEPT_CD", "부서코드", "VARCHAR2(20)", "", "", "Y", "부서", "Y"),
            ("JOB_GRADE", "직급", "VARCHAR2(30)", "", "", "Y", "직급(예: 사원·대리·과장)", "Y"),
            (
                "ANNUAL_SAL",
                "연봉",
                "NUMBER(12)",
                "",
                "",
                "Y",
                "연간 급여(원)",
                "Y",
            ),
        ],
    )
    wb5.save(sample_customer / "TBL_EMPDIM.xlsx")

    wb_c_bgt = Workbook()
    _write_table(
        wb_c_bgt,
        korean_name="예산 팩트(고객뷰)",
        domain="재무",
        description="부서·계정별 예산 (고객 풀 샘플)",
        rows=[
            ("BGT_ID", "예산ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("BGT_YR", "예산연도", "NUMBER(4)", "", "", "N", "회계연도", "Y"),
            ("DEPT_CD", "부서코드", "VARCHAR2(20)", "", "", "Y", "부서", "Y"),
            ("ACCT_CD", "계정코드", "VARCHAR2(20)", "", "", "Y", "계정", "Y"),
            ("BGT_AMT", "예산금액", "NUMBER(18,2)", "", "", "N", "예산액", ""),
        ],
    )
    wb_c_bgt.save(sample_customer / "TBL_BUDGETFACT.xlsx")

    # —— 관리자 풀 TB_* (Oracle 예시 질의·DML 데모) ——
    wb_admin_cust = Workbook()
    _write_table(
        wb_admin_cust,
        korean_name="고객 차원(관리)",
        domain="영업",
        description="Oracle 관리 스키마·고객 마스터(등록일=신규 고객 판별)",
        rows=[
            ("CUST_ID", "고객ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("CUST_NAME", "고객명", "VARCHAR2(200)", "", "", "Y", "고객 이름", "Y"),
            (
                "REG_DT",
                "등록일",
                "DATE",
                "",
                "",
                "Y",
                "최초 등록일(신규 고객 구간)",
                "Y",
            ),
        ],
    )
    wb_admin_cust.save(sample_admin / "TB_CUSTDIM.xlsx")

    wb_admin_prod = Workbook()
    _write_table(
        wb_admin_prod,
        korean_name="상품 차원(관리)",
        domain="영업",
        description=(
            "상품·카테고리(CAT_NM, CAT_CD). 카테고리별 판매수량·금액은 "
            "TB_SALEFACT와 PROD_ID로 조인"
        ),
        rows=[
            ("PROD_ID", "상품ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("PROD_NAME", "상품명", "VARCHAR2(200)", "", "", "Y", "상품명", "Y"),
            ("CAT_CD", "카테고리코드", "VARCHAR2(20)", "", "", "Y", "카테고리 코드", "Y"),
            ("CAT_NM", "카테고리명", "VARCHAR2(100)", "", "", "Y", "카테고리명", "Y"),
        ],
    )
    wb_admin_prod.save(sample_admin / "TB_PRODUCTDIM.xlsx")

    wb_admin_sale = Workbook()
    _write_table(
        wb_admin_sale,
        korean_name="매출 팩트(관리)",
        domain="영업",
        description=(
            "판매 팩트: SALE_QTY(판매수량), SALE_AMT, PROD_ID. "
            "카테고리별 수량 합계는 TB_PRODUCTDIM과 PROD_ID 조인 후 CAT_NM 기준 GROUP BY"
        ),
        rows=[
            ("SALE_ID", "매출ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            (
                "CUST_ID",
                "고객ID",
                "NUMBER",
                "",
                "TB_CUSTDIM.CUST_ID",
                "N",
                "FK 고객",
                "Y",
            ),
            (
                "PROD_ID",
                "상품ID",
                "NUMBER",
                "",
                "TB_PRODUCTDIM.PROD_ID",
                "N",
                "FK 상품",
                "Y",
            ),
            ("SALE_QTY", "판매수량", "NUMBER(12,2)", "", "", "N", "판매 수량", "Y"),
            ("SALE_AMT", "매출금액", "NUMBER(18,2)", "", "", "N", "매출 금액", ""),
            ("SALE_DT", "매출일", "DATE", "", "", "N", "매출 일자", "Y"),
        ],
    )
    wb_admin_sale.save(sample_admin / "TB_SALEFACT.xlsx")

    wb_ch = Workbook()
    _write_table(
        wb_ch,
        korean_name="판매채널 차원",
        domain="영업",
        description="온라인·매장 등 판매 채널 마스터",
        rows=[
            ("CHAN_ID", "채널ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("CHAN_NM", "채널명", "VARCHAR2(100)", "", "", "Y", "채널명", "Y"),
            ("CHAN_TYPE", "채널유형", "VARCHAR2(30)", "", "", "Y", "ONLINE/OFFLINE", ""),
        ],
    )
    wb_ch.save(sample_admin / "TB_CHANNELDIM.xlsx")

    wb_st = Workbook()
    _write_table(
        wb_st,
        korean_name="매장 차원",
        domain="영업",
        description="지점·매장 마스터",
        rows=[
            ("STORE_ID", "매장ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("STORE_NM", "매장명", "VARCHAR2(200)", "", "", "Y", "매장명", "Y"),
            ("REGION_NM", "지역명", "VARCHAR2(100)", "", "", "Y", "시·도", "Y"),
        ],
    )
    wb_st.save(sample_admin / "TB_STOREDIM.xlsx")

    wb_vn = Workbook()
    _write_table(
        wb_vn,
        korean_name="협력사 차원",
        domain="조달",
        description="공급·협력 업체",
        rows=[
            ("VEND_ID", "협력사ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("VEND_NM", "협력사명", "VARCHAR2(200)", "", "", "Y", "업체명", "Y"),
            ("COUNTRY_CD", "국가코드", "CHAR(2)", "", "", "Y", "ISO 국가", ""),
        ],
    )
    wb_vn.save(sample_admin / "TB_VENDORDIM.xlsx")

    wb_oh = Workbook()
    _write_table(
        wb_oh,
        korean_name="주문 헤더",
        domain="영업",
        description="고객 주문 헤더(주문일·상태)",
        rows=[
            ("ORD_ID", "주문ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            (
                "CUST_ID",
                "고객ID",
                "NUMBER",
                "",
                "TB_CUSTDIM.CUST_ID",
                "N",
                "FK 고객",
                "Y",
            ),
            ("ORD_DT", "주문일", "DATE", "", "", "N", "주문 일자", "Y"),
            ("STATUS_CD", "상태코드", "VARCHAR2(20)", "", "", "Y", "주문상태", "Y"),
        ],
    )
    wb_oh.save(sample_admin / "TB_ORDERHDR.xlsx")

    wb_ol = Workbook()
    _write_table(
        wb_ol,
        korean_name="주문 라인",
        domain="영업",
        description="주문별 상품·수량·금액(주문 헤더·상품 FK)",
        rows=[
            ("LINE_ID", "라인ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            (
                "ORD_ID",
                "주문ID",
                "NUMBER",
                "",
                "TB_ORDERHDR.ORD_ID",
                "N",
                "FK 주문",
                "Y",
            ),
            (
                "PROD_ID",
                "상품ID",
                "NUMBER",
                "",
                "TB_PRODUCTDIM.PROD_ID",
                "N",
                "FK 상품",
                "Y",
            ),
            ("QTY", "수량", "NUMBER(12,2)", "", "", "N", "주문 수량", "Y"),
            ("LINE_AMT", "라인금액", "NUMBER(18,2)", "", "", "N", "라인 금액", ""),
        ],
    )
    wb_ol.save(sample_admin / "TB_ORDERLINE.xlsx")

    wb_inv = Workbook()
    _write_table(
        wb_inv,
        korean_name="재고 스냅샷",
        domain="물류",
        description="상품·창고별 재고 수량(일 스냅샷)",
        rows=[
            ("SNAPSHOT_ID", "스냅샷ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            (
                "PROD_ID",
                "상품ID",
                "NUMBER",
                "",
                "TB_PRODUCTDIM.PROD_ID",
                "N",
                "FK 상품",
                "Y",
            ),
            ("WH_CD", "창고코드", "VARCHAR2(20)", "", "", "Y", "창고", "Y"),
            ("STK_QTY", "재고수량", "NUMBER(12,2)", "", "", "N", "재고 수량", "Y"),
            ("AS_OF_DT", "기준일", "DATE", "", "", "N", "스냅샷 일자", "Y"),
        ],
    )
    wb_inv.save(sample_admin / "TB_INVENTORYFACT.xlsx")

    wb_rg = Workbook()
    _write_table(
        wb_rg,
        korean_name="지역 차원",
        domain="영업",
        description="권역·지역 코드 마스터",
        rows=[
            ("REGION_CD", "지역코드", "VARCHAR2(20)", "Y", "", "N", "PK", "Y"),
            ("REGION_NM", "지역명", "VARCHAR2(100)", "", "", "Y", "지역명", "Y"),
        ],
    )
    wb_rg.save(sample_admin / "TB_REGIONDIM.xlsx")

    wb6 = Workbook()
    _write_table(
        wb6,
        korean_name="예산 팩트(관리)",
        domain="재무",
        description="부서·계정별 예산 및 실적(예산 대비 실적률)",
        rows=[
            ("BGT_ID", "예산ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("BGT_YR", "예산연도", "NUMBER(4)", "", "", "N", "회계연도", "Y"),
            ("DEPT_CD", "부서코드", "VARCHAR2(20)", "", "", "Y", "부서", "Y"),
            ("ACCT_CD", "계정코드", "VARCHAR2(20)", "", "", "Y", "계정", "Y"),
            ("BGT_AMT", "예산금액", "NUMBER(18,2)", "", "", "N", "예산액", ""),
            (
                "ACT_AMT",
                "실적금액",
                "NUMBER(18,2)",
                "",
                "",
                "Y",
                "집계 실적(예산 대비)",
                "Y",
            ),
            ("BASE_DT", "기준일", "DATE", "", "", "Y", "기준일자", "Y"),
        ],
    )
    wb6.save(sample_admin / "TB_BUDGETFACT.xlsx")

    wb7 = Workbook()
    _write_table(
        wb7,
        korean_name="예산관리014",
        domain="재무",
        description="관리자 전용 예산 관리 테이블(샘플)",
        rows=[
            ("MGT_ID", "관리ID", "NUMBER", "Y", "", "N", "PK", "Y"),
            ("BGT_CD", "예산코드", "VARCHAR2(30)", "", "", "N", "예산 코드", "Y"),
            ("MGT_AMT", "관리금액", "NUMBER(18,2)", "", "", "Y", "금액", ""),
            ("REG_DT", "등록일", "DATE", "", "", "Y", "등록 일자", "Y"),
        ],
    )
    wb7.save(sample_admin / "TB_FNMGT014.xlsx")

    print(f"고객 풀 샘플: {sample_customer} (TBL_* 6개, 붙여쓰기 명명)")
    print(
        f"관리자 풀 샘플: {sample_admin} "
        f"(TB_* 12개: 영업·재무·물류·조달·관리014)"
    )


if __name__ == "__main__":
    main()
