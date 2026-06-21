/**
 * app/(tabs)/collections.tsx — Collections Tab
 * User's recipe folders (collections).
 */

import { useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { useRouter } from 'expo-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-expo'
import { useTranslation } from 'react-i18next'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

const EMOJI_OPTS = ['📁','🍝','🥗','🍜','🍕','🌮','🍣','🥘','🍰','🥩','🍱','🌿','❤️','⭐','🔥']

interface Collection {
  id: string; name: string; emoji: string; recipe_ids: string[]
}

export default function CollectionsTab() {
  const { getToken } = useAuth()
  const { t } = useTranslation()
  const qc = useQueryClient()
  const router = useRouter()
  const [showNew, setShowNew] = useState(false)
  const [newName, setNewName] = useState('')
  const [newEmoji, setNewEmoji] = useState('📁')

  const { data: collections = [], isLoading, refetch } = useQuery({
    queryKey: ['collections'],
    queryFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/collections`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await res.json()
      return data as Collection[]
    },
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/collections`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ name: newName.trim(), emoji: newEmoji }),
      })
      if (!res.ok) throw new Error('Failed to create')
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collections'] })
      setNewName(''); setNewEmoji('📁'); setShowNew(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const token = await getToken()
      await fetch(`${API_URL}/api/collections/${id}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collections'] }),
  })

  function confirmDelete(col: Collection) {
    Alert.alert(
      t('collections.deleteConfirm'),
      col.name,
      [
        { text: t('common.cancel'), style: 'cancel' },
        { text: t('common.delete'), style: 'destructive', onPress: () => deleteMutation.mutate(col.id) },
      ]
    )
  }

  return (
    <View style={s.container}>
      {/* New collection panel */}
      {showNew ? (
        <View style={s.newPanel}>
          <View style={s.emojiRow}>
            {EMOJI_OPTS.map(e => (
              <Pressable
                key={e}
                style={[s.emojiBtn, newEmoji === e && s.emojiBtnActive]}
                onPress={() => setNewEmoji(e)}
              >
                <Text style={s.emojiText}>{e}</Text>
              </Pressable>
            ))}
          </View>
          <View style={s.inputRow}>
            <Text style={s.selectedEmoji}>{newEmoji}</Text>
            <TextInput
              style={s.nameInput}
              placeholder={t('collections.namePlaceholder')}
              placeholderTextColor="#555"
              value={newName}
              onChangeText={setNewName}
              autoFocus
              returnKeyType="done"
              onSubmitEditing={() => newName.trim() && createMutation.mutate()}
            />
          </View>
          <View style={s.newActions}>
            <Pressable
              style={[s.createBtn, (!newName.trim() || createMutation.isPending) && s.createBtnDisabled]}
              onPress={() => createMutation.mutate()}
              disabled={!newName.trim() || createMutation.isPending}
            >
              {createMutation.isPending
                ? <ActivityIndicator color="#fff" size="small" />
                : <Text style={s.createBtnText}>{t('collections.create')}</Text>}
            </Pressable>
            <Pressable style={s.cancelBtn} onPress={() => setShowNew(false)}>
              <Text style={s.cancelBtnText}>{t('collections.cancel')}</Text>
            </Pressable>
          </View>
        </View>
      ) : (
        <Pressable style={s.newBtn} onPress={() => setShowNew(true)}>
          <Text style={s.newBtnText}>{t('collections.newCollection')}</Text>
        </Pressable>
      )}

      {isLoading && <ActivityIndicator style={s.loader} color="#ff6b35" />}

      {!isLoading && collections.length === 0 && !showNew && (
        <View style={s.empty}>
          <Text style={s.emptyText}>{t('collections.empty')}</Text>
          <Text style={s.emptyHint}>{t('collections.emptyHint')}</Text>
        </View>
      )}

      <FlatList
        data={collections}
        keyExtractor={c => c.id}
        onRefresh={refetch}
        refreshing={isLoading}
        contentContainerStyle={s.list}
        renderItem={({ item: col }) => (
          <Pressable
            style={s.card}
            onPress={() => { /* navigate to collection detail */ }}
            onLongPress={() => confirmDelete(col)}
          >
            <Text style={s.cardEmoji}>{col.emoji}</Text>
            <View style={s.cardInfo}>
              <Text style={s.cardName}>{col.name}</Text>
              <Text style={s.cardCount}>
                {col.recipe_ids.length} {col.recipe_ids.length === 1 ? 'recipe' : 'recipes'}
              </Text>
            </View>
            <Text style={s.cardArrow}>›</Text>
          </Pressable>
        )}
      />
    </View>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  newBtn: { margin: 16, marginBottom: 8, backgroundColor: '#ff6b35', borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  newBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  newPanel: { backgroundColor: '#1a1a1a', margin: 16, borderRadius: 16, padding: 14, gap: 10 },
  emojiRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  emojiBtn: { width: 38, height: 38, borderRadius: 8, backgroundColor: '#111', alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: '#2a2a2a' },
  emojiBtnActive: { borderColor: '#ff6b35', backgroundColor: '#2a1a0a' },
  emojiText: { fontSize: 18 },
  inputRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  selectedEmoji: { fontSize: 22 },
  nameInput: { flex: 1, backgroundColor: '#111', borderWidth: 1.5, borderColor: '#2a2a2a', borderRadius: 10, padding: 12, fontSize: 15, color: '#f5f5f5' },
  newActions: { flexDirection: 'row', gap: 8 },
  createBtn: { flex: 1, backgroundColor: '#ff6b35', borderRadius: 10, paddingVertical: 11, alignItems: 'center' },
  createBtnDisabled: { opacity: 0.5 },
  createBtnText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  cancelBtn: { paddingHorizontal: 16, paddingVertical: 11, justifyContent: 'center' },
  cancelBtnText: { color: '#666', fontSize: 14 },
  loader: { marginTop: 40 },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 },
  emptyText: { fontSize: 16, color: '#888', fontWeight: '600', marginBottom: 6 },
  emptyHint: { fontSize: 13, color: '#555', textAlign: 'center' },
  list: { padding: 16, gap: 6, paddingTop: 8 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1a1a1a', borderRadius: 12, padding: 14, gap: 12 },
  cardEmoji: { fontSize: 26 },
  cardInfo: { flex: 1 },
  cardName: { fontSize: 15, fontWeight: '600', color: '#f5f5f5' },
  cardCount: { fontSize: 12, color: '#888', marginTop: 2 },
  cardArrow: { fontSize: 20, color: '#444' },
})
