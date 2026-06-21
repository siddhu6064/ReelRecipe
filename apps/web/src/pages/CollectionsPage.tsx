import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import { useTranslation } from 'react-i18next'
import styles from './CollectionsPage.module.css'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface Collection {
  id: string; name: string; emoji: string
  recipe_ids: string[]; created_at: string
}

const EMOJIS = ['📁','🍝','🥗','🍜','🍕','🌮','🍣','🥘','🍰','🥩','🍱','🌿','❤️','⭐','🔥','🎉']

export function CollectionsPage() {
  const { t } = useTranslation()
  const { getToken } = useAuth()
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [newName, setNewName] = useState('')
  const [newEmoji, setNewEmoji] = useState('📁')

  async function authFetch(path: string, init: RequestInit = {}) {
    const token = await getToken()
    return fetch(`${API}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  }

  const { data: collections = [], isLoading } = useQuery({
    queryKey: ['collections'],
    queryFn: async () => {
      const r = await authFetch('/api/collections')
      const { data } = await r.json(); return data as Collection[]
    },
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const r = await authFetch('/api/collections', {
        method: 'POST',
        body: JSON.stringify({ name: newName.trim(), emoji: newEmoji }),
      })
      if (!r.ok) throw new Error('Failed')
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collections'] })
      setNewName(''); setNewEmoji('📁'); setShowNew(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await authFetch(`/api/collections/${id}`, { method: 'DELETE' })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collections'] }),
  })

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>📁 {t('collections.title')}</h1>
        <button className={styles.newBtn} onClick={() => setShowNew(s => !s)}>
          {t('collections.newCollection')}
        </button>
      </header>

      {showNew && (
        <div className={styles.newCard}>
          <div className={styles.emojiPicker}>
            {EMOJIS.map(e => (
              <button
                key={e}
                className={`${styles.emojiBtn} ${newEmoji === e ? styles.emojiBtnActive : ''}`}
                onClick={() => setNewEmoji(e)}
              >
                {e}
              </button>
            ))}
          </div>
          <div className={styles.newRow}>
            <span className={styles.selectedEmoji}>{newEmoji}</span>
            <input
              className={styles.nameInput}
              placeholder={t('collections.namePlaceholder')}
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && newName.trim() && createMutation.mutate()}
              autoFocus
            />
            <button
              className={styles.createBtn}
              disabled={!newName.trim() || createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending ? '…' : t('collections.create')}
            </button>
            <button className={styles.cancelBtn} onClick={() => setShowNew(false)}>
              {t('collections.cancel')}
            </button>
          </div>
        </div>
      )}

      {isLoading && <p className={styles.loading}>{t('common.loading')}</p>}

      {!isLoading && collections.length === 0 && !showNew && (
        <div className={styles.empty}>
          <p className={styles.emptyText}>{t('collections.empty')}</p>
          <p className={styles.emptyHint}>{t('collections.emptyHint')}</p>
        </div>
      )}

      <div className={styles.grid}>
        {collections.map(col => (
          <CollectionCard
            key={col.id}
            collection={col}
            onDelete={() => {
              if (confirm(t('collections.deleteConfirm'))) deleteMutation.mutate(col.id)
            }}
          />
        ))}
      </div>
    </div>
  )
}

function CollectionCard({ collection: col, onDelete }: { collection: Collection; onDelete: () => void }) {
  const { t } = useTranslation()
  const count = col.recipe_ids.length

  return (
    <div className={styles.card}>
      <div className={styles.cardIcon}>{col.emoji}</div>
      <div className={styles.cardBody}>
        <h3 className={styles.cardName}>{col.name}</h3>
        <p className={styles.cardCount}>
          {t('collections.recipes', { count, defaultValue: `${count} recipes` })}
        </p>
      </div>
      <div className={styles.cardActions}>
        <Link to={`/collections/${col.id}`} className={styles.viewBtn}>View →</Link>
        <button className={styles.deleteBtn} onClick={onDelete} title="Delete">🗑</button>
      </div>
    </div>
  )
}
