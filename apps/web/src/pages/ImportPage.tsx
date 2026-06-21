import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../stores/appStore'
import styles from './ImportPage.module.css'

const PLATFORM_HINTS = [
  { icon: '▶️', label: 'YouTube' },
  { icon: '🎵', label: 'TikTok' },
  { icon: '📸', label: 'Instagram' },
  { icon: '📘', label: 'Facebook' },
  { icon: '𝕏', label: 'X / Twitter' },
]

export function ImportPage() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const setActiveJobId = useAppStore((s) => s.setActiveJobId)

  async function handleImport() {
    const trimmed = url.trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/api/jobs/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmed }),
        credentials: 'include',
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail || `Request failed (${res.status})`)
      }
      const { data } = await res.json()
      setActiveJobId(data.jobId)
      navigate(`/processing/${data.jobId}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleImport()
  }

  return (
    <div className={styles.page}>
      <div className={styles.hero}>
        <h1 className={styles.heading}>
          Paste a cooking video.<br />Get a full recipe.
        </h1>
        <p className={styles.sub}>
          ReelRecipes extracts ingredients, steps, and nutrition from any cooking video
          — in under 60 seconds.
        </p>

        <div className={styles.inputRow}>
          <input
            className={styles.input}
            type="url"
            placeholder="https://youtube.com/watch?v=..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            autoFocus
          />
          <button
            className={styles.btn}
            onClick={handleImport}
            disabled={loading || !url.trim()}
          >
            {loading ? 'Importing…' : 'Extract Recipe'}
          </button>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.platforms}>
          {PLATFORM_HINTS.map((p) => (
            <span key={p.label} className={styles.platform}>
              {p.icon} {p.label}
            </span>
          ))}
        </div>
      </div>

      <div className={styles.features}>
        <div className={styles.feature}>
          <span className={styles.featureIcon}>🧄</span>
          <strong>Smart Pantry</strong>
          <span>Add ingredients you own. See what you can cook right now.</span>
        </div>
        <div className={styles.feature}>
          <span className={styles.featureIcon}>🤖</span>
          <strong>AI Suggestions</strong>
          <span>Let AI generate recipes from whatever's in your pantry.</span>
        </div>
        <div className={styles.feature}>
          <span className={styles.featureIcon}>👨‍🍳</span>
          <strong>Cook Mode</strong>
          <span>Full-screen step-by-step view with built-in timers.</span>
        </div>
      </div>
    </div>
  )
}
