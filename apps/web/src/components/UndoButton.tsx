/**
 * components/UndoButton.tsx
 *
 * Floating undo button shown on RecipePage when the recipe has edit history.
 * Supports Cmd+Z / Ctrl+Z keyboard shortcut.
 */

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import styles from './UndoButton.module.css'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface HistoryEntry {
  snapshot_id: string
  label: string
  created_at: string
}

interface Props {
  recipeId: string
}

export function UndoButton({ recipeId }: Props) {
  const { getToken } = useAuth()
  const qc = useQueryClient()
  const [showHistory, setShowHistory] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)

  async function authFetch(path: string, init: RequestInit = {}) {
    const token = await getToken()
    return fetch(`${API}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  }

  const { data: history = [] } = useQuery({
    queryKey: ['recipe-history', recipeId],
    queryFn: async () => {
      const r = await authFetch(`/api/recipes/${recipeId}/history`)
      const { data } = await r.json()
      return data as HistoryEntry[]
    },
  })

  const undoMutation = useMutation({
    mutationFn: async () => {
      const r = await authFetch(`/api/recipes/${recipeId}/undo`, { method: 'POST' })
      if (!r.ok) throw new Error('Nothing to undo')
      const { undid } = await r.json()
      return undid as string
    },
    onSuccess: (undid) => {
      qc.invalidateQueries({ queryKey: ['recipe', recipeId] })
      qc.invalidateQueries({ queryKey: ['recipe-history', recipeId] })
      setFeedback(`Undid: ${undid}`)
      setTimeout(() => setFeedback(null), 2500)
      setShowHistory(false)
    },
    onError: () => {
      setFeedback('Nothing to undo')
      setTimeout(() => setFeedback(null), 1500)
    },
  })

  // Cmd+Z / Ctrl+Z keyboard shortcut
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        if (history.length > 0) undoMutation.mutate()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [history.length])

  if (history.length === 0) return null

  return (
    <div className={styles.wrap}>
      {feedback && <div className={styles.feedback}>{feedback}</div>}

      <div className={styles.btnGroup}>
        <button
          className={styles.undoBtn}
          onClick={() => undoMutation.mutate()}
          disabled={undoMutation.isPending}
          title="Undo last edit (⌘Z)"
        >
          {undoMutation.isPending ? '…' : '↩ Undo'}
        </button>
        <button
          className={styles.historyBtn}
          onClick={() => setShowHistory(s => !s)}
          title="Edit history"
        >
          {history.length}
        </button>
      </div>

      {showHistory && (
        <div className={styles.historyPanel}>
          <div className={styles.historyHeader}>Edit history</div>
          {history.map((entry, i) => (
            <div key={entry.snapshot_id} className={styles.historyEntry}>
              <span className={styles.historyLabel}>{entry.label}</span>
              <span className={styles.historyTime}>
                {new Date(entry.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          ))}
          <div className={styles.historyNote}>
            Click ↩ Undo to restore step-by-step · ⌘Z shortcut
          </div>
        </div>
      )}
    </div>
  )
}
