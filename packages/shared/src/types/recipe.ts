// packages/shared/src/types/recipe.ts

export type Platform = 'youtube' | 'instagram' | 'tiktok' | 'facebook' | 'twitter' | 'unknown'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type IngredientCategory =
  | 'produce' | 'meat' | 'seafood' | 'dairy' | 'grains'
  | 'pantry' | 'spices' | 'frozen' | 'beverages' | 'other'

export interface RecipeIngredient {
  name: string
  quantity: number | null
  unit: string | null
  preparation: string | null
  optional: boolean
}

export interface RecipeStep {
  order: number
  text: string
  timer_seconds: number | null
}

export interface NutritionInfo {
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  fiber_g: number | null
  sugar_g: number | null
  sodium_mg: number | null
  fetched_at: string | null
}

export interface Recipe {
  id: string
  user_id: string
  job_id: string | null
  source_url: string
  platform: Platform
  thumbnail_url: string | null
  video_title: string | null
  title: string
  description: string | null
  cuisine: string | null
  difficulty: Difficulty
  servings: number
  prep_time_minutes: number | null
  cook_time_minutes: number | null
  total_time_minutes: number | null
  ingredients: RecipeIngredient[]
  steps: RecipeStep[]
  tags: string[]
  nutrition: NutritionInfo | null
  is_edited: boolean
  notes: string | null
  created_at: string
  updated_at: string
}

export interface PantryItem {
  id: string
  name: string
  quantity: number | null
  unit: string | null
  category: IngredientCategory
  added_at: string
  updated_at: string
}

export interface Pantry {
  id: string
  user_id: string
  items: PantryItem[]
  updated_at: string
}

export interface PantryMatchResult {
  recipe_id: string
  title: string
  thumbnail_url: string | null
  cuisine: string | null
  difficulty: Difficulty
  total_time_minutes: number | null
  tags: string[]
  match_pct: number
  matched_count: number
  total_required: number
  matched_ingredients: string[]
  missing_ingredients: string[]
}
