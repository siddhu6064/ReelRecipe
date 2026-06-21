/**
 * components/AIChatPanel.tsx
 *
 * Self-contained AI chat panel for discussing a specific recipe.
 * Manages its own message history and API calls internally.
 * Can be dropped into any recipe page with a single prop.
 */

import { useRef, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import styles from './AIChatPanel.module.css'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface Message { role: 'user' | 'assistant'; content: string }

interface Props {
  recipeId: string
  /** Suggested chips shown when chat is empty */
  suggestions?: string[]
}

const DEFAULT_SUGGESTIONS = [
  'Can I make this dairy-free?',
  'What can I substitute for the main protein?',
  'How do I scale this for a crowd?',
  'What wine pairs well with this?',
]

export function AIChatPanel({ recipeId, suggestions = DEFAULT_SUGGESTIONS }: Props) {
  const { getToken } = useAuth()
  const [open, setOpen] = useState(false)
  const [history, setHistory] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  async function send(text?: string) {
    const msg = (text ?? input).trim()
    if (!msg || loading) return
    setInput('')
    setHistory(h => [...h, { role: 'user', content: msg }])
    setLoading(true)

    try {
      const token = await getToken()
      const res = await fetch(`${API}/api/ai/chat/${recipeId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ message: msg, history }),
      })
      const { data } = await res.json()
      setHistory(h => [...h, { role: 'assistant', content: data.reply }])
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    } catch {
      setHistory(h => [...h, { role: 'assistant', content: 'Sorry, something went wrong. Try again.' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.wrap}>
      <button className={styles.toggle} onClick={() => setOpen(o => !o)}>
        💬 {open ? 'Close chat' : 'Ask AI about this recipe'}
      </button>

      {open && (
        <div className={styles.panel}>
          {/* Message history */}
          <div className={styles.history}>
            {history.length === 0 && (
              <div className={styles.empty}>
                <p className={styles.emptyHint}>Ask anything about this recipe.</p>
                <div className={styles.chips}>
                  {suggestions.map(s => (
                    <button key={s} className={styles.chip} onClick={() => send(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {history.map((m, i) => (
              <div
                key={i}
                className={`${styles.msg} ${m.role === 'user' ? styles.userMsg : styles.aiMsg}`}
              >
                {m.content}
              </div>
            ))}

            {loading && (
              <div className={`${styles.msg} ${styles.aiMsg} ${styles.typing}`}>
                <span />
                <span />
                <span />
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Input */}
          <div className={styles.inputRow}>
            <input
              className={styles.input}
              placeholder="Ask a question…"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && send()}
              disabled={loading}
            />
            <button
              className={styles.sendBtn}
              onClick={() => send()}
              disabled={!input.trim() || loading}
            >
              Send
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
