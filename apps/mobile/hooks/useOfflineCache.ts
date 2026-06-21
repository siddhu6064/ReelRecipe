/**
 * hooks/useOfflineCache.ts
 *
 * Caches API responses to AsyncStorage so recipes are available
 * when the device is offline.
 *
 * Usage:
 *   const { getCached, setCached } = useOfflineCache()
 *   const cached = await getCached('recipes')
 *   await setCached('recipes', data)
 */

import AsyncStorage from '@react-native-async-storage/async-storage'

const CACHE_PREFIX = 'rr_cache:'
const CACHE_TTL_MS = 24 * 60 * 60 * 1000   // 24 hours

interface CacheEntry<T> {
  data: T
  cachedAt: number
}

export function useOfflineCache() {

  async function getCached<T>(key: string): Promise<T | null> {
    try {
      const raw = await AsyncStorage.getItem(`${CACHE_PREFIX}${key}`)
      if (!raw) return null
      const entry: CacheEntry<T> = JSON.parse(raw)
      // Invalidate stale entries
      if (Date.now() - entry.cachedAt > CACHE_TTL_MS) {
        await AsyncStorage.removeItem(`${CACHE_PREFIX}${key}`)
        return null
      }
      return entry.data
    } catch {
      return null
    }
  }

  async function setCached<T>(key: string, data: T): Promise<void> {
    try {
      const entry: CacheEntry<T> = { data, cachedAt: Date.now() }
      await AsyncStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(entry))
    } catch { /* storage full — fail silently */ }
  }

  async function clearCache(): Promise<void> {
    try {
      const keys = await AsyncStorage.getAllKeys()
      const cacheKeys = keys.filter(k => k.startsWith(CACHE_PREFIX))
      if (cacheKeys.length > 0) await AsyncStorage.multiRemove(cacheKeys)
    } catch { /* ignore */ }
  }

  return { getCached, setCached, clearCache }
}
