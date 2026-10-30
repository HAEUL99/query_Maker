import { useState, useRef, useEffect } from 'react'
import './MockupPage.css'

const SCREEN_ID = 'SFNRCV767'
const SCREEN_NAME = '수납 마감자료 조회'

const RECEIPT_COLUMNS = [
  '영수일자',
  '대출발생_ERPHB', '대출발생', '대출발생_MOD',
  '대출상환_ERPHB', '대출상환', '대출상환_MOD',
  '수입이자_ERPHB', '수입이자', '수입이자_MOD',
]

const RECEIPT_ROWS = [
  ['20251103', '4,392,224,331',  '4,392,224,331',  '4,392,224,331',  '2,673,926,466',  '2,673,926,466',  '2,673,926,466',  '-9,387,269,364', '133,672,883',    '-9,387,269,364'],
  ['20251104', '3,489,703,250',  '3,489,703,250',  '3,489,703,250',  '2,132,161,797',  '2,132,161,797',  '2,132,161,797',  '139,667,901',    '139,667,901',    '139,667,901'   ],
  ['20251105', '3,449,350,000',  '3,449,350,000',  '3,449,350,000',  '3,273,177,480',  '3,405,414,692',  '3,273,177,480',  '2,066,205,233',  '2,276,802,866',  '2,066,205,233' ],
  ['20251106', '3,038,500,000',  '3,038,500,000',  '3,038,500,000',  '1,870,888,894',  '1,870,888,894',  '1,870,888,894',  '109,765,479',    '109,765,479',    '109,765,479'   ],
  ['20251107', '3,195,740,000',  '3,195,740,000',  '3,195,740,000',  '2,362,621,101',  '2,362,621,101',  '2,362,621,101',  '99,462,541',     '99,462,541',     '99,462,541'    ],
  ['20251110', '3,832,562,400',  '3,832,562,400',  '3,832,562,400',  '3,516,207,623',  '3,470,170,199',  '3,515,952,672',  '1,661,830,036',  '1,569,499,851',  '1,661,830,036' ],
  ['20251111', '3,851,759,500',  '3,851,759,500',  '3,851,759,500',  '1,985,166,145',  '1,985,166,145',  '1,985,166,145',  '146,256,385',    '146,256,385',    '146,256,385'   ],
  ['20251112', '2,616,300,000',  '2,616,300,000',  '2,616,300,000',  '1,670,373,119',  '1,670,373,119',  '1,670,373,119',  '78,064,153',     '78,064,153',     '78,064,153'    ],
  ['20251113', '3,148,459,600',  '3,148,459,600',  '3,148,459,600',  '2,239,481,163',  '2,153,026,424',  '2,239,481,163',  '260,819,360',    '142,551,912',    '260,819,360'   ],
  ['20251114', '3,322,600,500',  '3,322,600,500',  '3,322,600,500',  '2,089,089,309',  '2,089,089,309',  '2,089,089,309',  '86,712,282',     '86,745,455',     '86,745,455'    ],
  ['20251117', '4,667,063,057',  '4,667,063,057',  '4,667,063,057',  '3,444,722,844',  '3,572,360,193',  '3,444,722,844',  '1,979,265,250',  '2,156,891,710',  '1,979,265,250' ],
  ['20251118', '3,962,835,000',  '3,962,835,000',  '3,962,835,000',  '1,819,471,995',  '1,819,471,995',  '1,819,471,995',  '78,080,175',     '78,080,175',     '78,080,175'    ],
  ['20251119', '3,914,100,000',  '3,914,100,000',  '3,914,100,000',  '2,169,107,183',  '2,169,107,183',  '2,169,107,183',  '101,546,236',    '101,546,236',    '101,546,236'   ],
  ['20251120', '3,137,128,870',  '3,137,128,870',  '3,137,128,870',  '3,546,449,435',  '3,564,260,674',  '3,546,449,435',  '2,342,451,808',  '2,379,207,201',  '2,342,451,808' ],
  ['20251121', '3,292,136,942',  '3,292,136,942',  '3,292,136,942',  '2,484,184,252',  '2,484,184,252',  '2,484,184,252',  '145,899,723',    '145,899,723',    '145,899,723'   ],
  ['20251124', '5,695,119,539',  '5,695,119,539',  '5,695,119,539',  '2,591,194,198',  '2,591,194,198',  '2,591,194,198',  '161,645,420',    '161,645,420',    '161,645,420'   ],
  ['20251125', '3,726,486,824',  '3,726,486,824',  '3,726,486,824',  '5,229,942,019',  '5,338,991,138',  '5,229,942,019',  '4,496,825,590',  '4,652,555,081',  '4,496,825,590' ],
  ['20251126', '3,643,438,024',  '3,643,438,024',  '3,643,438,024',  '3,554,579,037',  '3,556,831,186',  '3,556,831,186',  '312,340,760',    '313,291,213',    '313,291,213'   ],
  ['20251127', '0',              '3,325,720,000',  '3,325,720,000',  '10,650,000',     '2,060,806,276',  '2,060,806,276',  '509,493',        '330,001,004',    '330,001,004'   ],
  ['20251128', '0',              '1,914,800,000',  '1,914,800,000',  '258,763,707',    '1,532,472,404',  '1,786,970,111',  '371,296,674',    '113,070,605',    '483,181,949'   ],
]

const RECEIPT_TOTAL = [
  '합 계',
  '66,375,507,837', '71,616,027,837', '71,616,027,837',
  '48,922,157,767', '52,502,517,645', '52,502,517,645',
  '5,251,375,135',  '15,214,677,794', '5,693,735,547',
]

const SUSPENSE_COLUMNS = ['영수일자', '가수금발생_ERP', '가수금발생', '가수금발생_MOD']

const SUSPENSE_ROWS = [
  ['20251103', '9,660,967,100',   '401,119,173',   '401,119,173'  ],
  ['20251104', '4,887,345,833',   '116,345,870',   '116,345,870'  ],
  ['20251105', '5,112,736,820',   '371,522,120',   '365,280,781'  ],
  ['20251106', '5,273,913,611',   '113,843,756',   '113,843,756'  ],
  ['20251107', '7,378,704,550',   '64,707,280',    '64,707,280'   ],
  ['20251110', '6,093,753,975',   '230,090,745',   '232,071,863'  ],
  ['20251111', '6,993,859,083',   '256,246,433',   '256,246,433'  ],
  ['20251112', '4,983,715,411',   '279,532,093',   '279,532,093'  ],
  ['20251113', '4,241,053,367',   '171,337,952',   '175,598,173'  ],
  ['20251114', '9,059,088,691',   '171,765,639',   '171,765,639'  ],
  ['20251117', '6,982,281,724',   '564,923,207',   '561,920,075'  ],
  ['20251118', '7,822,570,792',   '193,443,093',   '193,443,093'  ],
  ['20251119', '5,798,329,819',   '489,662,579',   '489,662,579'  ],
  ['20251120', '7,636,776,982',   '156,207,631',   '155,750,761'  ],
  ['20251121', '5,039,335,105',   '107,041,143',   '107,041,143'  ],
  ['20251124', '8,693,217,560',   '236,489,831',   '236,489,831'  ],
  ['20251125', '8,219,560,040',   '441,669,324',   '428,266,318'  ],
  ['20251126', '6,313,814,116',   '1,052,270,660', '1,052,270,660'],
  ['20251127', '8,784,221,003',   '1,915,731,578', '1,915,731,578'],
  ['20251128', '16,192,640,509',  '165,373,101',   '182,236,109'  ],
]

const SUSPENSE_TOTAL = ['합 계', '145,167,886,091', '7,499,323,208', '7,499,323,208']

function isNegative(val) {
  if (typeof val !== 'string') return false
  return val.trim().startsWith('-')
}

function formatDate(val) {
  if (/^\d{8}$/.test(val.trim())) {
    const s = val.trim()
    return `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`
  }
  return val
}

const API_BASE = 'http://localhost:8000'

const STATUS_LABEL = {
  confirmed: '확정',
  low_confidence: '저신뢰',
  unmatched: '미매칭',
  no_dna_schema: 'DNA 없음',
}

export default function MockupPage() {
  const [activeTab, setActiveTab] = useState('receipt')
  const [suptObjt, setSuptObjt] = useState('개인')
  const [loanSubj, setLoanSubj] = useState('신용')

  // 미니 챗봇 상태
  const [chatOpen, setChatOpen] = useState(false)
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef(null)

  // DNA 매핑 상태
  const [mappingOpen, setMappingOpen] = useState(false)
  const [mappingLoading, setMappingLoading] = useState(false)
  const [mappingResults, setMappingResults] = useState([])
  const [mappingMeta, setMappingMeta] = useState({ dna_table_count: 0, openai_used: false })
  const [mappingError, setMappingError] = useState('')

  const columns = activeTab === 'receipt' ? RECEIPT_COLUMNS : SUSPENSE_COLUMNS
  const rows    = activeTab === 'receipt' ? RECEIPT_ROWS    : SUSPENSE_ROWS
  const total   = activeTab === 'receipt' ? RECEIPT_TOTAL   : SUSPENSE_TOTAL

  useEffect(() => {
    if (chatOpen && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatMessages, chatOpen])

  async function sendChatMessage() {
    const question = chatInput.trim()
    if (!question || chatLoading) return

    const userMsg = { role: 'user', content: question }
    const newMessages = [...chatMessages, userMsg]
    setChatMessages(newMessages)
    setChatInput('')
    setChatLoading(true)

    try {
      const history = chatMessages.map(m => ({ role: m.role, content: m.content }))
      const res = await fetch(`${API_BASE}/api/screen-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          screen_id: SCREEN_ID,
          screen_name: SCREEN_NAME,
          active_tab: activeTab === 'receipt' ? '수납내역' : '가수금',
          filters: {
            기준년월: '2025년 11월',
            지원대상구분: suptObjt,
            대출구분: loanSubj,
          },
          columns,
          rows,
          total_row: total,
          question,
          history,
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      setChatMessages(prev => [...prev, { role: 'assistant', content: data.answer }])
    } catch (err) {
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', content: `오류: ${err.message}` },
      ])
    } finally {
      setChatLoading(false)
    }
  }

  function handleChatKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendChatMessage()
    }
  }

  function clearChat() {
    setChatMessages([])
    setChatInput('')
  }

  async function runDnaMapping() {
    setMappingOpen(true)
    setMappingLoading(true)
    setMappingError('')
    setMappingResults([])

    // 현재 화면 헤더(한글명)를 HFSR 컬럼으로 전송. 날짜 키 컬럼(영수일자)은 제외.
    const hfsr_cols = columns
      .filter(col => col !== '영수일자')
      .map(col => ({ col_name: col, col_ko: col }))

    try {
      const res = await fetch(`${API_BASE}/api/screen-mapping`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hfsr_cols }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      setMappingResults(data.mappings || [])
      setMappingMeta({
        dna_table_count: data.dna_table_count || 0,
        openai_used: data.openai_used || false,
      })
    } catch (err) {
      setMappingError(err.message)
    } finally {
      setMappingLoading(false)
    }
  }

  return (
    <div className="mockup-page">
      <div className="mockup-titlebar">
        <span className="mockup-title-text">수납 마감자료 조회</span>
        <span className="mockup-screen-id">SFNRCV767</span>
      </div>

      <div className="mockup-search-area">
        <div className="mockup-search-row">
          <label className="mockup-search-label">기준년월</label>
          <input
            className="mockup-search-input"
            type="text"
            defaultValue="2025년 11월"
            readOnly
          />
          <label className="mockup-search-label">지원대상구분</label>
          <select
            className="mockup-search-select"
            value={suptObjt}
            onChange={(e) => setSuptObjt(e.target.value)}
          >
            <option>개인</option>
            <option>기업</option>
            <option>FP</option>
          </select>
          <label className="mockup-search-label">대출구분</label>
          <select
            className="mockup-search-select"
            value={loanSubj}
            onChange={(e) => setLoanSubj(e.target.value)}
          >
            <option>신용</option>
            <option>담보</option>
          </select>
          <button className="mockup-search-btn" type="button">조회</button>
          <button
            className="mockup-mapping-btn"
            type="button"
            onClick={runDnaMapping}
            title="현재 화면 컬럼을 DNA 풀과 매핑"
          >
            DNA 매핑
          </button>
        </div>
      </div>

      <div className="mockup-tabs">
        <button
          type="button"
          className={`mockup-tab-btn${activeTab === 'receipt' ? ' active' : ''}`}
          onClick={() => setActiveTab('receipt')}
        >
          수납내역
        </button>
        <button
          type="button"
          className={`mockup-tab-btn${activeTab === 'suspense' ? ' active' : ''}`}
          onClick={() => setActiveTab('suspense')}
        >
          가수금
        </button>
      </div>

      <div className="mockup-grid-wrap">
        <table className="mockup-grid">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className={[
                      j === 0 ? 'cell-date' : 'cell-num',
                      isNegative(cell) ? 'negative' : '',
                    ].filter(Boolean).join(' ')}
                  >
                    {j === 0 ? formatDate(cell) : cell}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="total-row">
              {total.map((cell, j) => (
                <td
                  key={j}
                  className={[
                    j === 0 ? 'cell-date' : 'cell-num',
                    isNegative(cell) ? 'negative' : '',
                  ].filter(Boolean).join(' ')}
                >
                  {cell}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mockup-footer">
        총 <strong>{rows.length}</strong>건 &nbsp;|&nbsp; 기준: 2025년 11월 &nbsp;|&nbsp; 지원대상: {suptObjt} &nbsp;/&nbsp; 대출구분: {loanSubj}
      </div>

      {/* ── DNA 매핑 결과 패널 ── */}
      {mappingOpen && (
        <div className="dna-map-overlay" onClick={() => setMappingOpen(false)}>
          <div className="dna-map-panel" onClick={e => e.stopPropagation()}>
            <div className="dna-map-header">
              <span>HFSR → DNA 컬럼 매핑</span>
              <button
                type="button"
                className="dna-map-close"
                onClick={() => setMappingOpen(false)}
              >
                ✕
              </button>
            </div>

            <div className="dna-map-body">
              {mappingLoading && (
                <div className="dna-map-loading">
                  DNA 풀과 매핑 중입니다…
                </div>
              )}

              {!mappingLoading && mappingError && (
                <div className="dna-map-error">
                  오류: {mappingError}
                </div>
              )}

              {!mappingLoading && !mappingError && (
                <>
                  <div className="dna-map-meta">
                    DNA 테이블 {mappingMeta.dna_table_count}개 대상
                    {mappingMeta.openai_used && (
                      <span className="dna-map-openai-badge">OpenAI 판정 사용</span>
                    )}
                  </div>

                  <table className="dna-map-table">
                    <thead>
                      <tr>
                        <th>HFSR 컬럼</th>
                        <th>상태</th>
                        <th>DNA 테이블</th>
                        <th>DNA 컬럼</th>
                        <th>유사도</th>
                        <th>방식</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mappingResults.map((m, i) => (
                        <tr key={i} className={`dna-row dna-row--${m.status}`}>
                          <td>{m.hfsr_ko || m.hfsr_col}</td>
                          <td>
                            <span className={`dna-status dna-status--${m.status}`}>
                              {STATUS_LABEL[m.status] || m.status}
                            </span>
                          </td>
                          <td>{m.dna_table || '-'}</td>
                          <td>
                            {m.dna_ko ? `${m.dna_ko} (${m.dna_col})` : '-'}
                            {m.status === 'low_confidence' && m.candidates?.length > 1 && (
                              <div className="dna-candidates">
                                후보: {m.candidates.slice(0, 3).map(c => `${c.col_ko}(${c.score})`).join(', ')}
                              </div>
                            )}
                          </td>
                          <td className="dna-score">{m.score > 0 ? m.score.toFixed(2) : '-'}</td>
                          <td>
                            {m.method === 'openai' && <span className="dna-method dna-method--openai">GPT</span>}
                            {m.method === 'edit_distance' && <span className="dna-method">편집거리</span>}
                            {m.method === 'none' && '-'}
                          </td>
                        </tr>
                      ))}
                      {mappingResults.length === 0 && (
                        <tr>
                          <td colSpan={6} className="dna-map-empty">매핑 결과가 없습니다.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── 플로팅 챗봇 버튼 ── */}
      <button
        className="screen-chat-fab"
        type="button"
        title="화면 데이터 AI 질문"
        onClick={() => setChatOpen(o => !o)}
      >
        {chatOpen ? '✕' : '💬'}
      </button>

      {/* ── 미니 챗봇 창 ── */}
      {chatOpen && (
        <div className="screen-chat-window">
          <div className="screen-chat-header">
            <span>화면 데이터 AI 질문</span>
            <div className="screen-chat-header-actions">
              <button type="button" className="screen-chat-clear-btn" onClick={clearChat} title="대화 초기화">
                초기화
              </button>
              <button type="button" className="screen-chat-close-btn" onClick={() => setChatOpen(false)}>
                ✕
              </button>
            </div>
          </div>

          <div className="screen-chat-context-badge">
            {activeTab === 'receipt' ? '수납내역' : '가수금'} · {suptObjt} · {loanSubj} · {rows.length}건
          </div>

          <div className="screen-chat-messages">
            {chatMessages.length === 0 && (
              <div className="screen-chat-empty">
                현재 화면 데이터를 기반으로 질문하세요.<br />
                <small>예: 합계 대출발생 금액은 얼마인가요?</small>
              </div>
            )}
            {chatMessages.map((msg, i) => (
              <div key={i} className={`screen-chat-msg screen-chat-msg--${msg.role}`}>
                <div className="screen-chat-bubble">{msg.content}</div>
              </div>
            ))}
            {chatLoading && (
              <div className="screen-chat-msg screen-chat-msg--assistant">
                <div className="screen-chat-bubble screen-chat-typing">
                  <span /><span /><span />
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="screen-chat-input-row">
            <textarea
              className="screen-chat-input"
              rows={2}
              placeholder="질문을 입력하세요… (Enter: 전송, Shift+Enter: 줄바꿈)"
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={handleChatKeyDown}
              disabled={chatLoading}
            />
            <button
              type="button"
              className="screen-chat-send-btn"
              onClick={sendChatMessage}
              disabled={chatLoading || !chatInput.trim()}
            >
              전송
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
