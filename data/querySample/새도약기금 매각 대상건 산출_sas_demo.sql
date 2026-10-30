/* 고객풀 SAS 시연 — 1차·최종: 산출_sas_step1.sql, 산출_sas_step2.sql (Oracle 참조: 산출.sql) */

PROC SQL;
SELECT
    t.LOAN_ID,
    t.LOAN_SQNO,
    t.CUST_ID,
    t.연체시작일자,
    t.연체정리일자,
    t.대출별대출금액,
    t.차주별대출금액,
    t.특수채권등록일자,
    t.시효완성일자,
    t.시효중단사유,
    t.LOAN_DATE
FROM (
  /* 1차 추출 — 바깥 SELECT는 fl0514b 스코프 */
  SELECT
      fl0514b.LOAN_ID,
      fl0514b.LOAN_SQNO,
      fl0514b.CUST_ID,
      ly003.ARRE_RGST_DATE AS 연체시작일자 LABEL="연체시작일자",
      ly003.ARRE_ARGM_DATE AS 연체정리일자 LABEL="연체정리일자",
      fl0514b.FRST_LOAN_HNDL_AMT AS 대출별대출금액 LABEL="대출별대출금액",
      fp0525.SPFC_BOND_FRST_RGST_DATE AS 특수채권등록일자 LABEL="특수채권등록일자",
      SUM(fl0514b.FRST_LOAN_HNDL_AMT)
        OVER (PARTITION BY fl0514b.CUST_ID) AS 차주별대출금액 LABEL="차주별대출금액",
      fp0525.STLT_CMPT_DATE AS 시효완성일자 LABEL="시효완성일자",
      fl0514b.LOAN_DATE,
      fp0525.STLT_SSPS_RESN_DVSN_CODE AS 시효중단사유 LABEL="시효중단사유"
  FROM (
    /* … ly003 · fp0525 조인 (saedoyakFundDemo.js SAEDOYAK_SAS_SQL_STEP1 참고) … */
  ) AS base
  WHERE base.차주별대출금액 <= 50000000
) AS t;
QUIT;
