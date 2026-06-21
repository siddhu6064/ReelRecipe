/**
 * components/IngredientList.tsx
 *
 * Reusable ingredient list with:
 *  - Quantity scaling (passed in as a scale factor)
 *  - Up/down reorder buttons (calls onReorder callback)
 *  - Substitution trigger (calls onSubstitute callback)
 *  - Optional badge on flagged ingredients
 */

import styles from './IngredientList.module.css'

export interface Ingredient {
  id: string
  name: string
  quantity: number | null
  unit: string | null
  preparation: string | null
  optional: boolean
}

interface Props {
  ingredients: Ingredient[]
  scale?: number                                     // multiply quantities by this factor (default 1)
  onReorder?: (ids: string[]) => void               // called with new ordered ID array
  onSubstitute?: (ingredientName: string) => void   // called when ↔ is clicked
  readOnly?: boolean                                 // hide reorder + substitute buttons
}

function scaleQty(qty: number | null, scale: number): string {
  if (qty == null) return ''
  const v = Math.round(qty * scale * 100) / 100
  return v % 1 === 0 ? String(v) : v.toFixed(1)
}

function move(arr: string[], i: number, dir: 'up' | 'down'): string[] {
  const next = [...arr]
  const j = dir === 'up' ? i - 1 : i + 1
  if (j < 0 || j >= next.length) return arr
  ;[next[i], next[j]] = [next[j], next[i]]
  return next
}

export function IngredientList({
  ingredients,
  scale = 1,
  onReorder,
  onSubstitute,
  readOnly = false,
}: Props) {
  return (
    <ul className={styles.list}>
      {ingredients.map((ing, i) => (
        <li
          key={ing.id}
          className={`${styles.row} ${ing.optional ? styles.optional : ''}`}
        >
          {/* Reorder arrows */}
          {!readOnly && onReorder && (
            <div className={styles.arrows}>
              <button
                className={styles.arrowBtn}
                disabled={i === 0}
                onClick={() => onReorder(move(ingredients.map(x => x.id), i, 'up'))}
                title="Move up"
              >↑</button>
              <button
                className={styles.arrowBtn}
                disabled={i === ingredients.length - 1}
                onClick={() => onReorder(move(ingredients.map(x => x.id), i, 'down'))}
                title="Move down"
              >↓</button>
            </div>
          )}

          {/* Quantity */}
          <span className={styles.qty}>
            {scaleQty(ing.quantity, scale)}{ing.unit ? ` ${ing.unit}` : ''}
          </span>

          {/* Name */}
          <span className={styles.name}>
            {ing.name}
            {ing.preparation && <span className={styles.prep}>, {ing.preparation}</span>}
            {ing.optional && <span className={styles.optBadge}> optional</span>}
          </span>

          {/* Substitute button */}
          {!readOnly && onSubstitute && (
            <button
              className={styles.subBtn}
              onClick={() => onSubstitute(ing.name)}
              title={`Find substitutes for ${ing.name}`}
            >
              ↔
            </button>
          )}
        </li>
      ))}
    </ul>
  )
}
