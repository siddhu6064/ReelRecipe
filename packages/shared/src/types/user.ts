// packages/shared/src/types/user.ts

export interface User {
  id: string
  clerk_id: string
  email: string
  name: string
  avatar_url: string | null
  dietary_prefs: string[]   // ['vegan', 'gluten-free', ...]
  cuisine_prefs: string[]   // ['italian', 'japanese', ...]
  unit_system: 'metric' | 'imperial'
  created_at: string
  updated_at: string
}
