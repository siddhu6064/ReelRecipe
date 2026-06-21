/**
 * components/ShoppingListPanel.tsx
 *
 * Displays a pantry-aware shopping list for a meal plan.
 * Groups missing ingredients by recipe, marks items already in pantry.
 * Used in MealPlannerPage and (optionally) the mobile planner tab.
 */

import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import styles from './ShoppingListPanel.module.css'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface ShoppingItem {
  name: string
  needed_for: string[]   // recipe titles
  in_pantry?: boolean
}

interface Props {
  planId: string
  /** Called when user closes/hides the panel */
  onClose?: () => void
}

export function ShoppingListPanel({ planId, onClose }: Props) {
  const { getToken } = useAuth()

  const { data, isLoading, error } = useQuery({
    queryKey: ['shopping', planId],
    queryFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API}/api/meal-plans/${planId}/shopping`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await res.json()
      return data as { items: ShoppingItem[]; total_count: number }
    },
    enabled: !!planId,
  })

  if (isLoading) {
    return (
      <div className={styles.panel}>
        <div className={styles.loading}>Building your shopping list…</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className={styles.panel}>
        <p className={styles.error}>Could not load shopping list.</p>
      </div>
    )
  }

  const needed = data.items.filter(i => !i.in_pantry)
  const have   = data.items.filter(i => i.in_pantry)

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h3 className={styles.title}>🛒 Shopping List</h3>
        <div className={styles.headerRight}>
          <span className={styles.count}>{needed.length} item{needed.length !== 1 ? 's' : ''} to buy</span>
          {onClose && <button className={styles.closeBtn} onClick={onClose}>✕</button>}
        </div>
      </div>

      {needed.length === 0 && (
        <div className={styles.allSet}>
          <span className={styles.allSetEmoji}>✓</span>
          <p>You have everything you need!</p>
        </div>
      )}

      {needed.length > 0 && (
        <ul className={styles.list}>
          {needed.map((item, i) => (
            <li key={i} className={styles.item}>
              <div className={styles.itemCheck} />
              <div className={styles.itemBody}>
                <span className={styles.itemName}>{item.name}</span>
                {item.needed_for.length > 0 && (
                  <span className={styles.neededFor}>
                    for {item.needed_for.join(', ')}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {have.length > 0 && (
        <details className={styles.haveSection}>
          <summary className={styles.haveSummary}>
            ✓ Already in pantry ({have.length})
          </summary>
          <ul className={styles.haveList}>
            {have.map((item, i) => (
              <li key={i} className={styles.haveItem}>{item.name}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
