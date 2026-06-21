/**
 * components/SubstitutionModal.tsx
 *
 * Modal that displays AI-generated substitutions for a missing or
 * undesired ingredient. Triggered by clicking ↔ on an ingredient row.
 */

import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import styles from './SubstitutionModal.module.css'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface Substitution { name: string; notes: string; ratio?: string }

interface Props {
  recipeId: string
  ingredientName: string
  onClose: () => void
}

export function SubstitutionModal({ recipeId, ingredientName, onClose }: Props) {
  const { getToken } = useAuth()
  const [subs, setSubs] = useState<Substitution[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const token = await getToken()
        const res = await fetch(`${API}/api/ai/substitute`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify({ recipe_id: recipeId, ingredient_name: ingredientName }),
        })
        if (!res.ok) throw new Error('API error')
        const { data } = await res.json()
        setSubs(data.substitutions ?? [])
      } catch {
        setError(true)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [ingredientName])

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <div>
            <h3 className={styles.title}>Substitutes for</h3>
            <p className={styles.ingredient}>{ingredientName}</p>
          </div>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        {loading && (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <p>Asking AI…</p>
          </div>
        )}

        {error && (
          <p className={styles.error}>Could not load substitutions. Try again.</p>
        )}

        {!loading && !error && subs.length === 0 && (
          <p className={styles.empty}>No substitutions found for this ingredient.</p>
        )}

        {!loading && !error && subs.length > 0 && (
          <ul className={styles.list}>
            {subs.map((sub, i) => (
              <li key={i} className={styles.item}>
                <div className={styles.itemHeader}>
                  <span className={styles.subName}>{sub.name}</span>
                  {sub.ratio && <span className={styles.ratio}>{sub.ratio}</span>}
                </div>
                <p className={styles.notes}>{sub.notes}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
