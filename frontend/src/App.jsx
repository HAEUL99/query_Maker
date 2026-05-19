import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BASE,
  adminStatsSummary,
  getStats,
  getTables,
  loginAdmin,
  querySQL,
  resetIndex,
  uploadFiles,
} from './api.js'
import './App.css'
import { addFavorite, loadFavorites, removeFavorite } from './favoritesStorage.js'

const KEYWORDS = new Set(
  [
    'SELECT',
    'FROM',
    'WHERE',
    'JOIN',
    'INNER',
    'LEFT',
    'RIGHT',
    'OUTER',
    'FULL',
    'CROSS',
    'ON',
    'AND',
    'OR',
    'NOT',
    'AS',
    'GROUP',
    'BY',
    'ORDER',
    'HAVING',
    'UNION',
    'ALL',
    'DISTINCT',
    'CASE',
    'WHEN',
    'THEN',
    'ELSE',
    'END',
    'NULL',
    'IN',
    'IS',
    'LIKE',
    'BETWEEN',
    'EXISTS',
    'WITH',
    'ASC',
    'DESC',
    'LIMIT',
    'OFFSET',
    'FETCH',
    'FIRST',
    'ROWS',
    'ONLY',
  ].map((s) => s.toUpperCase()),
)

const FUNCTIONS = new Set(
  [
    'SUM',
    'COUNT',
    'AVG',
    'MAX',
    'MIN',
    'NVL',
    'TO_DATE',
    'TO_CHAR',
    'TRUNC',
    'SUBSTR',
    'LENGTH',
    'DECODE',
    'COALESCE',
    'ROUND',
    'ROWNUM',
    'SYSDATE',
    'INSTR',
    'LPAD',
    'RPAD',
    'REPLACE',
    'REGEXP_REPLACE',
    'TRIM',
    'INITCAP',
    'UPPER',
    'LOWER',
    'ABS',
    'MOD',
    'POWER',
    'EXP',
    'LN',
    'NULLIF',
    'GREATEST',
    'LEAST',
    'PROC',
    'SQL',
    'CREATE',
    'TABLE',
    'DROP',
    'ALTER',
    'INDEX',
    'VIEW',
    'MERGE',
    'INSERT',
    'UPDATE',
    'DELETE',
  ].map((s) => s.toUpperCase()),
)

function highlightSqlParts(sql) {
  if (!sql) return []
  const parts = []
  let i = 0
  const s = sql
  while (i < s.length) {
    const c = s[i]
    if (c === "'" || c === '"') {
      const quote = c
      let j = i + 1
      while (j < s.length) {
        if (s[j] === quote && s[j - 1] !== '\\') break
        j++
      }
      if (j < s.length) j++
      parts.push({ type: 'string', text: s.slice(i, j) })
      i = j
      continue
    }
    if (/\s/.test(c)) {
      let j = i
      while (j < s.length && /\s/.test(s[j])) j++
      parts.push({ type: 'ws', text: s.slice(i, j) })
      i = j
      continue
    }
    if (/[0-9]/.test(c)) {
      let j = i
      while (j < s.length && /[0-9.]/.test(s[j])) j++
      parts.push({ type: 'number', text: s.slice(i, j) })
      i = j
      continue
    }
    if (/[a-zA-Z_]/.test(c) || /[\u0080-\uFFFF]/.test(c)) {
      let j = i
      while (
        j < s.length &&
        (/[a-zA-Z0-9_]/.test(s[j]) || /[\u0080-\uFFFF]/.test(s[j]))
      )
        j++
      const word = s.slice(i, j)
      const upper = word.toUpperCase()
      if (KEYWORDS.has(upper)) parts.push({ type: 'keyword', text: word })
      else if (FUNCTIONS.has(upper))
        parts.push({ type: 'function', text: word })
      else parts.push({ type: 'ident', text: word })
      i = j
      continue
    }
    parts.push({ type: 'punct', text: c })
    i++
  }
  return parts
}

function SqlHighlighted({ sql }) {
  const parts = useMemo(() => highlightSqlParts(sql), [sql])
  return (
    <pre className="sql-pre">
      <code>
        {parts.map((p, idx) => (
          <span key={idx} className={`sql-tok sql-${p.type}`}>
            {p.text}
          </span>
        ))}
      </code>
    </pre>
  )
}

function SqlBlock({ sql, onCopy }) {
  return (
    <div className="sql-block-wrap">
      <button
        type="button"
        className="sql-copy-corner"
        onClick={onCopy}
        aria-label="SQL 복사"
      >
        복사
      </button>
      <SqlHighlighted sql={sql} />
    </div>
  )
}

function IconHexLogo({ className }) {
  return (
    <svg
      className={className}
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M12 2L20 6.5V17.5L12 22L4 17.5V6.5L12 2Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconUpload({ className }) {
  return (
    <svg
      className={className}
      width="34"
      height="34"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M4 16.004V17a3 3 0 003 3h10a3 3 0 003-3v-1M8 8l4-4m0 0l4 4m-4-4v12"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconEmpty({ className }) {
  return (
    <svg
      className={className}
      width="72"
      height="72"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M4 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V6z"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinejoin="round"
      />
      <path
        d="M9 12h6M9 16h4"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
    </svg>
  )
}

function domainBadgeClass(domain) {
  const d = (domain || '').trim()
  if (d === '영업') return 'domain-sales'
  if (d === '재무') return 'domain-finance'
  if (d === '인사') return 'domain-hr'
  return 'domain-other'
}

function confidenceClass(c) {
  const v = (c || '').toLowerCase()
  if (v === 'high') return 'conf-high'
  if (v === 'medium') return 'conf-medium'
  if (v === 'low') return 'conf-low'
  return 'conf-muted'
}

function nextId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/** 결과 카드의 favoriteId가 현재 즐겨찾기 목록과 연결되는지 */
function isFavoriteLinked(favoritesList, favoriteId) {
  return Boolean(
    favoriteId && favoritesList.some((f) => f.id === favoriteId),
  )
}

const ADMIN_TOKEN_KEY = 'schema-query-admin-token'

export default function App() {
  const [tables, setTables] = useState([])
  const [selectedTable, setSelectedTable] = useState(null)
  const [results, setResults] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [stats, setStats] = useState(null)
  const [queryText, setQueryText] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [sidebarTab, setSidebarTab] = useState('query')
  const [tableCategory, setTableCategory] = useState('전체')

  const [adminToken, setAdminToken] = useState(() =>
    typeof localStorage !== 'undefined'
      ? localStorage.getItem(ADMIN_TOKEN_KEY) || ''
      : '',
  )
  const [adminPwd, setAdminPwd] = useState('')
  const [adminLoginErr, setAdminLoginErr] = useState('')
  const [adminPreviewPool, setAdminPreviewPool] = useState('customer')
  const [uploadTargetPool, setUploadTargetPool] = useState('customer')
  const [oracleProfile, setOracleProfile] = useState('admin_dml')
  const [adminQueryText, setAdminQueryText] = useState('')
  const [adminResults, setAdminResults] = useState([])
  const [isAdminQueryLoading, setIsAdminQueryLoading] = useState(false)
  const [adminSummary, setAdminSummary] = useState(null)
  const [favorites, setFavorites] = useState(() => loadFavorites())

  const persistAdminToken = useCallback((t) => {
    setAdminToken(t)
    if (t) localStorage.setItem(ADMIN_TOKEN_KEY, t)
    else localStorage.removeItem(ADMIN_TOKEN_KEY)
  }, [])

  const loadTables = useCallback(async () => {
    try {
      if (sidebarTab === 'query') {
        const data = await getTables(undefined, 'customer', null)
        setTables(data.tables || [])
        return
      }
      if (adminPreviewPool === 'customer') {
        const data = await getTables(undefined, 'customer', null)
        setTables(data.tables || [])
        return
      }
      if (!adminToken) {
        setTables([])
        return
      }
      const data = await getTables(undefined, 'admin', adminToken)
      setTables(data.tables || [])
    } catch (e) {
      console.error(e)
      setTables([])
    }
  }, [sidebarTab, adminToken, adminPreviewPool])

  const loadStats = useCallback(async () => {
    try {
      if (sidebarTab === 'query') {
        const s = await getStats('customer', null)
        setStats(s)
        setAdminSummary(null)
      } else if (adminToken) {
        const sum = await adminStatsSummary(adminToken)
        setAdminSummary(sum)
        const s = await getStats('customer', null)
        setStats(s)
      }
    } catch (e) {
      console.error(e)
    }
  }, [sidebarTab, adminToken])

  useEffect(() => {
    loadTables()
  }, [loadTables])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  useEffect(() => {
    if (sidebarTab === 'admin') {
      setTableCategory('전체')
    }
  }, [adminPreviewPool, sidebarTab])

  const tableDomainOptions = useMemo(() => {
    const set = new Set()
    for (const t of tables) {
      const d = (t.domain || '').trim() || '기타'
      set.add(d)
    }
    const list = Array.from(set)
    const priority = ['영업', '재무', '인사', '기타']
    list.sort((a, b) => {
      const ia = priority.indexOf(a)
      const ib = priority.indexOf(b)
      if (ia !== -1 && ib !== -1) return ia - ib
      if (ia !== -1) return -1
      if (ib !== -1) return 1
      return a.localeCompare(b, 'ko')
    })
    return list
  }, [tables])

  const filteredTables = useMemo(() => {
    if (tableCategory === '전체') return tables
    return tables.filter((t) => {
      const d = (t.domain || '').trim() || '기타'
      return d === tableCategory
    })
  }, [tables, tableCategory])

  useEffect(() => {
    if (
      tableCategory !== '전체' &&
      !tableDomainOptions.includes(tableCategory)
    ) {
      setTableCategory('전체')
    }
  }, [tableDomainOptions, tableCategory])

  useEffect(() => {
    setSelectedTable((prev) => {
      if (!prev) return null
      const stillVisible = filteredTables.some(
        (t) => t.table_name === prev.table_name,
      )
      return stillVisible ? prev : null
    })
  }, [filteredTables])

  useEffect(() => {
    if (!selectedTable?.table_name) return
    const pool = sidebarTab === 'query' ? 'customer' : adminPreviewPool
    const token = pool === 'admin' ? adminToken : null
    let cancelled = false
    ;(async () => {
      try {
        const headers = {}
        if (token) headers.Authorization = `Bearer ${token}`
        const res = await fetch(
          `${BASE}/api/tables/${encodeURIComponent(selectedTable.table_name)}?schema_pool=${encodeURIComponent(pool)}`,
          { headers },
        )
        if (!res.ok) {
          const text = await res.text()
          throw new Error(text || `HTTP ${res.status}`)
        }
        const detail = await res.json()
        if (cancelled) return
        setSelectedTable((prev) =>
          prev && prev.table_name === detail.table_name
            ? { ...prev, columns: detail.columns || [], columnsError: null }
            : prev,
        )
      } catch (e) {
        if (cancelled) return
        setSelectedTable((prev) =>
          prev
            ? {
                ...prev,
                columns: [],
                columnsError: e.message || String(e),
              }
            : null,
        )
      }
    })()
    return () => {
      cancelled = true
    }
  }, [
    selectedTable?.table_name,
    sidebarTab,
    adminPreviewPool,
    adminToken,
  ])

  const handleRowClick = (row) => {
    setSelectedTable({
      table_name: row.table_name,
      korean_name: row.korean_name || '',
      domain: row.domain || '',
      columns: null,
      columnsError: null,
    })
  }

  const handleDrop = async (e) => {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files || []).filter((f) =>
      f.name.toLowerCase().endsWith('.xlsx'),
    )
    if (!files.length) return
    await runUpload(files)
  }

  const handleFileInput = async (e) => {
    const files = Array.from(e.target.files || []).filter((f) =>
      f.name.toLowerCase().endsWith('.xlsx'),
    )
    e.target.value = ''
    if (!files.length) return
    await runUpload(files)
  }

  const runUpload = async (files) => {
    if (!adminToken) return
    setIsUploading(true)
    try {
      await uploadFiles(files, uploadTargetPool, adminToken)
      await loadTables()
      await loadStats()
      alert(
        `인덱싱 완료 (${uploadTargetPool === 'customer' ? '고객' : '관리자'} 풀)`,
      )
    } catch (err) {
      alert(err.message || String(err))
    } finally {
      setIsUploading(false)
    }
  }

  const executeCustomerQuery = useCallback(
    async (rawText, opts) => {
      const favoriteId = opts?.favoriteId
      const q = String(rawText ?? '').trim()
      if (!q) return
      if (stats !== null && stats.total_tables === 0) {
        window.alert(
          [
            '고객 풀에 인덱싱된 테이블이 없어 질의를 실행할 수 없습니다.',
            '',
            '샘플 정의서를 넣으려면 터미널에서(query-maker 폴더):',
            '  python scripts/create_sample_data.py',
            '  PYTHONPATH=. python scripts/index.py --dir data/excel/sample_customer/ --pool customer --reset',
            '',
            '고객+관리자 풀 한 번에: PYTHONPATH=. python scripts/bootstrap_demo_index.py',
          ].join('\n'),
        )
        return
      }
      setQueryText(q)
      setIsLoading(true)
      try {
        const data = await querySQL(
          q,
          'sas',
          undefined,
          undefined,
          { schema_pool: 'customer' },
        )
        setResults((prev) => [
          {
            id: nextId(),
            query: q,
            data,
            error: null,
            source: 'customer',
            favoriteId,
          },
          ...prev,
        ])
      } catch (e) {
        setResults((prev) => [
          {
            id: nextId(),
            query: q,
            data: null,
            error: e.message || String(e),
            source: 'customer',
            favoriteId,
          },
          ...prev,
        ])
      } finally {
        setIsLoading(false)
      }
    },
    [stats],
  )

  const submitQuery = async () => {
    await executeCustomerQuery(queryText, {})
  }

  const executeAdminQuery = useCallback(
    async (rawText, opts) => {
      const favoriteId = opts?.favoriteId
      const q = String(rawText ?? '').trim()
      if (!q || !adminToken) return
      if (
        adminSummary !== null &&
        (adminSummary.admin?.total ?? 0) === 0
      ) {
        window.alert(
          [
            '관리자 풀에 인덱싱된 테이블이 없어 질의를 실행할 수 없습니다.',
            '',
            '샘플 정의서를 넣으려면 터미널에서(query-maker 폴더):',
            '  python scripts/create_sample_data.py',
            '  PYTHONPATH=. python scripts/index.py --dir data/excel/sample_admin/ --pool admin --reset',
            '',
            '고객+관리자 풀 한 번에: PYTHONPATH=. python scripts/bootstrap_demo_index.py',
          ].join('\n'),
        )
        return
      }
      setAdminQueryText(q)
      setIsAdminQueryLoading(true)
      try {
        const data = await querySQL(
          q,
          'oracle',
          undefined,
          undefined,
          {
            schema_pool: 'admin',
            oracle_profile: oracleProfile,
            token: adminToken,
          },
        )
        setAdminResults((prev) => [
          {
            id: nextId(),
            query: q,
            data,
            error: null,
            source: 'admin',
            favoriteId,
          },
          ...prev,
        ])
      } catch (e) {
        setAdminResults((prev) => [
          {
            id: nextId(),
            query: q,
            data: null,
            error: e.message || String(e),
            source: 'admin',
            favoriteId,
          },
          ...prev,
        ])
      } finally {
        setIsAdminQueryLoading(false)
      }
    },
    [adminToken, adminSummary, oracleProfile],
  )

  const submitAdminQuery = async () => {
    await executeAdminQuery(adminQueryText, {})
  }

  const handleAddFavorite = useCallback((pool, naturalLanguageQuery) => {
    const q = String(naturalLanguageQuery ?? '').trim()
    if (!q) return
    const name = window.prompt('즐겨찾기 이름을 입력하세요.', '')
    if (name === null) return
    const trimmed = name.trim()
    if (!trimmed) {
      window.alert('이름을 입력해 주세요.')
      return
    }
    setFavorites(addFavorite(pool, trimmed, q))
  }, [])

  const handleFavoriteStarCustomer = useCallback(
    (item) => {
      const list = favorites.customer
      const linked =
        item.favoriteId &&
        list.some((f) => f.id === item.favoriteId)
      if (linked) {
        if (!window.confirm('즐겨찾기를 해제하시겠습니까?')) return
        setFavorites(removeFavorite('customer', item.favoriteId))
        setResults((prev) =>
          prev.map((r) =>
            r.id === item.id ? { ...r, favoriteId: undefined } : r,
          ),
        )
        return
      }
      if (!item.data?.sql) return
      handleAddFavorite('customer', item.query)
    },
    [favorites.customer, handleAddFavorite],
  )

  const handleFavoriteStarAdmin = useCallback(
    (item) => {
      const list = favorites.admin
      const linked =
        item.favoriteId &&
        list.some((f) => f.id === item.favoriteId)
      if (linked) {
        if (!window.confirm('즐겨찾기를 해제하시겠습니까?')) return
        setFavorites(removeFavorite('admin', item.favoriteId))
        setAdminResults((prev) =>
          prev.map((r) =>
            r.id === item.id ? { ...r, favoriteId: undefined } : r,
          ),
        )
        return
      }
      if (!item.data?.sql) return
      handleAddFavorite('admin', item.query)
    },
    [favorites.admin, handleAddFavorite],
  )

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      submitQuery()
    }
  }

  const onAdminKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      submitAdminQuery()
    }
  }

  const handleAdminLogin = async (e) => {
    e.preventDefault()
    setAdminLoginErr('')
    try {
      const r = await loginAdmin(adminPwd)
      persistAdminToken(r.access_token)
      setAdminPwd('')
    } catch (err) {
      setAdminLoginErr(err.message || String(err))
    }
  }

  const handleAdminLogout = () => {
    persistAdminToken('')
    setAdminPwd('')
    setAdminLoginErr('')
    setAdminResults([])
  }

  const handleResetPool = async (pool) => {
    if (!adminToken || !confirm(`정말 ${pool} 풀 인덱스를 비울까요?`)) return
    try {
      await resetIndex(adminToken, pool)
      await loadTables()
      await loadStats()
    } catch (err) {
      alert(err.message || String(err))
    }
  }

  const domainSummary =
    stats?.by_domain &&
    Object.entries(stats.by_domain)
      .map(([k, v]) => `${k || '—'} ${v}개`)
      .join(', ')

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-scroll">
          <div className="logo-row">
            <IconHexLogo className="logo-icon" />
            <span className="logo-text">Schema·Query</span>
          </div>

          <div
            className="sidebar-tabs"
            role="tablist"
            aria-label="사이드 메뉴"
          >
            <button
              type="button"
              role="tab"
              aria-selected={sidebarTab === 'query'}
              className={`sidebar-tab ${sidebarTab === 'query' ? 'active' : ''}`}
              onClick={() => setSidebarTab('query')}
            >
              질의
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={sidebarTab === 'admin'}
              className={`sidebar-tab ${sidebarTab === 'admin' ? 'active' : ''}`}
              onClick={() => setSidebarTab('admin')}
            >
              관리자
            </button>
          </div>

          {sidebarTab === 'query' && (
            <div className="sidebar-section flex-grow no-border">
              <div className="section-label">테이블</div>
              <label className="table-category-label" htmlFor="table-category">
                카테고리
              </label>
              <select
                id="table-category"
                className="table-category-select"
                value={tableCategory}
                onChange={(e) => setTableCategory(e.target.value)}
                disabled={tables.length === 0}
              >
                <option value="전체">전체</option>
                {tableDomainOptions.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <div className="table-list">
                {tables.length === 0 && (
                  <p className="muted small">
                    인덱싱된 테이블이 없습니다. 관리자 탭에서 고객 풀용
                    정의서를 올려 주세요.
                  </p>
                )}
                {tables.length > 0 && filteredTables.length === 0 && (
                  <p className="muted small">
                    이 카테고리에 해당하는 테이블이 없습니다.
                  </p>
                )}
                {filteredTables.map((row) => (
                  <button
                    key={row.table_name}
                    type="button"
                    className={`table-row ${selectedTable?.table_name === row.table_name ? 'selected' : ''}`}
                    onClick={() => handleRowClick(row)}
                  >
                    <div className="table-row-top">
                      <span className="table-name">{row.table_name}</span>
                      {tableCategory === '전체' && (
                        <span
                          className={`domain-badge ${domainBadgeClass(row.domain)}`}
                        >
                          {row.domain || '기타'}
                        </span>
                      )}
                    </div>
                    <div className="table-ko">{row.korean_name || '—'}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {sidebarTab === 'admin' && (
            <div className="sidebar-section flex-grow no-border dev-panel">
              <div className="section-label">관리자</div>
              {!adminToken ? (
                <form className="admin-login-form" onSubmit={handleAdminLogin}>
                  <p className="dev-panel-hint">
                    아래에서 <strong>고객 풀</strong> 테이블은 로그인 없이 볼 수
                    있습니다. 업로드·관리자 풀 목록·Oracle 생성은 로그인 후
                    가능합니다.
                  </p>
                  <input
                    type="password"
                    className="admin-pwd-input"
                    placeholder="관리자 비밀번호"
                    value={adminPwd}
                    onChange={(e) => setAdminPwd(e.target.value)}
                    autoComplete="current-password"
                  />
                  {adminLoginErr && (
                    <p className="muted small err">{adminLoginErr}</p>
                  )}
                  <button type="submit" className="btn-primary admin-login-btn">
                    로그인
                  </button>
                </form>
              ) : (
                <div className="admin-toolbar">
                  <button
                    type="button"
                    className="btn-secondary btn-small"
                    onClick={handleAdminLogout}
                  >
                    로그아웃
                  </button>
                </div>
              )}

              <p className="dev-panel-hint admin-preview-hint">
                질의 탭과 <strong>동일한 데이터</strong>로 고객 풀(TBL_*)을
                불러옵니다. Oracle 메타는 관리자 풀(TB_*)을 선택하세요.
              </p>
              <label className="admin-field-label" htmlFor="preview-pool">
                테이블 목록(미리보기)
              </label>
              <select
                id="preview-pool"
                className="table-category-select"
                value={adminPreviewPool}
                onChange={(e) => setAdminPreviewPool(e.target.value)}
              >
                <option value="customer">고객 풀 (TBL_* · SAS·현업)</option>
                <option value="admin">관리자 풀 (TB_* · Oracle)</option>
              </select>

              {adminPreviewPool === 'admin' && !adminToken && (
                <p className="muted small">
                  관리자 풀 테이블 목록은 로그인 후 표시됩니다.
                </p>
              )}

              {(adminPreviewPool === 'customer' || adminToken) && (
                <>
                  <label
                    className="table-category-label"
                    htmlFor="table-category-admin"
                  >
                    카테고리
                  </label>
                  <select
                    id="table-category-admin"
                    className="table-category-select"
                    value={tableCategory}
                    onChange={(e) => setTableCategory(e.target.value)}
                    disabled={tables.length === 0}
                  >
                    <option value="전체">전체</option>
                    {tableDomainOptions.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                  <div className="table-list">
                    {tables.length === 0 &&
                      adminPreviewPool === 'customer' && (
                        <p className="muted small">
                          고객 풀에 인덱싱된 테이블이 없습니다. 로그인 후
                          업로드하거나{' '}
                          <code className="inline-code">
                            python scripts/bootstrap_demo_index.py
                          </code>{' '}
                          로 샘플을 넣어 보세요.
                        </p>
                      )}
                    {tables.length === 0 &&
                      adminPreviewPool === 'admin' &&
                      adminToken && (
                        <p className="muted small">
                          관리자 풀에 테이블이 없습니다. 아래에서 관리자 풀로
                          .xlsx를 올리거나{' '}
                          <code className="inline-code">
                            bootstrap_demo_index.py
                          </code>
                          를 실행하세요.
                        </p>
                      )}
                    {tables.length > 0 && filteredTables.length === 0 && (
                      <p className="muted small">
                        이 카테고리에 해당하는 테이블이 없습니다.
                      </p>
                    )}
                    {filteredTables.map((row) => (
                      <button
                        key={`${adminPreviewPool}-${row.table_name}`}
                        type="button"
                        className={`table-row ${selectedTable?.table_name === row.table_name ? 'selected' : ''}`}
                        onClick={() => handleRowClick(row)}
                      >
                        <div className="table-row-top">
                          <span className="table-name">{row.table_name}</span>
                          {tableCategory === '전체' && (
                            <span
                              className={`domain-badge ${domainBadgeClass(row.domain)}`}
                            >
                              {row.domain || '기타'}
                            </span>
                          )}
                        </div>
                        <div className="table-ko">{row.korean_name || '—'}</div>
                      </button>
                    ))}
                  </div>
                </>
              )}

              {adminToken && (
                <>
                  <label className="admin-field-label" htmlFor="upload-pool">
                    업로드 대상 풀
                  </label>
                  <select
                    id="upload-pool"
                    className="table-category-select"
                    value={uploadTargetPool}
                    onChange={(e) => setUploadTargetPool(e.target.value)}
                  >
                    <option value="customer">고객 풀</option>
                    <option value="admin">관리자 풀</option>
                  </select>
                  <p className="muted small naming-hint">
                    파일명=테이블명. 고객{' '}
                    <code className="inline-code">TBL_</code> 뒤는 붙여 쓰기(예:
                    TBL_CUSTDIM.xlsx), 관리자{' '}
                    <code className="inline-code">TB_</code> 뒤 동일(예:
                    TB_BUDGETFACT.xlsx).
                  </p>
                  <label
                    className={`dropzone ${dragOver ? 'dragover' : ''} ${isUploading ? 'busy' : ''}`}
                    onDragOver={(e) => {
                      e.preventDefault()
                      setDragOver(true)
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                  >
                    <input
                      type="file"
                      accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                      multiple
                      onChange={handleFileInput}
                      disabled={isUploading}
                    />
                    {isUploading ? (
                      <span className="dropzone-busy">인덱싱 중…</span>
                    ) : (
                      <>
                        <IconUpload className="dropzone-icon" />
                        <span className="dropzone-title">
                          정의서 .xlsx 업로드
                        </span>
                        <span className="dropzone-hint">
                          위에서 선택한 풀에만 반영됩니다
                        </span>
                      </>
                    )}
                  </label>
                  <div className="admin-reset-row">
                    <button
                      type="button"
                      className="btn-secondary btn-small"
                      onClick={() => handleResetPool('customer')}
                    >
                      고객 풀 초기화
                    </button>
                    <button
                      type="button"
                      className="btn-secondary btn-small"
                      onClick={() => handleResetPool('admin')}
                    >
                      관리자 풀 초기화
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <div className="sidebar-bottom">
          {selectedTable && (
            <div className="preview-block">
              <div className="section-label">컬럼 미리보기</div>
              <div className="preview-meta">
                <span className="table-name">{selectedTable.table_name}</span>
              </div>
              {selectedTable.columns === null && (
                <p className="muted small">불러오는 중…</p>
              )}
              {selectedTable.columnsError && (
                <>
                  <p className="muted small err">{selectedTable.columnsError}</p>
                  <p className="muted small">
                    컬럼 메타는 벡터 DB에 없을 수 있습니다. 엑셀을 다시
                    인덱싱해 보세요.
                  </p>
                </>
              )}
              {Array.isArray(selectedTable.columns) &&
                selectedTable.columns.length === 0 &&
                !selectedTable.columnsError && (
                  <p className="muted small">컬럼 정보가 없습니다.</p>
                )}
              {Array.isArray(selectedTable.columns) &&
                selectedTable.columns.length > 0 && (
                  <>
                    <div className="col-chips">
                      {selectedTable.columns.map((col) => {
                        const idx = Boolean(col.is_indexed)
                        const pk = Boolean(col.is_pk)
                        const fk = Boolean(col.is_fk)
                        const chipClass = [
                          'col-chip',
                          pk && 'pk',
                          fk && 'fk',
                          idx && 'indexed',
                        ]
                          .filter(Boolean)
                          .join(' ')
                        const tip = [
                          pk && '기본키(PK)',
                          fk && '외래키(FK)',
                          idx && '인덱스(정의서 8열 Y)',
                        ]
                          .filter(Boolean)
                          .join(' · ')
                        return (
                          <span
                            key={col.name}
                            className={chipClass}
                            title={
                              tip || '일반 컬럼(정의서에 인덱스 미표시)'
                            }
                            aria-label={`${col.name}. ${tip || '일반 컬럼'}`}
                          >
                            <span className="col-chip-name">{col.name}</span>
                            {(pk || fk || idx) && (
                              <span className="col-chip-badges">
                                {pk && (
                                  <span className="col-chip-badge col-chip-badge-pk">
                                    PK
                                  </span>
                                )}
                                {fk && (
                                  <span className="col-chip-badge col-chip-badge-fk">
                                    FK
                                  </span>
                                )}
                                {idx && (
                                  <span className="col-chip-badge col-chip-badge-ix">
                                    IX
                                  </span>
                                )}
                              </span>
                            )}
                          </span>
                        )
                      })}
                    </div>
                    <div
                      className="col-preview-legend"
                      role="note"
                      aria-label="컬럼 칩 색상·표기 안내"
                    >
                      <span className="col-preview-legend-title">
                        색상·표기 안내
                      </span>
                      <p className="col-preview-legend-lead muted small">
                        각 컬럼 칩에는 컬럼명 옆에{' '}
                        <strong className="col-preview-legend-mono">PK</strong>·
                        <strong className="col-preview-legend-mono">FK</strong>·
                        <strong className="col-preview-legend-mono">IX</strong>{' '}
                        뱃지가 붙습니다. 배경색·왼쪽 세로줄과 함께 아래
                        의미를 가집니다.
                      </p>
                      <div className="col-preview-legend-items">
                        <div className="col-preview-legend-item">
                          <span
                            className="col-preview-legend-swatch pk"
                            aria-hidden
                          />
                          <span>
                            <strong>노란색</strong> + 뱃지{' '}
                            <span className="col-preview-legend-mono">PK</span>{' '}
                            — 기본키 컬럼입니다.
                          </span>
                        </div>
                        <div className="col-preview-legend-item">
                          <span
                            className="col-preview-legend-swatch index"
                            aria-hidden
                          />
                          <span>
                            <strong>연한 남색</strong> + 뱃지{' '}
                            <span className="col-preview-legend-mono">IX</span>{' '}
                            — PK·FK가 아니고, 정의서 8열「인덱스」에 Y인
                            컬럼입니다.
                          </span>
                        </div>
                        <div className="col-preview-legend-item">
                          <span
                            className="col-preview-legend-swatch fk"
                            aria-hidden
                          />
                          <span>
                            <strong>살구색</strong> + 뱃지{' '}
                            <span className="col-preview-legend-mono">FK</span>{' '}
                            — 외래키, 다른 테이블 컬럼을 참조합니다. (IX도
                            있으면 함께 표시)
                          </span>
                        </div>
                        <div className="col-preview-legend-item">
                          <span
                            className="col-preview-legend-swatch plain"
                            aria-hidden
                          />
                          <span>
                            <strong>회색</strong> — 뱃지 없음 또는 위에 해당
                            없음. 일반 컬럼입니다.
                          </span>
                        </div>
                        <div className="col-preview-legend-item">
                          <span
                            className="col-preview-legend-swatch pk-indexed"
                            aria-hidden
                          />
                          <span>
                            <strong>왼쪽 청록 세로줄</strong> — PK 또는 FK
                            칩에 <span className="col-preview-legend-mono">IX</span>{' '}
                            뱃지가 함께 있을 때: 해당 컬럼에 별도 인덱스가
                            정의됨(정의서 인덱스=Y)을 뜻합니다.
                          </span>
                        </div>
                      </div>
                    </div>
                  </>
                )}
            </div>
          )}
        </div>
      </aside>

      <main className="main">
        {sidebarTab === 'query' && stats && (
          <aside className="main-stats-dock" aria-label="인덱스 요약">
            <div className="stats-line">
              <strong>{stats.total_tables}</strong> 테이블 (고객 풀)
            </div>
            {domainSummary && (
              <div className="stats-sub muted small">{domainSummary}</div>
            )}
            <div className="stats-sub muted small mono">{stats.model}</div>
          </aside>
        )}

        {sidebarTab === 'admin' && adminToken && adminSummary && (
          <aside className="main-stats-dock" aria-label="풀별 인덱스 요약">
            <div className="stats-line stats-line-split">
              <span>
                고객 풀 <strong>{adminSummary.customer?.total ?? 0}</strong>
              </span>
              <span>
                관리자 풀 <strong>{adminSummary.admin?.total ?? 0}</strong>
              </span>
            </div>
            <div className="stats-sub muted small mono">
              {adminSummary.customer?.model || ''}
            </div>
          </aside>
        )}

        <div className="main-inner">
          {sidebarTab === 'query' && (
            <div className="input-card">
              <div className="sql-format-block">
                <div className="sql-format-labels">
                  <span className="input-field-label">SQL 종류</span>
                  <span className="input-field-hint">
                    현업·고객용 — SAS PROC SQL만 생성합니다. 스키마 검색은{' '}
                    <strong>고객 풀 전체</strong> 테이블을 대상으로 하며, 왼쪽에서
                    고른 테이블의 카테고리로 검색을 막지 않습니다. 테이블명{' '}
                    <code className="inline-code">TBL_</code>뒤 붙여 쓰기(예:
                    TBL_CUSTDIM → 별칭 dim)
                  </span>
                </div>
                <div className="dialect-badge-static">SAS PROC SQL</div>
              </div>

              <div className="query-input-wrap">
                <textarea
                  className="query-input"
                  placeholder="자연어로 질의를 입력하세요… (Ctrl+Enter로 생성)"
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={5}
                  disabled={isLoading}
                />
              </div>
              <div className="input-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setQueryText('')}
                  disabled={isLoading || !queryText}
                  title="입력한 질의 지우기"
                >
                  초기화
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={submitQuery}
                  disabled={isLoading || !queryText.trim()}
                >
                  {isLoading ? '생성 중…' : '생성'}
                </button>
              </div>
              <div className="chips-row favorites-chips">
                {favorites.customer.map((f) => (
                  <div key={f.id} className="favorite-chip-wrap">
                    <button
                      type="button"
                      className="chip favorite-chip"
                      title={f.query}
                      onClick={() =>
                        void executeCustomerQuery(f.query, {
                          favoriteId: f.id,
                        })
                      }
                    >
                      <span className="favorite-chip-icon" aria-hidden>
                        ★
                      </span>
                      {f.name}
                    </button>
                    <button
                      type="button"
                      className="favorite-chip-remove"
                      aria-label={`${f.name} 즐겨찾기 삭제`}
                      onClick={() =>
                        setFavorites(removeFavorite('customer', f.id))
                      }
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <p className="muted small chips-hint">
                고객 풀 즐겨찾기(이 브라우저 저장). 성공한 질의 결과 카드에서
                ☆로 추가합니다.
              </p>
            </div>
          )}

          {sidebarTab === 'admin' && adminToken && (
            <div className="input-card admin-oracle-card">
              <div className="sql-format-block">
                <div className="sql-format-labels">
                  <span className="input-field-label">Oracle SQL</span>
                  <span className="input-field-hint">
                    관리자 풀(TB_*) 전체를 스키마 검색 대상으로 하며, 유사 테이블이
                    없으면 풀에 있는 테이블 정의를 모두 넣어 생성합니다. 조회 또는
                    DML(INSERT·MERGE·UPDATE·DELETE)
                  </span>
                </div>
                <div className="dialect-toggle dialect-toggle-main">
                  <button
                    type="button"
                    className={oracleProfile === 'select_only' ? 'active' : ''}
                    onClick={() => setOracleProfile('select_only')}
                  >
                    조회만
                  </button>
                  <button
                    type="button"
                    className={oracleProfile === 'admin_dml' ? 'active' : ''}
                    onClick={() => setOracleProfile('admin_dml')}
                  >
                    DML 허용
                  </button>
                </div>
              </div>
              <div className="query-input-wrap">
                <textarea
                  className="query-input"
                  placeholder="자연어로 Oracle 작업을 설명하세요… (Ctrl+Enter)"
                  value={adminQueryText}
                  onChange={(e) => setAdminQueryText(e.target.value)}
                  onKeyDown={onAdminKeyDown}
                  rows={5}
                  disabled={isAdminQueryLoading}
                />
              </div>
              <div className="input-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setAdminQueryText('')}
                  disabled={isAdminQueryLoading || !adminQueryText}
                >
                  초기화
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={submitAdminQuery}
                  disabled={isAdminQueryLoading || !adminQueryText.trim()}
                >
                  {isAdminQueryLoading ? '생성 중…' : 'Oracle SQL 생성'}
                </button>
              </div>
              <div className="chips-row favorites-chips">
                {favorites.admin.map((f) => (
                  <div key={f.id} className="favorite-chip-wrap">
                    <button
                      type="button"
                      className="chip favorite-chip"
                      title={f.query}
                      onClick={() =>
                        void executeAdminQuery(f.query, { favoriteId: f.id })
                      }
                    >
                      <span className="favorite-chip-icon" aria-hidden>
                        ★
                      </span>
                      {f.name}
                    </button>
                    <button
                      type="button"
                      className="favorite-chip-remove"
                      aria-label={`${f.name} 즐겨찾기 삭제`}
                      onClick={() =>
                        setFavorites(removeFavorite('admin', f.id))
                      }
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <p className="muted small chips-hint">
                관리자 풀 즐겨찾기(이 브라우저 저장). 성공한 Oracle 결과 카드에서
                ☆로 추가합니다.
              </p>
            </div>
          )}

          {sidebarTab === 'admin' && !adminToken && (
            <div className="input-card admin-placeholder-card">
              <p className="muted">
                왼쪽 사이드바에서 관리자 로그인 후 Oracle SQL 생성·정의서
                업로드를 사용할 수 있습니다.
              </p>
            </div>
          )}

          <div className="results-area">
            {sidebarTab === 'query' && results.length === 0 && (
              <div className="empty-state">
                <IconEmpty className="empty-state-icon" />
                <p>
                  테이블을 선택하고 자연어로 질의하세요.
                  <br />
                  <span className="empty-sub">
                    데이터가 없으면 관리자 탭에서 고객 풀 정의서를 올려 주세요.
                  </span>
                </p>
              </div>
            )}

            {sidebarTab === 'admin' &&
              adminToken &&
              adminResults.length === 0 && (
                <div className="empty-state">
                  <IconEmpty className="empty-state-icon" />
                  <p>
                    관리자 풀에 인덱싱된 테이블을 바탕으로 Oracle SQL을 생성할
                    수 있습니다. DDL(CREATE·ALTER·DROP·TRUNCATE)은 생성되지
                    않습니다.
                  </p>
                </div>
              )}

            {sidebarTab === 'query' &&
              results.map((item) => (
                <article key={item.id} className="result-card">
                {item.error ? (
                  <>
                    <div className="card-head">
                      <span className="card-query">{item.query}</span>
                      <span className="badge err">오류</span>
                    </div>
                    <div className="sql-null-box">{item.error}</div>
                  </>
                ) : !item.data ? (
                  <>
                    <div className="card-head">
                      <span className="card-query">{item.query}</span>
                      <span className="badge err">오류</span>
                    </div>
                    <div className="sql-null-box">
                      서버 응답을 표시할 수 없습니다. 잠시 후 다시 시도해 주세요.
                    </div>
                  </>
                ) : (
                  <>
                    <div className="card-head">
                      <span className="card-query">{item.query}</span>
                      <span
                        className={`conf-badge ${confidenceClass(item.data.confidence)}`}
                      >
                        {item.data.confidence}
                      </span>
                      <span className="dialect-badge">
                        {item.data.dialect === 'oracle' ? 'Oracle' : 'SAS'}
                      </span>
                      <div className="card-head-actions">
                        <button
                          type="button"
                          className="btn-copy"
                          onClick={() => {
                            if (item.data.sql)
                              navigator.clipboard.writeText(item.data.sql)
                          }}
                          disabled={!item.data.sql}
                        >
                          복사
                        </button>
                        <button
                          type="button"
                          className={`btn-favorite ${
                            isFavoriteLinked(
                              favorites.customer,
                              item.favoriteId,
                            )
                              ? 'btn-favorite-on'
                              : ''
                          }`}
                          onClick={() => handleFavoriteStarCustomer(item)}
                          disabled={
                            !isFavoriteLinked(
                              favorites.customer,
                              item.favoriteId,
                            ) && !item.data.sql
                          }
                          title={
                            isFavoriteLinked(
                              favorites.customer,
                              item.favoriteId,
                            )
                              ? '즐겨찾기 해제'
                              : '즐겨찾기에 추가'
                          }
                          aria-label={
                            isFavoriteLinked(
                              favorites.customer,
                              item.favoriteId,
                            )
                              ? '즐겨찾기 해제'
                              : '즐겨찾기에 추가'
                          }
                        >
                          {isFavoriteLinked(
                            favorites.customer,
                            item.favoriteId,
                          )
                            ? '★'
                            : '☆'}
                        </button>
                      </div>
                    </div>

                    {item.data.sql ? (
                      <SqlBlock
                        sql={item.data.sql}
                        onCopy={() =>
                          navigator.clipboard.writeText(item.data.sql)
                        }
                      />
                    ) : (
                      <div className="sql-null-box">
                        쿼리를 생성할 수 없습니다
                      </div>
                    )}

                    {item.data.clarification_needed && (
                      <div className="clar-box">
                        {item.data.clarification_needed}
                      </div>
                    )}

                    <p className="explanation">{item.data.explanation}</p>

                    <div className="used-tables">
                      {(item.data.used_tables || []).map((t) => (
                        <span key={t} className="used-chip">
                          {t}
                        </span>
                      ))}
                    </div>
                  </>
                )}
                </article>
              ))}

            {sidebarTab === 'admin' &&
              adminToken &&
              adminResults.map((item) => (
                <article key={item.id} className="result-card">
                  {item.error ? (
                    <>
                      <div className="card-head">
                        <span className="card-query">{item.query}</span>
                        <span className="badge err">오류</span>
                      </div>
                      <div className="sql-null-box">{item.error}</div>
                    </>
                  ) : !item.data ? (
                    <>
                      <div className="card-head">
                        <span className="card-query">{item.query}</span>
                        <span className="badge err">오류</span>
                      </div>
                      <div className="sql-null-box">
                        서버 응답을 표시할 수 없습니다. 잠시 후 다시 시도해 주세요.
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="card-head">
                        <span className="card-query">{item.query}</span>
                        <span
                          className={`conf-badge ${confidenceClass(item.data.confidence)}`}
                        >
                          {item.data.confidence}
                        </span>
                        <span className="dialect-badge">Oracle</span>
                        {item.data.oracle_profile && (
                          <span className="dialect-badge subtle">
                            {item.data.oracle_profile === 'admin_dml'
                              ? 'DML'
                              : '조회'}
                          </span>
                        )}
                        <div className="card-head-actions">
                          <button
                            type="button"
                            className="btn-copy"
                            onClick={() => {
                              if (item.data.sql)
                                navigator.clipboard.writeText(item.data.sql)
                            }}
                            disabled={!item.data.sql}
                          >
                            복사
                          </button>
                          <button
                            type="button"
                            className={`btn-favorite ${
                              isFavoriteLinked(favorites.admin, item.favoriteId)
                                ? 'btn-favorite-on'
                                : ''
                            }`}
                            onClick={() => handleFavoriteStarAdmin(item)}
                            disabled={
                              !isFavoriteLinked(
                                favorites.admin,
                                item.favoriteId,
                              ) && !item.data.sql
                            }
                            title={
                              isFavoriteLinked(favorites.admin, item.favoriteId)
                                ? '즐겨찾기 해제'
                                : '즐겨찾기에 추가'
                            }
                            aria-label={
                              isFavoriteLinked(favorites.admin, item.favoriteId)
                                ? '즐겨찾기 해제'
                                : '즐겨찾기에 추가'
                            }
                          >
                            {isFavoriteLinked(favorites.admin, item.favoriteId)
                              ? '★'
                              : '☆'}
                          </button>
                        </div>
                      </div>

                      {item.data.sql ? (
                        <SqlBlock
                          sql={item.data.sql}
                          onCopy={() =>
                            navigator.clipboard.writeText(item.data.sql)
                          }
                        />
                      ) : (
                        <div className="sql-null-box">
                          쿼리를 생성할 수 없습니다
                        </div>
                      )}

                      {item.data.clarification_needed && (
                        <div className="clar-box">
                          {item.data.clarification_needed}
                        </div>
                      )}

                      <p className="explanation">{item.data.explanation}</p>

                      <div className="used-tables">
                        {(item.data.used_tables || []).map((t) => (
                          <span key={t} className="used-chip">
                            {t}
                          </span>
                        ))}
                      </div>
                    </>
                  )}
                </article>
              ))}
          </div>
        </div>
      </main>
    </div>
  )
}
