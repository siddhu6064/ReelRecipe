/**
 * components/NutritionPanel.tsx
 *
 * Displays per-serving macro breakdown (calories, protein, carbs, fat).
 * Accepts an optional scale multiplier for servings adjustment.
 * Returns null if no nutrition data is available.
 */

import styles from './NutritionPanel.module.css'

export interface Nutrition {
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  fiber_g?: number | null
  sugar_g?: number | null
  sodium_mg?: number | null
}

interface Props {
  nutrition: Nutrition | null | undefined
  scale?: number   // multiply values by this factor (default 1)
  compact?: boolean  // hide heading and description line
}

const MACROS = [
  { key: 'calories' as const,  label: 'Calories', unit: 'kcal', accent: true  },
  { key: 'protein_g' as const, label: 'Protein',  unit: 'g'                   },
  { key: 'carbs_g' as const,   label: 'Carbs',    unit: 'g'                   },
  { key: 'fat_g' as const,     label: 'Fat',       unit: 'g'                   },
  { key: 'fiber_g' as const,   label: 'Fibre',    unit: 'g'                   },
]

export function NutritionPanel({ nutrition, scale = 1, compact = false }: Props) {
  if (!nutrition) return null

  const rows = MACROS
    .map(m => ({ ...m, value: nutrition[m.key] }))
    .filter(m => m.value != null)

  if (rows.length === 0) return null

  return (
    <div className={styles.panel}>
      {!compact && (
        <div className={styles.header}>
          <h3 className={styles.title}>Nutrition</h3>
          <span className={styles.subtitle}>per serving</span>
        </div>
      )}
      <div className={styles.grid}>
        {rows.map(macro => (
          <div
            key={macro.key}
            className={`${styles.card} ${macro.accent ? styles.cardAccent : ''}`}
          >
            <div className={styles.value}>
              {Math.round(macro.value! * scale)}
              <span className={styles.unit}>{macro.unit}</span>
            </div>
            <div className={styles.label}>{macro.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
