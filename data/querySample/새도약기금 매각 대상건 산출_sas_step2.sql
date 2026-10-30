/* 새도약기금 매각 대상건 — 고객풀 SAS (1차 tmp + 매각 심사 컬럼) */

PROC SQL;
WITH
  /* 건별 최신 연체, 연체등록일 2018-06-20 미만 */
  arre_latest AS (
    SELECT LOAN_ID,
           LOAN_SQNO,
           ARRE_ARGM_DATE,
           ARRE_RGST_DATE
    FROM (
      SELECT ROW_NUMBER()
               OVER (PARTITION BY LOAN_ID, LOAN_SQNO
                     ORDER BY ARRE_RGST_DATE DESC) AS rn,
             LOAN_ID,
             LOAN_SQNO,
             ARRE_ARGM_DATE,
             ARRE_RGST_DATE
      FROM &MYLIB..TBL_WFGWFD0503
    ) z
    WHERE rn = 1
      AND ARRE_RGST_DATE < '19JUN2018'd
  ),
  /* 미종료 특수채권 + 대출기본 */
  loan_spbd AS (
    SELECT fp0525.LOAN_ID,
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
         OR (    fl0514.FNCG_SUPT_TRGT_DVSN_CODE = '5'
             AND fl0514.SUPT_DVSN_CODE = '1')
          )
      AND fp0525.SPFC_BOND_CSMT_DATE IS NULL
  ),
  tmp AS (
    SELECT base.LOAN_ID,
           base.LOAN_SQNO,
           base.CUST_ID,
           base.연체시작일자,
           base.연체정리일자,
           base.대출별대출금액,
           base.특수채권등록일자,
           base.차주별대출금액,
           base.시효완성일자,
           base.LOAN_DATE,
           base.시효중단사유
    FROM (
      SELECT ls.LOAN_ID,
             ls.LOAN_SQNO,
             ls.CUST_ID,
             al.ARRE_RGST_DATE AS 연체시작일자 LABEL="연체시작일자",
             al.ARRE_ARGM_DATE AS 연체정리일자 LABEL="연체정리일자",
             ls.FRST_LOAN_HNDL_AMT AS 대출별대출금액 LABEL="대출별대출금액",
             ls.SPFC_BOND_FRST_RGST_DATE AS 특수채권등록일자 LABEL="특수채권등록일자",
             SUM(ls.FRST_LOAN_HNDL_AMT)
               OVER (PARTITION BY ls.CUST_ID) AS 차주별대출금액 LABEL="차주별대출금액",
             ls.STLT_CMPT_DATE AS 시효완성일자 LABEL="시효완성일자",
             ls.LOAN_DATE,
             ls.STLT_SSPS_RESN_DVSN_CODE AS 시효중단사유 LABEL="시효중단사유"
      FROM arre_latest al
      INNER JOIN loan_spbd ls
        ON ls.LOAN_ID = al.LOAN_ID
       AND ls.LOAN_SQNO = al.LOAN_SQNO
    ) base
    WHERE base.차주별대출금액 <= 50000000
  ),
  /* 고객별 최신 개인회생 — 폐지(73) 종결일 */
  prsn_revi AS (
    SELECT revi.CUST_ID,
           revi.PRSN_RVVL_CSMT_DATE
    FROM &MYLIB..TBL_WFGWFP0575 AS revi
    WHERE revi.PRSN_RVVL_SQNO = (
            SELECT MAX(x.PRSN_RVVL_SQNO)
            FROM &MYLIB..TBL_WFGWFP0575 AS x
            WHERE x.CUST_ID = revi.CUST_ID
          )
      AND revi.PRSN_RVVL_CSMT_RESN_CODE = '73'
      AND revi.PRSN_RVVL_CSMT_DATE IS NOT NULL
  ),
  /* 고객별 최신 신용회복 — 실효일 */
  cred_recv AS (
    SELECT recv.CUST_ID,
           recv.LAPS_DATE
    FROM &MYLIB..TBL_WFGWFP0550 AS recv
    WHERE recv.APLC_NOTC_DATE = (
            SELECT MAX(x.APLC_NOTC_DATE)
            FROM &MYLIB..TBL_WFGWFP0550 AS x
            WHERE x.CUST_ID = recv.CUST_ID
          )
  ),
  /* 고객별 최신 유효 면책 확정일 */
  immu AS (
    SELECT fp0555.CUST_ID,
           fp0555.EXLN_DTRM_DATE AS CONF_DATE
    FROM &MYLIB..TBL_WFGWFP0555 AS fp0555
    INNER JOIN (
      SELECT CUST_ID, MAX(EXLN_DTRM_DATE) AS MAX_EXLN
      FROM &MYLIB..TBL_WFGWFP0555
      WHERE EXLN_CNCL_DATE IS NULL
        AND DLTN_YN = 'N'
      GROUP BY CUST_ID
    ) mx
      ON fp0555.CUST_ID = mx.CUST_ID
     AND fp0555.EXLN_DTRM_DATE = mx.MAX_EXLN
    WHERE fp0555.EXLN_CNCL_DATE IS NULL
      AND fp0555.DLTN_YN = 'N'
  )
SELECT t.*,
       pr.PRSN_RVVL_CSMT_DATE AS 채무조정효력상실일_개인회생 LABEL="채무조정효력상실일_개인회생",
       cr.LAPS_DATE AS 채무조정효력상실일_신용회복 LABEL="채무조정효력상실일_신용회복",
       MAX(
         COALESCE(pr.PRSN_RVVL_CSMT_DATE, '01JAN1900'd),
         COALESCE(cr.LAPS_DATE, '01JAN1900'd)
       ) AS 채무조정효력상실일_최종 LABEL="채무조정효력상실일_최종",
       CASE
         WHEN cust.DEAD_YN = 'Y'
          AND cust.DEAD_DATE IS NOT NULL THEN 'Y'
         ELSE 'N'
       END AS 사망여부 LABEL="사망여부",
       CASE
         WHEN im.CUST_ID IS NOT NULL
          AND im.CONF_DATE >= t.LOAN_DATE THEN 'Y'
         ELSE 'N'
       END AS 면책여부 LABEL="면책여부",
       CASE
         WHEN EXISTS (
           SELECT 1
           FROM &MYLIB..TBL_WFGWFL0511 AS g
           WHERE g.LOAN_ID = t.LOAN_ID
             AND g.LOAN_SQNO = t.LOAN_SQNO
             AND g.GURT_LBDB_EXMP_DATE IS NULL
             AND g.BORR_RLTS_DVSN_CODE = '1'
         ) THEN 'Y'
         ELSE 'N'
       END AS 권리행사가능관계인유무 LABEL="권리행사가능관계인유무"
FROM tmp t
LEFT JOIN prsn_revi pr
  ON t.CUST_ID = pr.CUST_ID
LEFT JOIN cred_recv cr
  ON t.CUST_ID = cr.CUST_ID
LEFT JOIN &MYLIB..TBL_CSSCM010 AS cust
  ON t.CUST_ID = cust.CUST_ID
LEFT JOIN immu im
  ON t.CUST_ID = im.CUST_ID;
QUIT;
