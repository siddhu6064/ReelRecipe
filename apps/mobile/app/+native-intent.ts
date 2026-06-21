/**
 * app/+native-intent.ts
 *
 * Handles deep links via the custom reelrecipes:// scheme.
 *
 * Supported deep links:
 *   reelrecipes://recipe/:id        → open a saved recipe
 *   reelrecipes://import?url=...    → import a video URL directly
 *   reelrecipes://pantry            → open pantry tab
 *   reelrecipes://discover          → open discover tab
 *
 * Also handles https://reelrecipes.app/* universal links (same paths).
 */

import { parse } from 'expo-linking'

export function redirectSystemPath({
  path,
  initial,
}: {
  path: string
  initial: boolean
}): string {
  // Strip scheme prefix for uniform handling
  const clean = path
    .replace(/^reelrecipes:\/\//, '/')
    .replace(/^https?:\/\/reelrecipes\.app/, '')

  // Parse query params
  const { path: routePath, queryParams } = parse(`reelrecipes:/${clean}`)

  // Handle import URLs: reelrecipes://import?url=https://...
  if (routePath?.includes('import') && queryParams?.url) {
    return `/import?url=${encodeURIComponent(String(queryParams.url))}`
  }

  // Pass through recognised routes
  const VALID = ['/pantry', '/discover', '/cookbook', '/import', '/meal-planner']
  if (VALID.some(r => routePath?.startsWith(r))) {
    return routePath!
  }
  if (routePath?.startsWith('/recipe/')) {
    return routePath
  }

  // Fallback to home
  return '/'
}
