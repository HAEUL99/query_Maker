/* @PROC_DISPLAY_START @ */
/* SQL*Plus / 화면 표시용 SELECT (Pro*C 로더는 이 구간을 사용하지 않음) */
SELECT
    A.recp_date AS 영수일자,
    A.supt_objt_dvsn AS 지원대상구분,
    B.code_name AS 지원대상구분_한글,
    A.loan_subj_dvsn AS 대출주체구분,
    C.code_name AS 대출주체구분_한글,
    A.loan_incr_amt AS 대출발생,
    A.loan_redu_amt AS 대출상환,
    A.incm_inte AS 수입이자,
    A.sure_ocat AS 가수금발생,
    A.sspn_arng_amt AS 가수금정리,
    A.mtgg_sure_ocat AS 모기지발생,
    A.mtgg_sure_arat AS 모기지정리,
    A.loan_incr_erp AS 대출발생_ERPHB,
    A.loan_redu_erp AS 대출상환_ERPHB,
    DECODE(A.recp_date, E.min_RECP_DATE, (A.incm_inte_erp + D.misu), A.incm_inte_erp) AS 수입이자_ERPHB,
    A.sure_ocat_erp AS 가수금발생_ERPHB,
    A.sure_arat_erp AS 가수금정리_ERPHB,
    A.mtgg_ocat_erp AS 모기지발생_ERPHB,
    A.mtgg_arat_erp AS 모기지정리_ERPHB,
    A.loan_incr_amt + D.tot_loan_incr_amt AS 대출발생_MOD,
    A.loan_redu_amt + D.tot_loan_redu_amt AS 대출상환_MOD,
    A.incm_inte + D.tot_incm_inte AS 수입이자_MOD,
    A.sure_ocat + D.tot_sure_ocat AS 가수금발생_MOD,
    A.sspn_arng_amt + D.tot_sspn_arng_amt AS 가수금정리_MOD,
    A.mtgg_sure_ocat + D.tot_mtgg_sure_ocat AS 모기지발생_MOD,
    A.mtgg_sure_arat + D.tot_mtgg_sure_arat AS 모기지정리_MOD
/* @PROC_DISPLAY_END @ */
/* @PROC_BODY_START @ */
FROM (
    SELECT
        A.recp_date,
        A.supt_objt_dvsn,
        A.loan_subj_dvsn,
        A.loan_incr_amt,
        A.loan_redu_amt,
        A.incm_inte,
        A.sure_ocat,
        A.sspn_arng_amt,
        A.mtgg_sure_ocat,
        A.mtgg_sure_arat,
        A.loan_incr_erp,
        A.loan_redu_erp,
        A.incm_inte_erp,
        A.sure_ocat_erp,
        A.sure_arat_erp,
        A.mtgg_ocat_erp,
        A.mtgg_arat_erp
    FROM (
        SELECT
            recp_date,
            supt_objt_dvsn,
            loan_subj_dvsn,
            SUM(NVL(loan_incr_amt, 0)) AS loan_incr_amt,
            SUM(NVL(loan_redu_amt, 0)) AS loan_redu_amt,
            SUM(NVL(incm_inte, 0)) AS incm_inte,
            SUM(NVL(sure_ocat, 0)) AS sure_ocat,
            SUM(NVL(sspn_arng_amt, 0)) AS sspn_arng_amt,
            SUM(NVL(mtgg_sure_ocat, 0)) AS mtgg_sure_ocat,
            SUM(NVL(mtgg_sure_arat, 0)) AS mtgg_sure_arat,
            SUM(NVL(loan_incr_erp, 0)) AS loan_incr_erp,
            SUM(NVL(loan_redu_erp, 0)) AS loan_redu_erp,
            SUM(NVL(incm_inte_erp, 0)) AS incm_inte_erp,
            SUM(NVL(sure_ocat_erp, 0)) AS sure_ocat_erp,
            SUM(NVL(sure_arat_erp, 0)) AS sure_arat_erp,
            SUM(NVL(mtgg_ocat_erp, 0)) AS mtgg_ocat_erp,
            SUM(NVL(mtgg_arat_erp, 0)) AS mtgg_arat_erp
        FROM (
            SELECT
                recp_date,
                DECODE(SIGN(TO_NUMBER(NVL(supt_objt_dvsn, 0)) - 5), -1, '3', '5') AS supt_objt_dvsn,
                loan_subj_dvsn,
                loan_incr_amt,
                loan_redu_amt,
                incm_inte,
                sure_ocat,
                sspn_arng_amt,
                mtgg_sure_ocat,
                mtgg_sure_arat,
                loan_incr_erp,
                loan_redu_erp,
                incm_inte_erp,
                sure_ocat_erp,
                sure_arat_erp,
                mtgg_ocat_erp,
                mtgg_arat_erp
            FROM TB_FNSTS071
            WHERE supt_objt_dvsn BETWEEN DECODE(&p_supt_objt_dusn, '5', '5', '1')
                                   AND DECODE(&p_supt_objt_dusn, '5', '7', '4')
              AND loan_subj_dvsn = &p_loan_subj_dvsn
              AND recp_date BETWEEN &p_stdd_ym || '01' AND &p_stdd_ym || '31'
        )
        GROUP BY recp_date, supt_objt_dvsn, loan_subj_dvsn
    ) A,
    TB_UVCDM002 B,
    TB_UVCDM002 C
    WHERE A.supt_objt_dvsn = B.CODE_VAL
      AND B.CODE_ID = 'SUPT_OBJT_DVSN'
      AND A.loan_subj_dvsn = C.CODE_VAL
      AND C.CODE_ID = 'LOAN_SUBJ_DVSN'
) A,
(
    SELECT MIN(ymd) AS min_RECP_DATE
    FROM TB_UVETC001
    WHERE SUBSTR(ymd, 1, 6) = &P_STDD_YM
      AND hldy_yn = 'N'
      AND biwk_ofdy_yn = 'N'
) E,
(
    SELECT
        A.recp_date,
        NVL(D.result_amt, 0) AS misu,
        DECODE(A.recp_date, W.recp_date, 0, -NVL(B.loan_incr_amt, 0)) + NVL(C.loan_incr_amt, 0) AS tot_loan_incr_amt,
        DECODE(A.recp_date, W.recp_date, 0, -NVL(B.loan_redu_amt, 0)) + NVL(C.loan_redu_amt, 0) AS tot_loan_redu_amt,
        DECODE(A.recp_date, W.recp_date, 0, -NVL(B.incm_inte, 0)) + NVL(C.incm_inte, 0) + NVL(D.result_amt, 0) AS tot_incm_inte,
        DECODE(A.recp_date, W.recp_date, 0, -NVL(B.sure_ocat, 0)) + NVL(C.sure_ocat, 0) AS tot_sure_ocat,
        DECODE(A.recp_date, W.recp_date, 0, -NVL(B.sspn_arng_amt, 0)) + NVL(C.sspn_arng_amt, 0) AS tot_sspn_arng_amt,
        DECODE(A.recp_date, W.recp_date, 0, -NVL(B.mtgg_sure_ocat, 0)) + NVL(C.mtgg_sure_ocat, 0) AS tot_mtgg_sure_ocat,
        DECODE(A.recp_date, W.recp_date, 0, -NVL(B.mtgg_sure_arat, 0)) + NVL(C.mtgg_sure_arat, 0) AS tot_mtgg_sure_arat
    FROM (
        SELECT ymd AS RECP_DATE
        FROM TB_UVETC001
        WHERE SUBSTR(ymd, 1, 6) = &P_STDD_YM
          AND hldy_yn = 'N'
          AND biwk_ofdy_yn = 'N'
        ORDER BY ymd
    ) A,
    (
        SELECT
            RECP_DATE,
            SUM(LOAN_INCR_AMT) AS LOAN_INCR_AMT,
            SUM(LOAN_REDU_AMT) AS LOAN_REDU_AMT,
            SUM(INCM_INTE) AS INCM_INTE,
            SUM(SURE_OCAT) AS SURE_OCAT,
            SUM(SSPN_ARNG_AMT) AS SSPN_ARNG_AMT,
            SUM(MTGG_SURE_OCAT) AS MTGG_SURE_OCAT,
            SUM(MTGG_SURE_ARAT) AS MTGG_SURE_ARAT
        FROM TB_FNSTS071
        WHERE SUBSTR(recp_date, 1, 6) = &P_STDD_YM
          AND supt_objt_dvsn BETWEEN DECODE(&p_supt_objt_dusn, '5', '5', '1')
                               AND DECODE(&p_supt_objt_dusn, '5', '7', '4')
          AND loan_subj_dvsn = &p_loan_subj_dvsn
          AND recv_bsns_dvsn = '40'
        GROUP BY recp_date
    ) B,
    (
        SELECT MAX(ymd) AS RECP_DATE
        FROM TB_UVETC001
        WHERE SUBSTR(ymd, 1, 6) = &P_STDD_YM
          AND hldy_yn = 'N'
          AND biwk_ofdy_yn = 'N'
    ) W,
    (
        SELECT
            X.RECP_DATE AS ORG_RECP_DATE,
            Y.RECP_DATE AS RECP_DATE_AFT3,
            NVL(Z.LOAN_INCR_AMT, 0) AS LOAN_INCR_AMT,
            NVL(Z.LOAN_REDU_AMT, 0) AS LOAN_REDU_AMT,
            NVL(Z.INCM_INTE, 0) AS INCM_INTE,
            NVL(Z.SURE_OCAT, 0) AS SURE_OCAT,
            NVL(Z.SSPN_ARNG_AMT, 0) AS SSPN_ARNG_AMT,
            NVL(Z.MTGG_SURE_OCAT, 0) AS MTGG_SURE_OCAT,
            NVL(Z.MTGG_SURE_ARAT, 0) AS MTGG_SURE_ARAT
        FROM (
            SELECT
                X.NO,
                X.RECP_DATE
            FROM (
                SELECT
                    ROWNUM AS NO,
                    ymd AS RECP_DATE
                FROM TB_UVETC001 X
                WHERE YMD LIKE &P_STDD_YM || '%'
                  AND X.HLDY_YN = 'N'
                  AND X.BIWK_OFDY_YN = 'N'
            ) X,
            TB_UVDUM001 B
            WHERE X.NO = B.NO
        ) X,
        (
            SELECT
                A.NO,
                A.RECP_DATE
            FROM (
                SELECT
                    ROWNUM AS NO,
                    Y.YMD AS RECP_DATE
                FROM TB_UVETC001 Y
                WHERE Y.YMD BETWEEN &P_STDD_YM || '01'
                                AND TO_CHAR(LAST_DAY(ADD_MONTHS(TO_DATE(&P_STDD_YM, 'YYYYMM'), 1)), 'YYYYMMDD')
                  AND Y.HLDY_YN = 'N'
                  AND Y.BIWK_OFDY_YN = 'N'
            ) A,
            TB_UVDUM001 B
            WHERE A.NO = B.NO
        ) Y,
        (
            SELECT
                recp_date,
                SUM(loan_incr_amt) AS loan_incr_amt,
                SUM(loan_redu_amt) AS loan_redu_amt,
                SUM(incm_inte) AS incm_inte,
                SUM(sure_ocat) AS sure_ocat,
                SUM(sspn_arng_amt) AS sspn_arng_amt,
                SUM(mtgg_sure_ocat) AS mtgg_sure_ocat,
                SUM(mtgg_sure_arat) AS mtgg_sure_arat
            FROM TB_FNSTS071
            WHERE SUBSTR(recp_date, 1, 6) = &P_STDD_YM
              AND supt_objt_dvsn BETWEEN DECODE(&p_supt_objt_dusn, '5', '5', '1')
                                   AND DECODE(&p_supt_objt_dusn, '5', '7', '4')
              AND loan_subj_dvsn = &p_loan_subj_dvsn
              AND recv_bsns_dvsn = '40'
            GROUP BY recp_date
        ) Z
        WHERE X.NO + 3 = Y.NO
          AND X.RECP_DATE = Z.recp_date(+)
        ORDER BY X.RECP_DATE
    ) C,
    (
        SELECT
            CASE
                WHEN SUBSTR(slip_date, 1, 6) <> &P_STDD_YM THEN (
                    SELECT ymd
                    FROM TB_UVETC001
                    WHERE ymd LIKE &P_STDD_YM || '%'
                      AND hldy_yn = 'N'
                      AND biwk_ofdy_yn = 'N'
                      AND ROWNUM = 1
                )
                ELSE slip_date
            END AS slip_date,
            CASE
                WHEN SUBSTR(slip_date, 1, 6) <> &P_STDD_YM THEN
                    SUM(DECODE(DLGS_TYPE_CODE, 'FN005', -1 * amt, 'FS005', -1 * amt, 0)
                      + DECODE(DLGS_TYPE_CODE, 'FN014', amt, 'FS014', amt, 0))
                ELSE 0
            END AS result_amt
        FROM (
            SELECT
                slip_date,
                dlgs_type_code,
                SUM(
                    TO_NUMBER(SUBSTR(dlgs_data, 524, 15))
                    * DECODE(CNCL_YN, '1', 1, -1)
                    * TO_NUMBER(SUBSTR(dlgs_data, 554, 15))
                    * DECODE(cncl_yn, '1', 1, -1)
                ) AS amt
            FROM TB_UVERPHB1
            WHERE (
                slip_date = (
                    SELECT YMD
                    FROM TB_UVETC001
                    WHERE ymd LIKE &P_STDD_YM || '%'
                      AND hldy_yn = 'N'
                      AND biwk_ofdy_yn = 'N'
                      AND ROWNUM = 1
                )
                OR slip_date = (
                    SELECT YMD
                    FROM TB_UVETC001
                    WHERE ymd LIKE TO_CHAR(ADD_MONTHS(TO_DATE(&P_STDD_YM, 'YYYYMM'), -1), 'YYYYMM') || '%'
                      AND hldy_yn = 'N'
                      AND biwk_ofdy_yn = 'N'
                      AND ROWNUM = 1
                )
            )
              AND dlgs_type_code IN ('FN005', 'FS005', 'FN014', 'FS014')
              AND SUBSTR(dlgs_data, 6, 1) BETWEEN DECODE(&p_supt_objt_dusn, '5', '5', '1')
                                              AND DECODE(&p_supt_objt_dusn, '5', '7', '4')
              AND SUBSTR(dlgs_data, 7, 2) = &p_loan_subj_dvsn
            GROUP BY slip_date, dlgs_type_code
        )
        GROUP BY slip_date
    ) D
    WHERE A.recp_date = B.recp_date(+)
      AND A.recp_date = C.RECP_DATE_AFT3(+)
      AND A.recp_date = D.slip_date(+)
) D
WHERE A.recp_date = D.recp_date(+)
ORDER BY A.recp_date
/* @PROC_BODY_END @ */
