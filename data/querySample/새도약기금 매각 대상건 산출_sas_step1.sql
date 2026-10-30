PROC SQL;
SELECT
    base.LOAN_ID,
    base.LOAN_SQNO,
    base.CUST_ID,
    base.연체시작일자,
    base.연체정리일자,
    base.대출별대출금액,
    base.차주별대출금액,
    base.특수채권등록일자,
    base.시효완성일자,
    base.시효중단사유,
    base.LOAN_DATE
FROM (
  SELECT
      ls.LOAN_ID,
      ls.LOAN_SQNO,
      ls.CUST_ID,
      ly003.ARRE_RGST_DATE AS 연체시작일자 LABEL="연체시작일자",
      ly003.ARRE_ARGM_DATE AS 연체정리일자 LABEL="연체정리일자",
      ls.FRST_LOAN_HNDL_AMT AS 대출별대출금액 LABEL="대출별대출금액",
      ls.SPFC_BOND_FRST_RGST_DATE AS 특수채권등록일자 LABEL="특수채권등록일자",
      SUM(ls.FRST_LOAN_HNDL_AMT)
        OVER (PARTITION BY ls.CUST_ID) AS 차주별대출금액 LABEL="차주별대출금액",
      ls.STLT_CMPT_DATE AS 시효완성일자 LABEL="시효완성일자",
      ls.LOAN_DATE,
      ls.STLT_SSPS_RESN_DVSN_CODE AS 시효중단사유 LABEL="시효중단사유"
  FROM (
    SELECT
        ly003_rn.LOAN_ID,
        ly003_rn.LOAN_SQNO,
        ly003_rn.ARRE_ARGM_DATE,
        ly003_rn.ARRE_RGST_DATE
    FROM (
      SELECT
          ROW_NUMBER()
            OVER (
              PARTITION BY fd0503.LOAN_ID, fd0503.LOAN_SQNO
              ORDER BY fd0503.ARRE_RGST_DATE DESC
            ) AS rn,
          fd0503.LOAN_ID,
          fd0503.LOAN_SQNO,
          fd0503.ARRE_ARGM_DATE,
          fd0503.ARRE_RGST_DATE
      FROM &MYLIB..TBL_WFGWFD0503 AS fd0503
    ) AS ly003_rn
    WHERE ly003_rn.rn = 1
      AND ly003_rn.ARRE_RGST_DATE < '19JUN2018'd
  ) AS ly003
  INNER JOIN (
    SELECT
        fp0525.LOAN_ID,
        fp0525.LOAN_SQNO,
        fl0514.CUST_ID,
        fl0514.FRST_LOAN_HNDL_AMT,
        fl0514.LOAN_DATE,
        fp0525.SPFC_BOND_FRST_RGST_DATE,
        fp0525.STLT_CMPT_DATE,
        fp0525.STLT_SSPS_RESN_DVSN_CODE
    FROM &MYLIB..TBL_WFGWFP0525 AS fp0525
    INNER JOIN &MYLIB..TBL_WFGWFL0514 AS fl0514
      ON fp0525.LOAN_ID = fl0514.LOAN_ID
     AND fp0525.LOAN_SQNO = fl0514.LOAN_SQNO
    WHERE fl0514.LOAN_SUBJ_DVSN_CODE = '01'
      AND (
            fl0514.FNCG_SUPT_TRGT_DVSN_CODE IN ('1', '2', '3')
         OR (
                fl0514.FNCG_SUPT_TRGT_DVSN_CODE = '5'
            AND fl0514.SUPT_DVSN_CODE = '1'
            )
          )
      AND fp0525.SPFC_BOND_CSMT_DATE IS NULL
  ) AS ls
    ON ls.LOAN_ID = ly003.LOAN_ID
   AND ls.LOAN_SQNO = ly003.LOAN_SQNO
) AS base
WHERE base.차주별대출금액 <= 50000000;
QUIT;
