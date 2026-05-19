/**
 * 브라우저 localStorage에 풀별 자연어 질의 즐겨찾기를 저장합니다.
 * @typedef {{ id: string, name: string, query: string }} FavoriteItem
 */

const STORAGE_KEY = 'schema-query-favorites-v1'

/** @returns {{ customer: FavoriteItem[], admin: FavoriteItem[] }} */
export function loadFavorites() {
  if (typeof localStorage === 'undefined') {
    return { customer: [], admin: [] }
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { customer: [], admin: [] }
    const o = JSON.parse(raw)
    return {
      customer: Array.isArray(o.customer) ? o.customer : [],
      admin: Array.isArray(o.admin) ? o.admin : [],
    }
  } catch {
    return { customer: [], admin: [] }
  }
}

function saveAll(data) {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
}

/**
 * @param {'customer'|'admin'} pool
 * @param {string} name
 * @param {string} query
 * @returns {{ customer: FavoriteItem[], admin: FavoriteItem[] }}
 */
export function addFavorite(pool, name, query) {
  const n = String(name ?? '').trim()
  const q = String(query ?? '').trim()
  const data = loadFavorites()
  if (!n || !q) {
    return data
  }
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  data[pool].push({ id, name: n, query: q })
  saveAll(data)
  return loadFavorites()
}

/**
 * @param {'customer'|'admin'} pool
 * @param {string} id
 */
export function removeFavorite(pool, id) {
  const data = loadFavorites()
  data[pool] = data[pool].filter((x) => x.id !== id)
  saveAll(data)
  return loadFavorites()
}
