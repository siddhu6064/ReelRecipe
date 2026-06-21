import { useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import styles from './RecipePage.module.css'
import { UndoButton } from '../components/UndoButton'
import { IngredientList } from '../components/IngredientList'
import { NutritionPanel } from '../components/NutritionPanel'
import { AIChatPanel } from '../components/AIChatPanel'
import { SubstitutionModal } from '../components/SubstitutionModal'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type Difficulty = 'easy' | 'medium' | 'hard'
const DIFF_COLOR: Record<Difficulty, string> = {
  easy: '#6dbf85', medium: '#e8a84a', hard: '#ff6b6b',
}

interface Recipe {
  id: string; title: string; description: string | null
  cuisine: string | null; difficulty: Difficulty; servings: number
  total_time_minutes: number | null; thumbnail_url: string | null
  source_url: string; is_favourite: boolean; personal_notes: string | null
  is_edited: boolean
  ingredients: { name: string; quantity: number | null; unit: string | null; preparation: string | null; optional: boolean }[]
  steps: { order: number; text: string; timer_seconds: number | null }[]
  tags: string[]
  nutrition: { calories: number | null; protein_g: number | null; carbs_g: number | null; fat_g: number | null } | null
}

export function RecipePage() {
  const { recipeId } = useParams<{ recipeId: string }>()
  const navigate = useNavigate()
  const { getToken } = useAuth()
  const qc = useQueryClient()
  const [servings, setServings] = useState<number | null>(null)
  const [showNotes, setShowNotes] = useState(false)
  const [notesText, setNotesText] = useState('')
  const [subIngredient, setSubIngredient] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [chatMsg, setChatMsg] = useState('')
  const [chatHistory, setChatHistory] = useState<{role:string;content:string}[]>([])
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  async function authFetch(path: string, init: RequestInit = {}) {
    const token = await getToken()
    return fetch(`${API}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers as Record<string, string> ?? {}) },
    })
  }

  const { data: recipe, isLoading } = useQuery({
    queryKey: ['recipe', recipeId],
    queryFn: async () => {
      const r = await authFetch(`/api/recipes/${recipeId}`)
      const { data } = await r.json(); return data as Recipe
    },
    enabled: !!recipeId,
    onSuccess: (r) => { setNotesText(r.personal_notes ?? ''); setServings(null) },
  })

  // Favourite toggle
  const favMutation = useMutation({
    mutationFn: async (star: boolean) => {
      await authFetch(`/api/recipes/${recipeId}/favourite`, { method: star ? 'POST' : 'DELETE' })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recipe', recipeId] }),
  })

  // Save notes
  const notesMutation = useMutation({
    mutationFn: async () => {
      await authFetch(`/api/recipes/${recipeId}/notes`, {
        method: 'PUT', body: JSON.stringify({ notes: notesText || null }),
      })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['recipe', recipeId] }); setShowNotes(false) },
  })

  // Persist servings (triggers server-side rescaling)
  const servingsMutation = useMutation({
    mutationFn: async (newServings: number) => {
      await authFetch(`/api/recipes/${recipeId}`, {
        method: 'PUT', body: JSON.stringify({ servings: newServings }),
      })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['recipe', recipeId] }); setServings(null) },
  })

  // Reset to original
  const resetMutation = useMutation({
    mutationFn: async () => {
      await authFetch(`/api/recipes/${recipeId}/reset`, { method: 'POST' })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recipe', recipeId] }),
  })

  // Delete
  const deleteMutation = useMutation({
    mutationFn: async () => {
      await authFetch(`/api/recipes/${recipeId}`, { method: 'DELETE' })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['recipes'] }); navigate('/cookbook') },
  })

  // Visibility toggle
  const visibilityMutation = useMutation({
    mutationFn: async () => {
      await authFetch(`/api/recipes/${recipeId}/visibility`, { method: 'PATCH' })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recipe', recipeId] }),
  })

  // PDF download
  async function downloadPDF() {
    const token = await getToken()
    const r = await authFetch(`/api/recipes/${recipeId}/export/pdf`)
    if (!r.ok) return
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${recipe?.title ?? 'recipe'}.pdf`; a.click()
    URL.revokeObjectURL(url)
  }

  // Cost estimate
  const { data: cost } = useQuery({
    queryKey: ['recipe-cost', recipeId],
    queryFn: async () => {
      const r = await authFetch(`/api/recipes/${recipeId}/cost`)
      if (!r.ok) return null
      const { data } = await r.json()
      return data
    },
  })

  // Collaboration invite
  const [inviteLink, setInviteLink] = useState<string | null>(null)
  const inviteMutation = useMutation({
    mutationFn: async (role: 'viewer' | 'editor') => {
      const r = await authFetch(`/api/recipes/${recipeId}/invite`, { method: 'POST', body: JSON.stringify({ role }) })
      const { data } = await r.json()
      return data.invite_url as string
    },
    onSuccess: (url) => setInviteLink(url),
  })

  // Reorder
  const reorderMutation = useMutation({
    mutationFn: async ({ type, ids }: { type: 'ingredients' | 'steps'; ids: string[] }) => {
      await authFetch(`/api/recipes/${recipeId}/${type}/reorder`, {
        method: 'PUT', body: JSON.stringify({ ids }),
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recipe', recipeId] }),
  })

  function moveItem(
    items: { id: string }[],
    index: number,
    direction: 'up' | 'down',
    type: 'ingredients' | 'steps',
  ) {
    const newItems = [...items]
    const swap = direction === 'up' ? index - 1 : index + 1
    if (swap < 0 || swap >= newItems.length) return
    ;[newItems[index], newItems[swap]] = [newItems[swap], newItems[index]]
    reorderMutation.mutate({ type, ids: newItems.map(i => i.id) })
  }

  // AI chat
  async function sendChat() {
    if (!chatMsg.trim()) return
    const userMsg = { role: 'user', content: chatMsg }
    setChatHistory(h => [...h, userMsg])
    setChatMsg('')
    setChatLoading(true)
    try {
      const r = await authFetch(`/api/ai/chat/${recipeId}`, {
        method: 'POST', body: JSON.stringify({ message: chatMsg, history: chatHistory }),
      })
      const { data } = await r.json()
      setChatHistory(h => [...h, { role: 'assistant', content: data.reply }])
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    } catch { /* silent */ } finally { setChatLoading(false) }
  }

  if (isLoading) return <div className={styles.loading}>Loading recipe…</div>
  if (!recipe) return <div className={styles.error}>Recipe not found.</div>

  const displayServings = servings ?? recipe.servings
  const scale = displayServings / recipe.servings
  const timeLabel = recipe.total_time_minutes
    ? recipe.total_time_minutes < 60 ? `${recipe.total_time_minutes}m`
      : `${Math.floor(recipe.total_time_minutes / 60)}h ${recipe.total_time_minutes % 60}m`
    : null

  function scaleQty(qty: number | null) {
    if (qty == null) return ''
    const s = Math.round(qty * scale * 100) / 100
    return s % 1 === 0 ? String(s) : s.toFixed(1)
  }

  return (
    <div className={styles.page}>
      {recipe.thumbnail_url && <img className={styles.hero} src={recipe.thumbnail_url} alt={recipe.title} />}

      <div className={styles.content}>
        {/* Title + actions */}
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{recipe.title}</h1>
          <div className={styles.actionBar}>
            <button
              className={`${styles.favBtn} ${recipe.is_favourite ? styles.favActive : ''}`}
              onClick={() => favMutation.mutate(!recipe.is_favourite)}
              title={recipe.is_favourite ? 'Remove from favourites' : 'Add to favourites'}
            >
              {recipe.is_favourite ? '★' : '☆'}
            </button>
            <button className={styles.notesBtn} onClick={() => setShowNotes(s => !s)} title="Personal notes">
              📝{recipe.personal_notes ? ' •' : ''}
            </button>
            {recipe.is_edited && (
              <>
                <UndoButton recipeId={recipe.id} />
                <button
                  className={styles.resetBtn}
                  onClick={() => { if (confirm('Reset to original AI extraction? Your edits will be lost.')) resetMutation.mutate() }}
                  title="Reset to original"
                  disabled={resetMutation.isPending}
                >
                  ↺ Reset
                </button>
              </>
            )}
            <button
              className={`${styles.publishBtn} ${recipe.is_public ? styles.publishBtnActive : ''}`}
              onClick={() => visibilityMutation.mutate()}
              disabled={visibilityMutation.isPending}
              title={recipe.is_public ? 'Make private' : 'Share publicly'}
            >
              {recipe.is_public ? '🌍 Public' : '🔒 Private'}
            </button>
            <button className={styles.pdfBtn} onClick={downloadPDF} title="Download PDF">📄 PDF</button>
            <a href={recipe.source_url} target="_blank" rel="noopener noreferrer" className={styles.sourceLink}>▶ Watch</a>
            <button className={styles.deleteBtn} onClick={() => { if (confirm('Delete this recipe?')) deleteMutation.mutate() }}>🗑</button>
          </div>
        </div>

        {/* Edited badge */}
        {recipe.is_edited && <div className={styles.editedBadge}>✏️ Edited from original</div>}
        {cost?.total_cost != null && (
          <div className={styles.costBadge}>
            💰 Est. cost: ${cost.total_cost.toFixed(2)}
            <span className={styles.costCoverage}> ({Math.round(cost.coverage_pct * 100)}% priced)</span>
          </div>
        )}

        {/* Personal notes panel */}
        {showNotes && (
          <div className={styles.notesPanel}>
            <textarea
              className={styles.notesArea}
              placeholder="Your cooking notes, tweaks, substitutions…"
              value={notesText}
              onChange={e => setNotesText(e.target.value)}
              rows={4}
            />
            <div className={styles.notesActions}>
              <button className={styles.notesSave} onClick={() => notesMutation.mutate()} disabled={notesMutation.isPending}>
                {notesMutation.isPending ? 'Saving…' : 'Save notes'}
              </button>
              <button className={styles.notesCancel} onClick={() => setShowNotes(false)}>Cancel</button>
            </div>
          </div>
        )}
        {recipe.personal_notes && !showNotes && (
          <div className={styles.notesDisplay} onClick={() => setShowNotes(true)}>
            📝 {recipe.personal_notes}
          </div>
        )}

        {/* Meta */}
        <div className={styles.meta}>
          {recipe.cuisine && <span className={styles.badge}>{recipe.cuisine}</span>}
          <span className={styles.badge} style={{ color: DIFF_COLOR[recipe.difficulty] }}>{recipe.difficulty}</span>
          {timeLabel && <span className={styles.badge}>⏱ {timeLabel}</span>}
          {recipe.tags.slice(0, 3).map(t => <span key={t} className={styles.dietBadge}>{t}</span>)}
        </div>

        {recipe.description && <p className={styles.desc}>{recipe.description}</p>}

        {/* Servings scaler */}
        <div className={styles.servingsRow}>
          <span className={styles.servingsLabel}>Servings</span>
          <button className={styles.scaleBtn} onClick={() => setServings(s => Math.max(1, (s ?? recipe.servings) - 1))}>−</button>
          <span className={styles.servingsNum}>{displayServings}</span>
          <button className={styles.scaleBtn} onClick={() => setServings(s => (s ?? recipe.servings) + 1)}>+</button>
          {servings && servings !== recipe.servings && (
            <>
              <button
                className={styles.scaleSaveBtn}
                onClick={() => servingsMutation.mutate(displayServings)}
                disabled={servingsMutation.isPending}
                title="Save scaled quantities to recipe"
              >
                {servingsMutation.isPending ? '…' : '💾 Save'}
              </button>
              <button className={styles.scaleResetBtn} onClick={() => setServings(null)}>Reset</button>
            </>
          )}
        </div>

        <div className={styles.columns}>
          {/* Ingredients */}
          <div>
            <h2 className={styles.sectionTitle}>Ingredients</h2>
            <IngredientList
              ingredients={recipe.ingredients}
              scale={scale}
              onReorder={ids => reorderMutation.mutate({ type: 'ingredients', ids })}
              onSubstitute={name => setSubIngredient(name)}
            />
          </div>

          {/* Nutrition */}
          <NutritionPanel nutrition={recipe.nutrition} scale={scale} />
        </div>

        {/* Steps */}
        <h2 className={styles.sectionTitle}>Instructions</h2>
        <ol className={styles.stepList}>
          {recipe.steps.map((step, i) => (
            <li key={step.id} className={styles.step}>
              <div className={styles.reorderBtnsV}>
                <button className={styles.moveBtn} disabled={i === 0} onClick={() => moveItem(recipe.steps, i, 'up', 'steps')}>↑</button>
                <button className={styles.moveBtn} disabled={i === recipe.steps.length - 1} onClick={() => moveItem(recipe.steps, i, 'down', 'steps')}>↓</button>
              </div>
              <div className={styles.stepNum}>{step.order}</div>
              <div className={styles.stepBody}>
                <p className={styles.stepText}>{step.text}</p>
                {step.timer_seconds && (
                  <span className={styles.timerBadge}>⏱ {Math.round(step.timer_seconds / 60)} min</span>
                )}
              </div>
            </li>
          ))}
        </ol>

        {/* Collaboration */}
        <div className={styles.collabSection}>
          <div className={styles.collabRow}>
            <span className={styles.collabTitle}>👥 Share recipe</span>
            <button className={styles.inviteBtn} onClick={() => inviteMutation.mutate('viewer')} disabled={inviteMutation.isPending}>
              Invite viewer
            </button>
            <button className={styles.inviteBtn} onClick={() => inviteMutation.mutate('editor')} disabled={inviteMutation.isPending}>
              Invite editor
            </button>
          </div>
          {inviteLink && (
            <div className={styles.inviteLink}>
              <input className={styles.inviteLinkInput} readOnly value={inviteLink} onClick={e => (e.target as HTMLInputElement).select()} />
              <button className={styles.copyBtn} onClick={() => navigator.clipboard.writeText(inviteLink)}>Copy</button>
            </div>
          )}
        </div>

        <AIChatPanel recipeId={recipe.id} />
        {subIngredient && (
          <SubstitutionModal
            recipeId={recipe.id}
            ingredientName={subIngredient}
            onClose={() => setSubIngredient(null)}
          />
        )}
        <div style={{ height: 40 }} />
      </div>
    </div>
  )
}
