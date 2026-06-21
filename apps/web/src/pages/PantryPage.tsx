import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import { getPantry, addPantryItem, deletePantryItem } from '../api/client'
import type { PantryItem } from '@reelrecipes/shared'
import styles from './PantryPage.module.css'

const CATEGORIES = ['produce','meat','seafood','dairy','grains','pantry','spices','frozen','beverages','other'] as const

function ExpiryBadge({ dateStr }: { dateStr: string }) {
  const days = Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86400000)
  const label = days < 0 ? 'Expired' : days === 0 ? 'Expires today' : `Exp. ${days}d`
  const color = days < 0 ? '#ff5555' : days <= 3 ? '#e8a84a' : '#888'
  return <span style={{ fontSize: '.72rem', color, fontWeight: 600, marginLeft: 4 }}>{label}</span>
}

export function PantryPage() {
  const { getToken } = useAuth()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [qty, setQty] = useState('')
  const [unit, setUnit] = useState('')
  const [cat, setCat] = useState<typeof CATEGORIES[number]>('other')
  const [adding, setAdding] = useState(false)

  const { data: pantry, isLoading } = useQuery({
    queryKey: ['pantry'],
    queryFn: async () => { const t = await getToken(); return getPantry(t) },
  })

  const addMutation = useMutation({
    mutationFn: async () => {
      const t = await getToken()
      return addPantryItem({ name: name.trim(), quantity: qty ? Number(qty) : null, unit: unit||null, category: cat }, t)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['pantry'] }); setName(''); setQty(''); setUnit('') },
  })

  const priceMutation = useMutation({
    mutationFn: async ({ itemId, price }: { itemId: string; price: number | null }) => {
      const t = await getToken()
      await fetch(`${API}/api/pantry/items/${itemId}/price`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({ estimated_cost_per_unit: price }),
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pantry'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: async (itemId: string) => { const t = await getToken(); return deletePantryItem(itemId, t) },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pantry'] }),
  })

  const grouped = groupByCategory(pantry?.items ?? [])

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>🧄 Pantry</h1>
      <p className={styles.sub}>Track what you have. We'll tell you what you can cook.</p>

      <div className={styles.addRow}>
        <input className={styles.input} placeholder="Ingredient name" value={name} onChange={e=>setName(e.target.value)}
          onKeyDown={e=>e.key==='Enter' && name.trim() && addMutation.mutate()} />
        <input className={styles.inputSm} placeholder="Qty" type="number" value={qty} onChange={e=>setQty(e.target.value)} />
        <input className={styles.inputSm} placeholder="Unit" value={unit} onChange={e=>setUnit(e.target.value)} />
        <select className={styles.select} value={cat} onChange={e=>setCat(e.target.value as any)}>
          {CATEGORIES.map(c=><option key={c} value={c}>{c}</option>)}
        </select>
        <button className={styles.addBtn} disabled={!name.trim() || addMutation.isPending}
          onClick={()=>addMutation.mutate()}>
          {addMutation.isPending ? '…' : 'Add'}
        </button>
      </div>

      {isLoading && <p className={styles.loading}>Loading pantry…</p>}

      {!isLoading && (pantry?.items ?? []).length === 0 && (
        <div className={styles.empty}>
          <p>Your pantry is empty. Add ingredients to get started.</p>
        </div>
      )}

      {Object.entries(grouped).map(([category, items]) => (
        <div key={category} className={styles.group}>
          <h2 className={styles.groupName}>{category}</h2>
          <div className={styles.itemList}>
            {items.map(item => (
              <div key={item.id} className={styles.item}>
                <span className={styles.itemName}>{item.name}</span>
                {item.quantity && <span className={styles.itemQty}>{item.quantity}{item.unit ? ` ${item.unit}` : ''}</span>}
                <input
                  className={styles.priceInput}
                  type="number" min="0" step="0.01"
                  placeholder="$/unit"
                  defaultValue={item.estimated_cost_per_unit ?? ''}
                  onBlur={e => priceMutation.mutate({ itemId: item.id, price: e.target.value ? parseFloat(e.target.value) : null })}
                />
                <button className={styles.deleteBtn} onClick={()=>deleteMutation.mutate(item.id)}
                  title="Remove">×</button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function groupByCategory(items: PantryItem[]): Record<string, PantryItem[]> {
  return items.reduce((acc, item) => {
    const cat = item.category ?? 'other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(item)
    return acc
  }, {} as Record<string, PantryItem[]>)
}
