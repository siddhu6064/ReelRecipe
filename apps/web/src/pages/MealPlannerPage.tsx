import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import styles from './MealPlannerPage.module.css'
import { ShoppingListPanel } from '../components/ShoppingListPanel'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
const SLOTS = ['breakfast','lunch','dinner'] as const

async function apiFetch<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
  if (res.status === 204) return null as T
  const json = await res.json()
  if (!res.ok) throw new Error(json?.detail ?? `${res.status}`)
  return json.data as T
}

interface Meal { id: string; recipe_id: string; recipe_title: string; slot: string; servings_override: number | null }
interface DayPlan { day_index: number; meals: Meal[] }
interface Plan { id: string; title: string; days: DayPlan[]; is_active: boolean }
interface ShoppingItem { name: string; needed_for: string[] }

export function MealPlannerPage() {
  const { getToken } = useAuth()
  const qc = useQueryClient()
  const [showShopping, setShowShopping] = useState(false)

  const { data: plan, isLoading } = useQuery({
    queryKey: ['active-plan'],
    queryFn: async () => {
      const t = await getToken()
      return apiFetch<Plan>('/api/meal-plans/active', t).catch(() => null)
    },
  })

  const { data: shopping } = useQuery({
    queryKey: ['shopping', plan?.id],
    queryFn: async () => {
      const t = await getToken()
      return apiFetch<{ items: ShoppingItem[]; total_count: number }>(`/api/meal-plans/${plan!.id}/shopping`, t)
    },
    enabled: !!plan?.id && showShopping,
  })

  const createPlan = useMutation({
    mutationFn: async () => {
      const t = await getToken()
      return apiFetch<Plan>('/api/meal-plans', t, { method: 'POST', body: JSON.stringify({ title: 'This Week' }) })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['active-plan'] }),
  })

  if (isLoading) return <div className={styles.loading}>Loading planner…</div>

  if (!plan) return (
    <div className={styles.empty}>
      <h1 className={styles.title}>📅 Meal Planner</h1>
      <p>Plan your meals for the week.</p>
      <button className={styles.createBtn} onClick={() => createPlan.mutate()} disabled={createPlan.isPending}>
        {createPlan.isPending ? 'Creating…' : 'Create this week\'s plan'}
      </button>
    </div>
  )

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>📅 {plan.title}</h1>
        <button className={styles.shoppingBtn} onClick={() => setShowShopping(s => !s)}>
          🛒 {showShopping ? 'Hide shopping list' : 'Shopping list'}
        </button>
      </div>

      {showShopping && shopping && (
        <div className={styles.shoppingPanel}>
          <h2 className={styles.shoppingTitle}>Shopping list ({shopping.total_count} items)</h2>
          {shopping.items.length === 0
            ? <p className={styles.shoppingEmpty}>You have everything you need! ✓</p>
            : <ul className={styles.shoppingList}>
                {shopping.items.map((item, i) => (
                  <li key={i} className={styles.shoppingItem}>
                    <span className={styles.shoppingName}>{item.name}</span>
                    <span className={styles.shoppingFor}>for: {item.needed_for.join(', ')}</span>
                  </li>
                ))}
              </ul>}
        </div>
      )}

      <div className={styles.calendar}>
        {DAYS.map((dayName, dayIndex) => {
          const day = plan.days.find(d => d.day_index === dayIndex)
          const meals = day?.meals ?? []
          return (
            <div key={dayIndex} className={styles.dayCol}>
              <div className={styles.dayName}>{dayName}</div>
              {SLOTS.map(slot => {
                const meal = meals.find(m => m.slot === slot)
                return (
                  <div key={slot} className={styles.slot}>
                    <div className={styles.slotLabel}>{slot}</div>
                    {meal
                      ? <div className={styles.mealCard}>{meal.recipe_title}</div>
                      : <div className={styles.emptySlot}>+</div>}
                  </div>
                )
              })}
            </div>
          )
        })}
      </div>
    </div>
  )
}
