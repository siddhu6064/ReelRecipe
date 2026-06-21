import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import { getRecipes } from '../api/client'
import type { Recipe } from '@reelrecipes/shared'
import styles from './CookbookPage.module.css'

const CUISINES = ['Italian','Japanese','Mexican','Indian','American','French','Chinese','Thai']
const DIFFS = ['easy','medium','hard'] as const

export function CookbookPage() {
  const { getToken } = useAuth()
  const [search, setSearch] = useState('')
  const [cuisine, setCuisine] = useState('')
  const [diff, setDiff] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['recipes', search, cuisine, diff, favsOnly],
    queryFn: async () => {
      const token = await getToken()
      const p: Record<string,string> = {}
      if (search) p.search = search
      if (cuisine) p.cuisine = cuisine
      if (diff) p.difficulty = diff
      if (favsOnly) p.favourites = 'true'
      p.apply_prefs = 'false'  // filter handled by search/UI
      return getRecipes(token, p)
    },
  })

  const recipes = data?.recipes ?? []

  const [favsOnly, setFavsOnly] = useState(false)

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>📖 Cookbook</h1>
        <Link to="/import" className={styles.importBtn}>+ Import Recipe</Link>
      </header>
      <div className={styles.filters}>
        <input className={styles.search} placeholder="Search…" value={search} onChange={e=>setSearch(e.target.value)} />
        <select className={styles.select} value={cuisine} onChange={e=>setCuisine(e.target.value)}>
          <option value="">All cuisines</option>
          {CUISINES.map(c=><option key={c}>{c}</option>)}
        </select>
        <select className={styles.select} value={diff} onChange={e=>setDiff(e.target.value)}>
          <option value="">All difficulties</option>
          {DIFFS.map(d=><option key={d} value={d}>{d[0].toUpperCase()+d.slice(1)}</option>)}
        </select>
        <button
          className={`${styles.favFilter} ${favsOnly ? styles.favFilterActive : ''}`}
          onClick={() => setFavsOnly(f => !f)}
        >
          {favsOnly ? '★' : '☆'} Starred
        </button>
      </div>
      {isLoading && <p className={styles.loading}>Loading…</p>}
      {!isLoading && recipes.length === 0 && (
        <div className={styles.empty}>
          <p>No recipes yet.</p>
          <Link to="/import" className={styles.emptyLink}>Import your first recipe →</Link>
        </div>
      )}
      <div className={styles.grid}>{recipes.map(r=><RecipeCard key={r.id} recipe={r}/>)}</div>
    </div>
  )
}

function RecipeCard({ recipe }: { recipe: Recipe }) {
  const t = recipe.total_time_minutes
  const timeLabel = t ? (t<60 ? `${t}m` : `${Math.floor(t/60)}h ${t%60}m`) : null
  return (
    <Link to={`/recipes/${recipe.id}`} className={styles.card}>
      {recipe.thumbnail_url
        ? <img className={styles.thumb} src={recipe.thumbnail_url} alt={recipe.title} />
        : <div className={styles.thumbPlaceholder}>🍳</div>}
      <div className={styles.cardBody}>
        <h3 className={styles.cardTitle}>{recipe.title}</h3>
        <div className={styles.cardMeta}>
          {recipe.cuisine && <span className={styles.tag}>{recipe.cuisine}</span>}
          {recipe.difficulty && <span className={`${styles.tag} ${styles[recipe.difficulty]}`}>{recipe.difficulty}</span>}
          {timeLabel && <span className={styles.time}>⏱ {timeLabel}</span>}
        </div>
        <div className={styles.tags}>{recipe.tags.slice(0,3).map(t=><span key={t} className={styles.dietTag}>{t}</span>)}</div>
      </div>
    </Link>
  )
}
