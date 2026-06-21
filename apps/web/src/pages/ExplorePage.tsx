import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import { useTranslation } from 'react-i18next'
import styles from './ExplorePage.module.css'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface PublicRecipe {
  id: string; title: string; cuisine: string | null; difficulty: string
  total_time_minutes: number | null; thumbnail_url: string | null
  tags: string[]; view_count: number; share_count: number
  user_id: string; is_public: boolean
  servings: number; ingredients: { name: string }[]
}

const DIFF_COLOR: Record<string, string> = { easy: '#6dbf85', medium: '#e8a84a', hard: '#ff6b6b' }

export function ExplorePage() {
  const { t } = useTranslation()
  const { getToken } = useAuth()
  const qc = useQueryClient()
  const [tab, setTab] = useState<'recent' | 'trending'>('trending')
  const [search, setSearch] = useState('')

  async function authFetch(path: string, init: RequestInit = {}) {
    const token = await getToken()
    return fetch(`${API}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  }

  const endpoint = tab === 'trending'
    ? '/api/recipes/explore/trending'
    : '/api/recipes/explore'

  const { data, isLoading } = useQuery({
    queryKey: ['explore', tab],
    queryFn: async () => {
      const r = await authFetch(endpoint)
      const json = await r.json()
      return (json.data?.recipes ?? json.data) as PublicRecipe[]
    },
  })

  const duplicateMutation = useMutation({
    mutationFn: async (recipeId: string) => {
      const r = await authFetch(`/api/recipes/${recipeId}/duplicate`, { method: 'POST' })
      if (!r.ok) throw new Error('Failed to save')
      return r.json()
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['recipes'] }) },
  })

  const recipes = (data ?? []).filter(r =>
    !search || r.title.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>🌍 {t('explore.title')}</h1>
        <input
          className={styles.search}
          placeholder="Search public recipes…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </header>

      <div className={styles.tabs}>
        <button className={`${styles.tab} ${tab === 'trending' ? styles.tabActive : ''}`} onClick={() => setTab('trending')}>
          🔥 {t('explore.trending')}
        </button>
        <button className={`${styles.tab} ${tab === 'recent' ? styles.tabActive : ''}`} onClick={() => setTab('recent')}>
          🆕 {t('explore.recent')}
        </button>
      </div>

      {isLoading && <p className={styles.loading}>{t('common.loading')}</p>}

      {!isLoading && recipes.length === 0 && (
        <div className={styles.empty}>
          <p>{t('explore.empty')}</p>
          <p className={styles.emptyHint}>Be the first — make a recipe public from your cookbook.</p>
        </div>
      )}

      <div className={styles.grid}>
        {recipes.map(recipe => (
          <div key={recipe.id} className={styles.card}>
            {recipe.thumbnail_url
              ? <img className={styles.thumb} src={recipe.thumbnail_url} alt={recipe.title} />
              : <div className={styles.thumbPlaceholder}>🍳</div>}
            <div className={styles.cardBody}>
              <h3 className={styles.cardTitle}>{recipe.title}</h3>
              <div className={styles.cardMeta}>
                {recipe.cuisine && <span className={styles.tag}>{recipe.cuisine}</span>}
                <span className={styles.tag} style={{ color: DIFF_COLOR[recipe.difficulty] }}>
                  {recipe.difficulty}
                </span>
                {recipe.total_time_minutes && (
                  <span className={styles.tag}>
                    ⏱ {recipe.total_time_minutes < 60 ? `${recipe.total_time_minutes}m` : `${Math.floor(recipe.total_time_minutes / 60)}h`}
                  </span>
                )}
              </div>

              <div className={styles.stats}>
                {recipe.view_count > 0 && (
                  <span className={styles.stat}>👁 {recipe.view_count}</span>
                )}
                {recipe.share_count > 0 && (
                  <span className={styles.stat}>📋 {recipe.share_count} saved</span>
                )}
                <span className={styles.stat}>{recipe.ingredients.length} ingredients</span>
              </div>

              <div className={styles.cardActions}>
                <button
                  className={styles.saveBtn}
                  onClick={() => duplicateMutation.mutate(recipe.id)}
                  disabled={duplicateMutation.isPending}
                >
                  {duplicateMutation.isPending ? '…' : `📋 ${t('explore.duplicate')}`}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
