import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth, useUser, useClerk } from '@clerk/clerk-react'
import { useNavigate } from 'react-router-dom'
import styles from './ProfilePage.module.css'
import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES, type LangCode } from '../i18n'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const DIETARY_OPTIONS = [
  'vegan', 'vegetarian', 'gluten-free', 'dairy-free',
  'nut-free', 'halal', 'kosher', 'keto', 'paleo', 'low-carb',
]
const CUISINE_OPTIONS = [
  'Italian', 'Japanese', 'Mexican', 'Indian', 'Chinese',
  'Thai', 'French', 'Mediterranean', 'American', 'Korean',
  'Vietnamese', 'Greek', 'Spanish', 'Middle Eastern',
]

interface UserProfile {
  clerk_id: string
  email: string
  name: string
  dietary_prefs: string[]
  cuisine_prefs: string[]
  unit_system: 'metric' | 'imperial'
}

export function ProfilePage() {
  const { getToken, signOut } = useAuth()
  const { user } = useUser()
  const { openUserProfile } = useClerk()
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [saved, setSaved] = useState(false)

  const { data: profile, isLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API}/api/users/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('Profile not found')
      const { data } = await res.json()
      return data as UserProfile
    },
  })

  const [dietary, setDietary] = useState<string[]>(profile?.dietary_prefs ?? [])
  const [cuisine, setCuisine] = useState<string[]>(profile?.cuisine_prefs ?? [])
  const [units, setUnits] = useState<'metric' | 'imperial'>(profile?.unit_system ?? 'metric')

  // Sync local state when profile loads
  const [synced, setSynced] = useState(false)
  if (profile && !synced) {
    setDietary(profile.dietary_prefs)
    setCuisine(profile.cuisine_prefs)
    setUnits(profile.unit_system)
    setSynced(true)
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API}/api/users/me/prefs`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          dietary_prefs: dietary,
          cuisine_prefs: cuisine,
          unit_system: units,
        }),
      })
      if (!res.ok) throw new Error('Failed to save')
      return res.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profile'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
  })

  function toggleDietary(pref: string) {
    setDietary(d => d.includes(pref) ? d.filter(x => x !== pref) : [...d, pref])
    setSaved(false)
  }

  function toggleCuisine(c: string) {
    setCuisine(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])
    setSaved(false)
  }

  async function handleSignOut() {
    await signOut()
    navigate('/import')
  }

  if (isLoading) return <div className={styles.loading}>Loading profile…</div>

  return (
    <div className={styles.page}>
      {/* Account card */}
      <div className={styles.accountCard}>
        {user?.imageUrl
          ? <img className={styles.avatar} src={user.imageUrl} alt="avatar" />
          : <div className={styles.avatarPlaceholder}>{user?.firstName?.[0] ?? '?'}</div>}
        <div className={styles.accountInfo}>
          <div className={styles.accountName}>{user?.fullName ?? profile?.name ?? 'Unknown'}</div>
          <div className={styles.accountEmail}>{user?.primaryEmailAddress?.emailAddress ?? profile?.email}</div>
        </div>
        <button className={styles.editAccountBtn} onClick={() => openUserProfile()}>
          Edit account
        </button>
      </div>

      {/* Dietary preferences */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Dietary preferences</h2>
        <p className={styles.sectionSub}>Used to personalise AI recipe suggestions.</p>
        <div className={styles.chipGrid}>
          {DIETARY_OPTIONS.map(pref => (
            <button
              key={pref}
              className={`${styles.chip} ${dietary.includes(pref) ? styles.chipActive : ''}`}
              onClick={() => toggleDietary(pref)}
            >
              {pref}
            </button>
          ))}
        </div>
      </section>

      {/* Cuisine preferences */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Favourite cuisines</h2>
        <p className={styles.sectionSub}>We'll prioritise these in suggestions.</p>
        <div className={styles.chipGrid}>
          {CUISINE_OPTIONS.map(c => (
            <button
              key={c}
              className={`${styles.chip} ${cuisine.includes(c) ? styles.chipActive : ''}`}
              onClick={() => toggleCuisine(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </section>

      {/* Unit system */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Unit system</h2>
        <div className={styles.unitRow}>
          {(['metric', 'imperial'] as const).map(u => (
            <button
              key={u}
              className={`${styles.unitBtn} ${units === u ? styles.unitBtnActive : ''}`}
              onClick={() => { setUnits(u); setSaved(false) }}
            >
              <span className={styles.unitIcon}>{u === 'metric' ? '🌍' : '🇺🇸'}</span>
              <span className={styles.unitLabel}>{u === 'metric' ? 'Metric (g, ml, °C)' : 'Imperial (oz, cups, °F)'}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Save button */}
      <div className={styles.saveRow}>
        <button
          className={`${styles.saveBtn} ${saved ? styles.saveBtnDone : ''}`}
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
        >
          {saveMutation.isPending ? 'Saving…' : saved ? '✓ Saved' : 'Save preferences'}
        </button>
        {saveMutation.isError && (
          <span className={styles.saveError}>Failed to save. Please try again.</span>
        )}
      </div>

      {/* Language */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t('profile.language')}</h2>
        <div className={styles.chipGrid}>
          {SUPPORTED_LANGUAGES.map(lang => (
            <button
              key={lang.code}
              className={`${styles.chip} ${i18n.language.startsWith(lang.code) ? styles.chipActive : ''}`}
              onClick={() => i18n.changeLanguage(lang.code)}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </section>

      {/* Danger zone */}
      <section className={styles.dangerSection}>
        <h2 className={styles.sectionTitle}>Account</h2>
        <button className={styles.signOutBtn} onClick={handleSignOut}>Sign out</button>
      </section>
    </div>
  )
}
