/** 새도약기금 매각 대상건 시연 — 고객 풀 SAS (SQL: querySample *_sas_step*.sql, API 로드) */

import { getSaedoyakDemoSql } from './api.js'

const DEMO_TABLES_STEP1 = [
  'TBL_WFGWFD0503',
  'TBL_WFGWFL0514',
  'TBL_WFGWFP0525',
]

const DEMO_TABLES_STEP2 = [
  ...DEMO_TABLES_STEP1,
  'TBL_WFGWFP0575',
  'TBL_WFGWFP0550',
  'TBL_WFGWFP0555',
  'TBL_WFGWFL0511',
  'TBL_CSSCM010',
]

const CLARIFY_EXPLANATION = `쿼리 작성 전에 조건을 두 가지만 확인할게요.

1. 「특수채권으로 등록된 건」 — 특수채권 정보에서 아직 종료되지 않은 건(종료일이 비어 있는 건)만 대상으로 볼까요?
2. 「연체등록일 2018-06-20 미만」 — 한 대출 건에 연체 이력이 여러 번 있을 수 있는데, 그 대출 건별로 연체등록일이 가장 늦은(최신) 한 건 기준으로 2018년 6월 20일 이전인지 보면 될까요?`

const STEP1_EXPLANATION =
  '확인해 주신 대로 종료일 없는 특수채권(SPFC_BOND_CSMT_DATE IS NULL)과 대출 건별 최신 연체등록일(ARRE_RGST_DATE) 조건을 반영했습니다. 개인 대출은 LOAN_SUBJ_DVSN_CODE = \'01\', 지원대상은 FNCG_SUPT_TRGT_DVSN_CODE IN (\'1\',\'2\',\'3\') 또는 (\'5\'이면서 SUPT_DVSN_CODE = \'1\')입니다. 특수채권·대출기본을 한 번 조인한 뒤 최신 연체와 맞추고, 차주별 FRST_LOAN_HNDL_AMT 합 5,000만 원 이하만 남겼습니다.'

const STEP2_EXPLANATION =
  '1차 대상에 개인회생(TBL_WFGWFP0575)·신용회복(TBL_WFGWFP0550)·고객(TBL_CSSCM010)·면책(TBL_WFGWFP0555)·보증인(TBL_WFGWFL0511) 정보를 LEFT JOIN 했습니다. 채무조정효력상실일_최종은 PRSN_RVVL_CSMT_DATE·LAPS_DATE 중 더 늦은 날짜입니다. 사망은 TBL_CSSCM010(DEAD_YN·DEAD_DATE) 기준, 면책은 EXLN_DTRM_DATE가 LOAN_DATE 이후인 경우, 보증인은 GURT_LBDB_EXMP_DATE가 없고 BORR_RLTS_DVSN_CODE = \'1\'인 경우 Y입니다.'

function norm(text) {
  return String(text ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

function lastAssistant(messages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') return messages[i]
  }
  return null
}

function isTurn1Query(q) {
  return q.includes('새도약') && (q.includes('매각') || q.includes('검토'))
}

function isTurn3Answer(q, prev) {
  if (q.includes('[clarification 답변]')) {
    const ids = (prev?.data?.clarifications || []).map((c) => c.id)
    if (ids.length && ids.some((id) => q.includes(id))) return true
  }
  return (
    (q.includes('종료') && q.includes('특수')) ||
    q.includes('종료 안') ||
    q.includes('맞아') ||
    q.includes('최신 연체')
  )
}

function isTurn5Query(q) {
  return (
    q.includes('매각 심사') ||
    q.includes('채무조정') ||
    (q.includes('사망') && q.includes('면책'))
  )
}

/**
 * @param {{ demoSqlKey?: string } & Record<string, unknown>} demoData
 */
export async function hydrateSaedoyakDemo(demoData) {
  if (!demoData?.demoSqlKey) return demoData
  try {
    const { sql } = await getSaedoyakDemoSql(demoData.demoSqlKey)
    const { demoSqlKey, ...rest } = demoData
    return { ...rest, sql }
  } catch (e) {
    return {
      ...demoData,
      sql: null,
      explanation: `${demoData.explanation || ''}\n\n(SQL 파일 로드 실패: ${e.message}. API(8000) 실행 여부 확인)`,
      confidence: 'low',
    }
  }
}

/**
 * 시연 스크립트 매칭 시 QueryResponse 골격 반환, 아니면 null.
 * sql 필드는 hydrateSaedoyakDemo 로 채웁니다.
 */
export function resolveSaedoyakDemoResponse(query, chatMessages) {
  const q = norm(query)
  const prev = lastAssistant(chatMessages)

  if (isTurn5Query(q) && prev?.data?.sql) {
    return {
      demoSqlKey: 'sas_step2',
      sql: null,
      explanation: STEP2_EXPLANATION,
      used_tables: DEMO_TABLES_STEP2,
      confidence: 'high',
      clarification_needed: null,
      clarifications: [],
      dialect: 'sas',
      schema_pool: 'customer',
      search_results: DEMO_TABLES_STEP2.map((table) => ({ table, score: 1 })),
      screen_maps: [],
      tokens: { input: 0, output: 0 },
    }
  }

  if (
    prev?.data &&
    !prev.data.sql &&
    (isTurn3Answer(q, prev) || q.includes('[clarification 답변]'))
  ) {
    return {
      demoSqlKey: 'sas_step1',
      sql: null,
      explanation: STEP1_EXPLANATION,
      used_tables: DEMO_TABLES_STEP1,
      confidence: 'high',
      clarification_needed: null,
      clarifications: [],
      dialect: 'sas',
      schema_pool: 'customer',
      search_results: DEMO_TABLES_STEP1.map((table) => ({ table, score: 1 })),
      screen_maps: [],
      tokens: { input: 0, output: 0 },
    }
  }

  if (isTurn1Query(q)) {
    return {
      sql: null,
      explanation: CLARIFY_EXPLANATION,
      used_tables: [],
      confidence: 'medium',
      clarification_needed: '조건 확인이 필요합니다. 아래 두 가지에 답해 주세요.',
      clarifications: [
        {
          id: 'spbd_active',
          question:
            '「특수채권으로 등록된 건」을 아직 종료되지 않은 건(종료일 없음)으로 볼까요?',
          kind: 'single',
          options: ['예, 종료일 없는 건만', '아니오, 등록만 되면 모두'],
        },
        {
          id: 'arre_latest',
          question:
            '연체등록일 2018-06-20 미만은 대출 건별 최신 연체등록일 기준으로 볼까요?',
          kind: 'single',
          options: ['예, 최신 연체등록일 기준', '아니오, 연체 이력 중 하나라도 해당되면'],
        },
      ],
      dialect: 'sas',
      schema_pool: 'customer',
      search_results: [],
      screen_maps: [],
      tokens: { input: 0, output: 0 },
    }
  }

  return null
}

export const SAEDOYAK_DEMO_USER_TURN1 = `새도약기금 매각 검토 대상 대출 목록이 필요합니다.

- 특수채권으로 등록된 건
- 개인 쪽이고, 신용 대출
- 연체등록일이 2018년 6월 20일 미만인 건
- 같은 차주 기준 대출금액 합이 5,000만 원 이하

우선 대출번호(대출ID·일련번호), 고객ID, 연체 시작·정리일, 건별·차주별 대출금액, 특수채권 등록일, 시효 관련 일자·사유, 대출일 정도만 뽑아 주세요.`

export const SAEDOYAK_DEMO_USER_TURN3 = `1번, 맞아요. 아직 종료 안 된 특수채권만이에요.
2번, 최신 연체등록일 기준으로 2018년 6월 20일 전이면 돼요.
개인·신용은 평소 매각 대상 뽑을 때 쓰는 그 범위 그대로면 됩니다.`

export const SAEDOYAK_DEMO_USER_TURN5 = `방금 결과에 매각 심사에 쓰는 항목 더 붙여 주세요.
- 채무조정 받다가 효력 없어진 날(개인회생·신용회복 각각, 그리고 둘 중 더 늦은 날)
- 사망 여부, 면책 받았는지(대출 이후 면책이면 해당)
- 보증인 중 권리 행사할 수 있는 사람 있는지 여부`
