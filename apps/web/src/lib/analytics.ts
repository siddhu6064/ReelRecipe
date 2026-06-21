/**
 * apps/web/src/lib/analytics.ts
 *
 * PostHog event tracking wrapper.
 * All events use the same naming scheme as ReelRoutes (snake_case).
 * Only fires in production to keep local dev clean.
 */

declare global {
  interface Window {
    posthog?: {
      capture: (event: string, props?: Record<string, unknown>) => void
      identify: (id: string, props?: Record<string, unknown>) => void
      reset: () => void
    }
  }
}

const isProd = import.meta.env.PROD

function track(event: string, props?: Record<string, unknown>) {
  if (!isProd) return
  window.posthog?.capture(event, props)
}

// ── Recipe events ────────────────────────────────────────────────────────

export const analytics = {
  /** User submits a video URL for extraction */
  importStarted: (platform: string) =>
    track('import_started', { platform }),

  /** Job completed successfully — recipe created */
  importCompleted: (platform: string, extractionSeconds: number) =>
    track('import_completed', { platform, extraction_seconds: extractionSeconds }),

  /** Job failed */
  importFailed: (platform: string, errorCode: string) =>
    track('import_failed', { platform, error_code: errorCode }),

  /** User opened the full recipe page */
  recipeViewed: (recipeId: string, source: 'cookbook' | 'processing' | 'discover') =>
    track('recipe_viewed', { recipe_id: recipeId, source }),

  /** User edited a recipe field */
  recipeEdited: (recipeId: string, field: string) =>
    track('recipe_edited', { recipe_id: recipeId, field }),

  /** User deleted a recipe */
  recipeDeleted: (recipeId: string) =>
    track('recipe_deleted', { recipe_id: recipeId }),

  // ── Pantry events ────────────────────────────────────────────────────

  /** User added an ingredient to pantry */
  pantryItemAdded: (category: string) =>
    track('pantry_item_added', { category }),

  /** User viewed the pantry match list */
  pantryMatchViewed: (recipeCount: number) =>
    track('pantry_match_viewed', { recipe_count: recipeCount }),

  // ── AI events ────────────────────────────────────────────────────────

  /** User requested AI recipe suggestions */
  aiSuggestRequested: (pantrySize: number) =>
    track('ai_suggest_requested', { pantry_size: pantrySize }),

  /** User sent a chat message about a recipe */
  aiChatMessage: (recipeId: string) =>
    track('ai_chat_message', { recipe_id: recipeId }),

  /** User requested ingredient substitutions */
  substitutionRequested: (recipeId: string, ingredient: string) =>
    track('substitution_requested', { recipe_id: recipeId, ingredient }),

  // ── Cook Mode ────────────────────────────────────────────────────────

  /** User started Cook Mode */
  cookModeStarted: (recipeId: string, stepCount: number) =>
    track('cook_mode_started', { recipe_id: recipeId, step_count: stepCount }),

  /** User completed all steps in Cook Mode */
  cookModeCompleted: (recipeId: string) =>
    track('cook_mode_completed', { recipe_id: recipeId }),

  // ── Auth ─────────────────────────────────────────────────────────────

  identify: (clerkId: string, email: string) => {
    if (!isProd) return
    window.posthog?.identify(clerkId, { email })
  },

  signedOut: () => {
    if (!isProd) return
    window.posthog?.reset()
  },
}
