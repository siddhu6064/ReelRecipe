import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import { getPantryMatch, suggestRecipes } from '../api/client'
import type { PantryMatchResult, Recipe } from '@reelrecipes/shared'
import styles from './DiscoverPage.module.css'

export function DiscoverPage() {
  const { getToken } = useAuth()
  const [tab, setTab] = useState<'match'|'suggest'|'community'>('match')

  const { data: matches, isLoading: matchLoading } = useQuery({
    queryKey: ['pantry-match'],
    queryFn: async () => { const t = await getToken(); return getPantryMatch(t) },
    enabled: tab === 'match',
  })

  const suggestMutation = useMutation({
    mutationFn: async () => {
      const t = await getToken()
      return suggestRecipes({ dietary_prefs: [], cuisine_prefs: [], max_recipes: 5 }, t)
    },
  })

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>✨ Discover</h1>
      <p className={styles.sub}>See what you can cook — or let AI invent something new.</p>

      <div className={styles.tabs}>
        <button className={`${styles.tab} ${tab==='match'?styles.active:''}`} onClick={()=>setTab('match')}>
          🎯 What can I cook?
        </button>
        <button className={`${styles.tab} ${tab==='suggest'?styles.active:''}`} onClick={()=>setTab('suggest')}>
          🤖 AI suggestions
        </button>
        <button className={`${styles.tab} ${tab==='community'?styles.active:''}`} onClick={()=>setTab('community')}>
          🌍 Community
        </button>
      </div>

      {tab === 'match' && (
        <div>
          {matchLoading && <p className={styles.loading}>Matching your pantry…</p>}
          {!matchLoading && (matches ?? []).length === 0 && (
            <div className={styles.empty}>
              <p>No recipes to match yet.</p>
              <Link to="/import" className={styles.link}>Import recipes →</Link>
            </div>
          )}
          <div className={styles.matchList}>
            {(matches ?? []).map(m => <MatchCard key={m.recipe_id} match={m} />)}
          </div>
        </div>
      )}

      {tab === 'suggest' && (
        <div>
          {!suggestMutation.data && !suggestMutation.isPending && (
            <div className={styles.suggestPrompt}>
              <p>Let AI generate recipes based on your pantry contents.</p>
              <button className={styles.suggestBtn} onClick={()=>suggestMutation.mutate()}>
                Generate 5 suggestions
              </button>
            </div>
          )}
          {suggestMutation.isPending && <p className={styles.loading}>Generating recipes with AI…</p>}
          {suggestMutation.isError && <p className={styles.error}>Something went wrong. Try again.</p>}
          <div className={styles.suggestGrid}>
            {(suggestMutation.data ?? []).map((r, i) => <SuggestedRecipeCard key={i} recipe={r} />)}
          </div>
          {suggestMutation.data && (
            <button className={styles.retryBtn} onClick={()=>suggestMutation.mutate()}>
              Generate more →
            </button>
          )}
        </div>
      )}

      {tab === 'community' && (
        <div style={{textAlign:'center', padding:'2rem', color:'#888'}}>
          <p>Browse recipes shared by the community.</p>
          <a href="/explore" style={{color:'#ff6b35', textDecoration:'none'}}>
            Open Community Explore →
          </a>
        </div>
      )}
    </div>
  )
}

function MatchCard({ match }: { match: PantryMatchResult }) {
  const pct = Math.round(match.match_pct * 100)
  const color = pct >= 80 ? '#6dbf85' : pct >= 50 ? '#e8a84a' : '#ff6b6b'
  return (
    <Link to={`/recipes/${match.recipe_id}`} className={styles.matchCard}>
      <div className={styles.matchLeft}>
        {match.thumbnail_url && <img className={styles.matchThumb} src={match.thumbnail_url} alt={match.title} />}
        <div>
          <div className={styles.matchTitle}>{match.title}</div>
          {match.cuisine && <div className={styles.matchCuisine}>{match.cuisine}</div>}
          {match.missing_ingredients.length > 0 && (
            <div className={styles.missing}>
              Missing: {match.missing_ingredients.slice(0,3).join(', ')}
              {match.missing_ingredients.length > 3 && ` +${match.missing_ingredients.length - 3} more`}
            </div>
          )}
        </div>
      </div>
      <div className={styles.pctBadge} style={{color, borderColor: color}}>{pct}%</div>
    </Link>
  )
}

function SuggestedRecipeCard({ recipe }: { recipe: Recipe }) {
  return (
    <div className={styles.suggestCard}>
      <h3 className={styles.suggestTitle}>{recipe.title}</h3>
      {recipe.description && <p className={styles.suggestDesc}>{recipe.description}</p>}
      <div className={styles.suggestMeta}>
        {recipe.cuisine && <span className={styles.tag}>{recipe.cuisine}</span>}
        <span className={styles.tag}>{recipe.difficulty}</span>
        {recipe.total_time_minutes && <span className={styles.tag}>⏱ {recipe.total_time_minutes}m</span>}
      </div>
      <div className={styles.ingredientCount}>{recipe.ingredients.length} ingredients · {recipe.steps.length} steps</div>
    </div>
  )
}
