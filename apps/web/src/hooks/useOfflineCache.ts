/**
 * hooks/useOfflineCache.ts  (web)
 *
 * IndexedDB-backed cache using idb-keyval.
 * Falls back gracefully to a no-op if IndexedDB is unavailable.
 *
 * Usage:
 *   const cache = useOfflineCache()
 *   await cache.set('recipes', data)
 *   const data = await cache.get<Recipe[]>('recipes')
 */

const DB_PREFIX = 'rr_web_cache:'
const TTL_MS = 24 * 60 * 60 * 1000   // 24 hours

interface CacheEntry<T> { data: T; cachedAt: number }

function idbAvailable() {
  return typeof window !== 'undefined' && 'indexedDB' in window
}

async function idbGet(key: string): Promise<string | undefined> {
  if (!idbAvailable()) return undefined
  return new Promise((resolve) => {
    const req = indexedDB.open('rr_cache', 1)
    req.onupgradeneeded = (e) => {
      (e.target as IDBOpenDBRequest).result.createObjectStore('cache')
    }
    req.onsuccess = (e) => {
      const db = (e.target as IDBOpenDBRequest).result
      const tx = db.transaction('cache', 'readonly')
      const get = tx.objectStore('cache').get(key)
      get.onsuccess = () => resolve(get.result)
      get.onerror = () => resolve(undefined)
    }
    req.onerror = () => resolve(undefined)
  })
}

async function idbSet(key: string, value: string): Promise<void> {
  if (!idbAvailable()) return
  return new Promise((resolve) => {
    const req = indexedDB.open('rr_cache', 1)
    req.onupgradeneeded = (e) => {
      (e.target as IDBOpenDBRequest).result.createObjectStore('cache')
    }
    req.onsuccess = (e) => {
      const db = (e.target as IDBOpenDBRequest).result
      const tx = db.transaction('cache', 'readwrite')
      tx.objectStore('cache').put(value, key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => resolve()
    }
    req.onerror = () => resolve()
  })
}

async function idbDelete(key: string): Promise<void> {
  if (!idbAvailable()) return
  return new Promise((resolve) => {
    const req = indexedDB.open('rr_cache', 1)
    req.onsuccess = (e) => {
      const db = (e.target as IDBOpenDBRequest).result
      const tx = db.transaction('cache', 'readwrite')
      tx.objectStore('cache').delete(key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => resolve()
    }
    req.onerror = () => resolve()
  })
}

export function useOfflineCache() {
  async function get<T>(key: string): Promise<T | null> {
    try {
      const raw = await idbGet(`${DB_PREFIX}${key}`)
      if (!raw) return null
      const entry: CacheEntry<T> = JSON.parse(raw)
      if (Date.now() - entry.cachedAt > TTL_MS) {
        await idbDelete(`${DB_PREFIX}${key}`)
        return null
      }
      return entry.data
    } catch {
      return null
    }
  }

  async function set<T>(key: string, data: T): Promise<void> {
    try {
      const entry: CacheEntry<T> = { data, cachedAt: Date.now() }
      await idbSet(`${DB_PREFIX}${key}`, JSON.stringify(entry))
    } catch { /* storage unavailable — fail silently */ }
  }

  return { get, set }
}
