/**
 * components/PantryScreen.tsx
 *
 * Full-featured pantry manager for mobile:
 *   • List all pantry items grouped by category
 *   • Add item by name (manual) or barcode scan (expo-camera)
 *   • Swipe-to-delete (or long-press menu)
 *
 * The barcode scanner reads UPC/EAN codes and resolves them against
 * the Nutritionix UPC lookup (POST /api/pantry/resolve-barcode) —
 * that endpoint is a Phase 2 extension, stubbed here.
 */

import { useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { BarcodeScanner } from './BarcodeScanner'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-expo'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

interface PantryItem {
  id: string
  name: string
  quantity: number | null
  unit: string | null
  category: string
}

interface Pantry {
  items: PantryItem[]
}

const CATEGORIES = [
  'produce', 'meat', 'seafood', 'dairy', 'grains',
  'pantry', 'spices', 'frozen', 'beverages', 'other',
] as const

function ExpiryChip({ dateStr }: { dateStr: string }) {
  const days = Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86400000)
  const label = days < 0 ? 'Expired' : days === 0 ? 'Today' : `${days}d`
  const color = days < 0 ? '#ff5555' : days <= 3 ? '#e8a84a' : '#888'
  return (
    <Text style={{ fontSize: 10, color, fontWeight: '700', marginLeft: 4 }}>
      {label}
    </Text>
  )
}

export function PantryScreen() {
  const { getToken } = useAuth()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [qty, setQty] = useState('')
  const [unit, setUnit] = useState('')
  const [category, setCategory] = useState<typeof CATEGORIES[number]>('other')
  const [showAdd, setShowAdd] = useState(false)
  const [scannerOpen, setScannerOpen] = useState(false)
  const [editingPriceId, setEditingPriceId] = useState<string | null>(null)
  const [expiry, setExpiry] = useState<string>('')

  function handleScanResult(name: string, category: string) {
    setScannerOpen(false)
    setName(name)
    setCat(category as typeof CATEGORIES[number])
    setShowAdd(true)
  }

  const priceMutation = useMutation({
    mutationFn: async ({ itemId, price }: { itemId: string; price: number | null }) => {
      const token = await getToken()
      await fetch(`${API_URL}/api/pantry/items/${itemId}/price`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ estimated_cost_per_unit: price }),
      })
    },
    onSuccess: () => {
      setEditingPriceId(null)
      queryClient.invalidateQueries({ queryKey: ['pantry'] })
    },
  })

  const { data: pantry, isLoading, refetch } = useQuery({
    queryKey: ['pantry'],
    queryFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/pantry`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await res.json()
      return data as Pantry
    },
  })

  const addMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/pantry/items`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          name: name.trim().toLowerCase(),
          quantity: qty ? Number(qty) : null,
          unit: unit.trim() || null,
          category,
        }),
      })
      if (!res.ok) throw new Error('Failed to add item')
      return res.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pantry'] })
      setName('')
      setQty('')
      setUnit('')
      setShowAdd(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (itemId: string) => {
      const token = await getToken()
      await fetch(`${API_URL}/api/pantry/items/${itemId}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pantry'] }),
  })

  function confirmDelete(item: PantryItem) {
    Alert.alert(
      'Remove item',
      `Remove "${item.name}" from your pantry?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Remove', style: 'destructive', onPress: () => deleteMutation.mutate(item.id) },
      ],
    )
  }

  const grouped = groupItems(pantry?.items ?? [])
  const sections = Object.entries(grouped)

  return (
    <View style={styles.container}>
      {/* Barcode scanner modal */}
      <Modal visible={scannerOpen} animationType="slide" statusBarTranslucent>
        <BarcodeScanner
          onResult={handleScanResult}
          onClose={() => setScannerOpen(false)}
        />
      </Modal>

      {/* Add item bar */}
      {showAdd ? (
        <View style={styles.addPanel}>
          <TextInput
            style={styles.addInput}
            placeholder="Ingredient name"
            placeholderTextColor="#555"
            value={name}
            onChangeText={setName}
            autoFocus
          />
          <View style={styles.addRow2}>
            <TextInput
              style={[styles.addInput, styles.addInputSm]}
              placeholder="Qty"
              placeholderTextColor="#555"
              value={qty}
              onChangeText={setQty}
              keyboardType="decimal-pad"
            />
            <TextInput
              style={[styles.addInput, styles.addInputSm]}
              placeholder="Unit"
              placeholderTextColor="#555"
              value={unit}
              onChangeText={setUnit}
            />
          </View>
          <View style={styles.catRow}>
            {CATEGORIES.map(c => (
              <Pressable
                key={c}
                style={[styles.catChip, category === c && styles.catChipActive]}
                onPress={() => setCategory(c)}
              >
                <Text style={[styles.catText, category === c && styles.catTextActive]}>{c}</Text>
              </Pressable>
            ))}
          </View>
          <View style={styles.addActions}>
            <Pressable style={styles.cancelBtn} onPress={() => setShowAdd(false)}>
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>
            <Pressable
              style={[styles.saveBtn, (!name.trim() || addMutation.isPending) && styles.saveBtnDisabled]}
              onPress={() => addMutation.mutate()}
              disabled={!name.trim() || addMutation.isPending}
            >
              {addMutation.isPending
                ? <ActivityIndicator color="#fff" size="small" />
                : <Text style={styles.saveBtnText}>Add</Text>}
            </Pressable>
          </View>
        </View>
      ) : (
        <View style={styles.toolbar}>
          <Pressable style={styles.addBtn} onPress={() => setShowAdd(true)}>
            <Text style={styles.addBtnText}>+ Add ingredient</Text>
          </Pressable>
          <Pressable
            style={styles.scanBtn}
            onPress={() => setScannerOpen(true)}
          >
            <Text style={styles.scanBtnText}>📷 Scan</Text>
          </Pressable>
        </View>
      )}

      {isLoading && <ActivityIndicator style={styles.loader} color="#ff6b35" />}

      {!isLoading && sections.length === 0 && (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>Your pantry is empty.</Text>
          <Text style={styles.emptyHint}>Add ingredients to discover what you can cook.</Text>
        </View>
      )}

      <FlatList
        data={sections}
        keyExtractor={([cat]) => cat}
        contentContainerStyle={styles.list}
        onRefresh={refetch}
        refreshing={isLoading}
        renderItem={({ item: [category, items] }) => (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>{category.toUpperCase()}</Text>
            {items.map(item => (
              <Pressable
                key={item.id}
                style={styles.item}
                onLongPress={() => confirmDelete(item)}
              >
                <View style={styles.itemLeft}>
                  <Text style={styles.itemName}>{item.name}</Text>
                  {item.quantity != null && (
                    <Text style={styles.itemQty}>
                      {item.quantity}{item.unit ? ` ${item.unit}` : ''}
                    </Text>
                  )}
                </View>
                <Pressable
                  style={styles.priceBtn}
                  onPress={() => setEditingPriceId(editingPriceId === item.id ? null : item.id)}
                >
                  <Text style={styles.priceBtnText}>
                    {item.estimated_cost_per_unit != null ? `$${Number(item.estimated_cost_per_unit).toFixed(2)}` : '💲'}
                  </Text>
                </Pressable>
                <Pressable style={styles.deleteBtn} onPress={() => confirmDelete(item)}>
                  <Text style={styles.deleteText}>×</Text>
                </Pressable>
              </Pressable>
            ))}
          </View>
        )}
      />
    </View>
  )
}

function groupItems(items: PantryItem[]): Record<string, PantryItem[]> {
  return items.reduce((acc, item) => {
    const cat = item.category ?? 'other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(item)
    return acc
  }, {} as Record<string, PantryItem[]>)
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  toolbar: { flexDirection: 'row', gap: 8, padding: 16, paddingBottom: 8 },
  addBtn: { flex: 1, backgroundColor: '#ff6b35', borderRadius: 12, paddingVertical: 11, alignItems: 'center' },
  addBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  scanBtn: { backgroundColor: '#1a1a1a', borderRadius: 12, paddingVertical: 11, paddingHorizontal: 16, borderWidth: 1.5, borderColor: '#2a2a2a' },
  scanBtnText: { color: '#888', fontSize: 14 },
  addPanel: { backgroundColor: '#1a1a1a', margin: 16, borderRadius: 16, padding: 16, gap: 10 },
  addInput: { backgroundColor: '#111', borderWidth: 1.5, borderColor: '#2a2a2a', borderRadius: 10, padding: 12, fontSize: 15, color: '#f5f5f5' },
  addRow2: { flexDirection: 'row', gap: 8 },
  addInputSm: { flex: 1 },
  catRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  catChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20, backgroundColor: '#2a2a2a' },
  catChipActive: { backgroundColor: '#ff6b35' },
  catText: { fontSize: 11, color: '#888' },
  catTextActive: { color: '#fff', fontWeight: '600' },
  addActions: { flexDirection: 'row', gap: 8, justifyContent: 'flex-end' },
  cancelBtn: { paddingHorizontal: 16, paddingVertical: 10 },
  cancelText: { color: '#666', fontSize: 14 },
  saveBtn: { backgroundColor: '#ff6b35', borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 },
  saveBtnDisabled: { opacity: 0.5 },
  saveBtnText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  loader: { marginTop: 40 },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 },
  emptyText: { fontSize: 16, color: '#888', fontWeight: '600', marginBottom: 6 },
  emptyHint: { fontSize: 13, color: '#555', textAlign: 'center', lineHeight: 19 },
  list: { paddingBottom: 20 },
  section: { paddingHorizontal: 16, marginBottom: 8 },
  sectionTitle: { fontSize: 10, fontWeight: '700', color: '#555', letterSpacing: 1, marginBottom: 4, marginTop: 12 },
  item: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1a1a1a', borderRadius: 10, padding: 12, marginBottom: 3 },
  itemLeft: { flex: 1, gap: 2 },
  itemName: { fontSize: 14, color: '#f5f5f5' },
  itemQty: { fontSize: 12, color: '#e8a84a', fontFamily: 'Courier' },
  expiryRow: { paddingHorizontal: 12, paddingBottom: 8, gap: 4 },
  expiryLabel: { fontSize: 11, color: '#555' },
  expiryInput: { backgroundColor: '#1a1a1a', borderWidth: 1, borderColor: '#2a2a2a', borderRadius: 8, padding: 8, color: '#e8a84a', fontSize: 13 },
  priceBtn: { backgroundColor: '#1a2a1a', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, minWidth: 44, alignItems: 'center' },
  priceBtnText: { color: '#6dbf85', fontSize: 11, fontWeight: '600' },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingBottom: 8, backgroundColor: '#111' },
  priceLabel: { color: '#666', fontSize: 12 },
  priceInput: { flex: 1, backgroundColor: '#1a1a1a', borderWidth: 1, borderColor: '#2a4a2a', borderRadius: 8, padding: 8, color: '#6dbf85', fontSize: 14 },
  priceClear: { color: '#555', fontSize: 12 },
  deleteBtn: { padding: 4 },
  deleteText: { fontSize: 18, color: '#444' },
})
