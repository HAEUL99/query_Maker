export const BASE = 'http://localhost:8000'

async function _throwIfNotOk(res) {
  if (!res.ok) {
    const text = await res.text()
    const err = new Error(text || `HTTP ${res.status}`)
    err.status = res.status
    throw err
  }
}

/**
 * @param {string} password
 * @returns {Promise<{ access_token: string, token_type: string }>}
 */
export async function loginAdmin(password) {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  await _throwIfNotOk(res)
  return res.json()
}

/**
 * @param {File[]} files
 * @param {'customer'|'admin'} schemaPool
 * @param {string} token
 */
export async function uploadFiles(files, schemaPool, token) {
  const form = new FormData()
  form.append('schema_pool', schemaPool)
  for (const f of files) {
    form.append('files', f)
  }
  const res = await fetch(`${BASE}/api/index`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  await _throwIfNotOk(res)
  return res.json()
}

/**
 * @param {string} token
 * @param {'customer'|'admin'} schemaPool
 */
export async function resetIndex(token, schemaPool) {
  const res = await fetch(
    `${BASE}/api/index/reset?schema_pool=${encodeURIComponent(schemaPool)}`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    },
  )
  await _throwIfNotOk(res)
  return res.json()
}

/**
 * @param {string} query
 * @param {'oracle'|'sas'} dialect
 * @param {string|null|undefined} domain
 * @param {number|null|undefined} top_k
 * @param {{ schema_pool?: 'customer'|'admin', oracle_profile?: 'select_only'|'admin_dml', token?: string|null }} [opts]
 */
export async function querySQL(query, dialect, domain, top_k, opts = {}) {
  const schema_pool = opts.schema_pool ?? 'customer'
  const oracle_profile = opts.oracle_profile ?? 'select_only'
  const body = {
    query,
    dialect,
    domain: domain ?? null,
    top_k: top_k ?? null,
    schema_pool,
    oracle_profile,
    history: opts.history ?? [],
  }
  const headers = { 'Content-Type': 'application/json' }
  if (opts.token) {
    headers.Authorization = `Bearer ${opts.token}`
  }
  const res = await fetch(`${BASE}/api/query`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  await _throwIfNotOk(res)
  return res.json()
}

/**
 * @param {string|undefined|null} domain
 * @param {'customer'|'admin'} [schemaPool]
 * @param {string|null} [token] admin 풀일 때 필수
 */
export async function getTables(domain, schemaPool = 'customer', token = null) {
  const params = new URLSearchParams()
  if (domain != null && domain !== '') {
    params.set('domain', domain)
  }
  params.set('schema_pool', schemaPool)
  const headers = {}
  if (schemaPool === 'admin' && token) {
    headers.Authorization = `Bearer ${token}`
  }
  const q = params.toString() ? `?${params}` : ''
  const res = await fetch(`${BASE}/api/tables${q}`, { headers })
  await _throwIfNotOk(res)
  return res.json()
}

/**
 * @param {'customer'|'admin'} [schemaPool]
 * @param {string|null} [token]
 */
export async function getStats(schemaPool = 'customer', token = null) {
  const params = new URLSearchParams()
  params.set('schema_pool', schemaPool)
  const headers = {}
  if (schemaPool === 'admin' && token) {
    headers.Authorization = `Bearer ${token}`
  }
  const res = await fetch(`${BASE}/api/stats?${params}`, { headers })
  await _throwIfNotOk(res)
  return res.json()
}

/**
 * @param {string} tableName
 * @param {'customer'|'admin'} schemaPool
 * @param {string} token
 */
export async function deleteTable(tableName, schemaPool, token) {
  const params = new URLSearchParams({ schema_pool: schemaPool })
  const res = await fetch(
    `${BASE}/api/tables/${encodeURIComponent(tableName)}?${params}`,
    {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    },
  )
  await _throwIfNotOk(res)
  return res.json()
}

/**
 * @param {string} token
 */
export async function adminStatsSummary(token) {
  const res = await fetch(`${BASE}/api/admin/stats/summary`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  await _throwIfNotOk(res)
  return res.json()
}

/**
 * 새도약기금 시연 SQL (querySample 파일, 수정 즉시 반영)
 * @param {'sas_step1'|'sas_step2'|'oracle'} source
 */
export async function getSaedoyakDemoSql(source) {
  const params = new URLSearchParams({ source })
  const res = await fetch(`${BASE}/api/demo/saedoyak-sql?${params}`, {
    cache: 'no-store',
  })
  await _throwIfNotOk(res)
  return res.json()
}
