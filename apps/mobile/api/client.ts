const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_URL}${path}`, { ...options, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail ?? `Request failed (${res.status})`)
  }
  return res.json()
}

export const api = {
  importVideo: (url: string, token?: string) =>
    request('/api/jobs/import', { method: 'POST', body: JSON.stringify({ url }) }, token),

  getJob: (jobId: string, token?: string) =>
    request(`/api/jobs/${jobId}`, {}, token),

  getRecipes: (token?: string) =>
    request('/api/recipes', {}, token),

  getRecipe: (id: string, token?: string) =>
    request(`/api/recipes/${id}`, {}, token),

  getPantry: (token?: string) =>
    request('/api/pantry', {}, token),

  addPantryItem: (item: object, token?: string) =>
    request('/api/pantry/items', { method: 'POST', body: JSON.stringify(item) }, token),

  getPantryMatch: (token?: string) =>
    request('/api/pantry/match', {}, token),

  suggestRecipes: (body: object, token?: string) =>
    request('/api/ai/suggest', { method: 'POST', body: JSON.stringify(body) }, token),
}
