/* 새도약기금 매각 대상건 산출 — 대상 추출(tmp) + 매각 심사 부가 컬럼 */

WITH /* 건별 최신 연체 1건, 연체등록일 2018-06-20 미만 */
     arre_latest AS (
       SELECT LOAN_ID,
              LOAN_SQNO,
              ARRE_ARNG_DATE,
              ARRE_RGST_DT
       FROM   (SELECT LOAN_ID,
                      LOAN_SQNO,
                      ARRE_ARNG_DATE,
                      ARRE_RGST_DT,
                      ROW_NUMBER()
                        OVER(PARTITION BY LOAN_ID, LOAN_SQNO
                             ORDER BY ARRE_RGST_DT DESC) AS rn
               FROM   TB_FNDLY003)
       WHERE  rn = 1
              AND ARRE_RGST_DT < '20180620'),
     /* 미종료 특수채권 + 대출기본 조건 */
     loan_spbd AS (
       SELECT spbd.LOAN_ID,
              spbd.LOAN_SQNO,
              mgt.CUST_ID,
              mgt.FRLN_HNDL_AMT,
              mgt.LOAN_DATE,
              spbd.SPBD_FRST_RGDT,
              spbd.PRSC_COMP_DT,
              spbd.PRSC_STOP_RSDV
       FROM   TB_FNBAD025 spbd
       INNER JOIN TB_FNMGT014 mgt
               ON spbd.LOAN_ID = mgt.LOAN_ID
              AND spbd.LOAN_SQNO = mgt.LOAN_SQNO
       WHERE  mgt.LOAN_SUBJ_DVSN = '01'
              AND ( mgt.SUPT_OBJT_DVSN IN ('1', '2', '3')
                    OR ( mgt.SUPT_OBJT_DVSN = '5'
                         AND mgt.SUPT_DVSN = '1' ) )
              AND spbd.SPBD_END_DATE IS NULL),
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
       FROM   (SELECT ls.LOAN_ID,
                      ls.LOAN_SQNO,
                      ls.CUST_ID,
                      al.ARRE_RGST_DT AS 연체시작일자,
                      al.ARRE_ARNG_DATE AS 연체정리일자,
                      ls.FRLN_HNDL_AMT AS 대출별대출금액,
                      ls.SPBD_FRST_RGDT AS 특수채권등록일자,
                      SUM(ls.FRLN_HNDL_AMT)
                        OVER(PARTITION BY ls.CUST_ID) AS 차주별대출금액,
                      ls.PRSC_COMP_DT AS 시효완성일자,
                      ls.LOAN_DATE,
                      ls.PRSC_STOP_RSDV AS 시효중단사유
               FROM   arre_latest al
               INNER JOIN loan_spbd ls
                       ON ls.LOAN_ID = al.LOAN_ID
                      AND ls.LOAN_SQNO = al.LOAN_SQNO) base
       WHERE  base.차주별대출금액 <= 50000000),
     /* 고객별 최신 개인회생 — 폐지(73) 종결일 */
     prsn_revi AS (
       SELECT revi.CUST_ID,
              revi.PSRV_END_DATE
       FROM   TB_FNBAD075 revi
       WHERE  revi.PRSN_REVI_SQNO = (SELECT MAX(x.PRSN_REVI_SQNO)
                                     FROM   TB_FNBAD075 x
                                     WHERE  x.CUST_ID = revi.CUST_ID)
              AND revi.PSRV_END_RSCD = '73'
              AND revi.PSRV_END_DATE IS NOT NULL),
     /* 고객별 최신 신용회복 — 실효일 */
     cred_recv AS (
       SELECT recv.CUST_ID,
              recv.LAPS_DATE
       FROM   TB_FNBAD050 recv
       WHERE  recv.RQST_NOTC_DATE = (SELECT MAX(x.RQST_NOTC_DATE)
                                    FROM   TB_FNBAD050 x
                                    WHERE  x.CUST_ID = recv.CUST_ID)),
     /* 고객별 최신 유효 면책 확정일 */
     immu AS (
       SELECT /*+ NO_MERGE */
              x.CUST_ID,
              x.IMMU_DCSN_DATE AS CONF_DATE
       FROM   TB_FNBAD056 x
       WHERE  x.IMMU_SQNO = (SELECT MAX(m.IMMU_SQNO)
                             FROM   TB_FNBAD055 m
                             WHERE  m.CUST_ID = x.CUST_ID)
              AND x.IMMU_CNCL_DATE IS NULL
              AND x.DEL_YN = 'N')
SELECT t.*,
       pr.PSRV_END_DATE AS 채무조정효력상실일_개인회생,
       cr.LAPS_DATE AS 채무조정효력상실일_신용회복,
       GREATEST(NVL(pr.PSRV_END_DATE, '0'), NVL(cr.LAPS_DATE, '0')) AS 채무조정효력상실일_최종,
       CASE
         WHEN cust.DEAD_YN = 'Y'
              AND cust.DEAD_DATE IS NOT NULL THEN 'Y'
         WHEN EXISTS (SELECT 1
                      FROM   TB_FNETL215 d
                      WHERE  d.RSDN_RGST_NO = cust.RSDN_RGST_NO) THEN 'Y'
         ELSE 'N'
       END AS 사망여부,
       CASE
         WHEN im.CUST_ID IS NOT NULL
              AND im.CONF_DATE >= t.LOAN_DATE THEN 'Y'
         ELSE 'N'
       END AS 면책여부,
       CASE
         WHEN EXISTS (SELECT 1
                      FROM   TB_FNMGT011 g
                      WHERE  g.LOAN_ID = t.LOAN_ID
                             AND g.LOAN_SQNO = t.LOAN_SQNO
                             AND g.GURT_DEBT_EPDT IS NULL
                             AND g.RLMN_CLSF_CODE IN ('1')) THEN 'Y'
         ELSE 'N'
       END AS 권리행사가능관계인유무
FROM   tmp t
LEFT JOIN prsn_revi pr
       ON t.CUST_ID = pr.CUST_ID
LEFT JOIN cred_recv cr
       ON t.CUST_ID = cr.CUST_ID
LEFT JOIN TB_CSSCM010 cust
       ON t.CUST_ID = cust.CUST_ID
LEFT JOIN immu im
       ON t.CUST_ID = im.CUST_ID;
