import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import { useTranslation } from 'react-i18next'
import styles from './StatsPage.module.css'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface Stats {
  total_recipes: number; public_recipes: number; unique_cuisines: number
  top_cuisines: string[]; top_tags: string[]; favourite_ingredient: string | null
  cook_sessions: number; most_cooked_cuisine: string | null
  recipes_this_month: number; recipes_this_year: number
  avg_cook_time_minutes: number | null; current_streak_days: number
  generated_at: string
}

export function StatsPage() {
  const { getToken } = useAuth()
  const { t } = useTranslation()

  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: async () => {
      const token = await getToken()
      const r = await fetch(`${API}/api/users/me/stats`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await r.json()
      return data as Stats
    },
  })

  if (isLoading) return <div className={styles.loading}>Crunching your cooking stats…</div>
  if (!stats) return null

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        {/* Header */}
        <div className={styles.header}>
          <span className={styles.headerEmoji}>👨‍🍳</span>
          <h1 className={styles.heading}>Your Cooking Wrapped</h1>
          <p className={styles.subheading}>Everything you've cooked with ReelRecipes</p>
        </div>

        {/* Big stats row */}
        <div className={styles.bigRow}>
          <StatBlock value={stats.total_recipes} label="Recipes Saved" emoji="📖" accent />
          <StatBlock value={stats.cook_sessions} label="Cook Sessions" emoji="🍳" />
          <StatBlock value={stats.unique_cuisines} label="Cuisines Tried" emoji="🌍" />
        </div>

        <div className={styles.divider} />

        {/* Detail stats */}
        <div className={styles.detailGrid}>
          {stats.favourite_ingredient && (
            <DetailCard emoji="❤️" label="Favourite ingredient" value={stats.favourite_ingredient} />
          )}
          {stats.most_cooked_cuisine && (
            <DetailCard emoji="🏆" label="Most cooked cuisine" value={stats.most_cooked_cuisine} />
          )}
          {stats.avg_cook_time_minutes && (
            <DetailCard emoji="⏱" label="Avg cook time"
              value={stats.avg_cook_time_minutes < 60
                ? `${stats.avg_cook_time_minutes}m`
                : `${Math.floor(stats.avg_cook_time_minutes / 60)}h ${stats.avg_cook_time_minutes % 60}m`} />
          )}
          {stats.current_streak_days > 0 && (
            <DetailCard emoji="🔥" label="Cooking streak" value={`${stats.current_streak_days} day${stats.current_streak_days > 1 ? 's' : ''}`} />
          )}
          <DetailCard emoji="📅" label="Recipes this month" value={String(stats.recipes_this_month)} />
          <DetailCard emoji="🌟" label="Public recipes" value={String(stats.public_recipes)} />
        </div>

        {/* Top cuisines */}
        {stats.top_cuisines.length > 0 && (
          <div className={styles.tagsSection}>
            <h3 className={styles.tagsLabel}>Cuisines explored</h3>
            <div className={styles.tags}>
              {stats.top_cuisines.map(c => <span key={c} className={styles.tag}>{c}</span>)}
            </div>
          </div>
        )}

        {/* Top tags */}
        {stats.top_tags.length > 0 && (
          <div className={styles.tagsSection}>
            <h3 className={styles.tagsLabel}>Favourite recipe styles</h3>
            <div className={styles.tags}>
              {stats.top_tags.map(t => <span key={t} className={`${styles.tag} ${styles.tagAccent}`}>#{t}</span>)}
            </div>
          </div>
        )}

        <div className={styles.footer}>
          Generated {new Date(stats.generated_at).toLocaleDateString()}
        </div>
      </div>
    </div>
  )
}

function StatBlock({ value, label, emoji, accent }: { value: number; label: string; emoji: string; accent?: boolean }) {
  return (
    <div className={`${styles.statBlock} ${accent ? styles.statBlockAccent : ''}`}>
      <div className={styles.statEmoji}>{emoji}</div>
      <div className={`${styles.statValue} ${accent ? styles.statValueAccent : ''}`}>{value}</div>
      <div className={styles.statLabel}>{label}</div>
    </div>
  )
}

function DetailCard({ emoji, label, value }: { emoji: string; label: string; value: string }) {
  return (
    <div className={styles.detailCard}>
      <span className={styles.detailEmoji}>{emoji}</span>
      <div>
        <div className={styles.detailValue}>{value}</div>
        <div className={styles.detailLabel}>{label}</div>
      </div>
    </div>
  )
}
