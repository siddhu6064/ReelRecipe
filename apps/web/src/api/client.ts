import type {
  JobStatusResponse,
  Pantry,
  PantryItem,
  PantryMatchResult,
  Recipe,
} from '@reelrecipes/shared'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type ApiResponse<T> = { ok: true; data: T }

async function request<T>(
  path: string,
  token: string | null,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers as Record<string, string>),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail ?? `${res.status} ${res.statusText}`)
  }
  const envelope = (await res.json()) as ApiResponse<T>
  return envelope.data
}

export const importVideo = (url: string, token: string | null) =>
  request<{ jobId: string; status: string; deduplicated: boolean }>(
    '/api/jobs/import', token,
    { method: 'POST', body: JSON.stringify({ url }) },
  )

export const getJob = (jobId: string, token: string | null) =>
  request<JobStatusResponse>(`/api/jobs/${jobId}`, token)

export interface RecipeListData { recipes: Recipe[]; total: number; limit: number; offset: number }

export const getRecipes = (token: string | null, params?: Record<string, string | number>) => {
  const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : ''
  return request<RecipeListData>(`/api/recipes${qs}`, token)
}

export const getRecipe = (id: string, token: string | null) =>
  request<Recipe>(`/api/recipes/${id}`, token)

export const updateRecipe = (id: string, body: Partial<Recipe>, token: string | null) =>
  request<Recipe>(`/api/recipes/${id}`, token, { method: 'PUT', body: JSON.stringify(body) })

export const deleteRecipe = async (id: string, token: string | null) => {
  const res = await fetch(`${BASE}/api/recipes/${id}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`)
}

export const getPantry = (token: string | null) => request<Pantry>('/api/pantry', token)

export const addPantryItem = (
  item: Omit<PantryItem, 'id' | 'added_at' | 'updated_at'>, token: string | null,
) => request<PantryItem>('/api/pantry/items', token, { method: 'POST', body: JSON.stringify(item) })

export const updatePantryItem = (
  itemId: string,
  update: Partial<Pick<PantryItem, 'quantity' | 'unit' | 'category'>>,
  token: string | null,
) => request<PantryItem>(`/api/pantry/items/${itemId}`, token, { method: 'PUT', body: JSON.stringify(update) })

export const deletePantryItem = async (itemId: string, token: string | null) => {
  const res = await fetch(`${BASE}/api/pantry/items/${itemId}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`)
}

export const getPantryMatch = (token: string | null) =>
  request<PantryMatchResult[]>('/api/pantry/match', token)

export const suggestRecipes = (
  body: { dietary_prefs: string[]; cuisine_prefs: string[]; max_recipes: number },
  token: string | null,
) => request<Recipe[]>('/api/ai/suggest', token, { method: 'POST', body: JSON.stringify(body) })

export const chatAboutRecipe = (
  recipeId: string, message: string,
  history: { role: string; content: string }[], token: string | null,
) => request<{ reply: string }>(`/api/ai/chat/${recipeId}`, token, {
  method: 'POST', body: JSON.stringify({ message, history }),
})

export const substituteIngredient = (
  recipeId: string, ingredientName: string, token: string | null,
) => request<{ ingredient: string; substitutions: { name: string; notes: string }[] }>(
  '/api/ai/substitute', token,
  { method: 'POST', body: JSON.stringify({ recipe_id: recipeId, ingredient_name: ingredientName }) },
)
