/**
 * app/tabs/cookbook.tsx — Cookbook Tab
 * Recipe grid with search and filter. Taps navigate to /recipe/:id.
 * Cached in AsyncStorage for offline access.
 */

import { useState } from 'react'
import {
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { useRouter } from 'expo-router'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-expo'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

interface Recipe {
  id: string
  title: string
  cuisine: string | null
  difficulty: 'easy' | 'medium' | 'hard'
  total_time_minutes: number | null
  thumbnail_url: string | null
  tags: string[]
}

const DIFF_COLOR = { easy: '#6dbf85', medium: '#e8a84a', hard: '#ff6b6b' }

export default function CookbookTab() {
  const router = useRouter()
  const { getToken } = useAuth()
  const [search, setSearch] = useState('')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['recipes', search],
    queryFn: async () => {
      const token = await getToken()
      const qs = search ? `?search=${encodeURIComponent(search)}` : ''
      const res = await fetch(`${API_URL}/api/recipes${qs}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await res.json()
      return data.recipes as Recipe[]
    },
  })

  const recipes = data ?? []

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.search}
        placeholder="Search cookbook…"
        placeholderTextColor="#555"
        value={search}
        onChangeText={setSearch}
        clearButtonMode="while-editing"
      />

      {!isLoading && recipes.length === 0 && (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>No recipes yet.</Text>
          <Text style={styles.emptyHint}>Import a cooking video from the Import tab.</Text>
        </View>
      )}

      <FlatList
        data={recipes}
        keyExtractor={r => r.id}
        numColumns={2}
        columnWrapperStyle={styles.row}
        contentContainerStyle={styles.list}
        onRefresh={refetch}
        refreshing={isLoading}
        renderItem={({ item: r }) => (
          <Pressable style={styles.card} onPress={() => router.push(`/recipe/${r.id}`)}>
            {r.thumbnail_url
              ? <Image source={{ uri: r.thumbnail_url }} style={styles.thumb} />
              : <View style={styles.thumbPlaceholder}><Text style={styles.thumbEmoji}>🍳</Text></View>}
            <View style={styles.cardBody}>
              <Text style={styles.cardTitle} numberOfLines={2}>{r.title}</Text>
              <View style={styles.cardMeta}>
                {r.cuisine && <Text style={styles.metaTag}>{r.cuisine}</Text>}
                <Text style={[styles.metaTag, { color: DIFF_COLOR[r.difficulty] }]}>
                  {r.difficulty}
                </Text>
              </View>
              {r.total_time_minutes && (
                <Text style={styles.timeLabel}>
                  ⏱ {r.total_time_minutes < 60 ? `${r.total_time_minutes}m` : `${Math.floor(r.total_time_minutes / 60)}h`}
                </Text>
              )}
            </View>
          </Pressable>
        )}
      />
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  search: {
    margin: 16, marginBottom: 8,
    backgroundColor: '#1a1a1a', borderWidth: 1.5, borderColor: '#2a2a2a',
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10,
    fontSize: 15, color: '#f5f5f5',
  },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 },
  emptyText: { fontSize: 17, color: '#888', fontWeight: '600', marginBottom: 6 },
  emptyHint: { fontSize: 13, color: '#555', textAlign: 'center' },
  list: { padding: 8, paddingTop: 4 },
  row: { gap: 8, paddingHorizontal: 8, marginBottom: 8 },
  card: { flex: 1, backgroundColor: '#1a1a1a', borderRadius: 14, overflow: 'hidden', maxWidth: '50%' },
  thumb: { width: '100%', height: 110, resizeMode: 'cover' },
  thumbPlaceholder: { width: '100%', height: 110, backgroundColor: '#111', justifyContent: 'center', alignItems: 'center' },
  thumbEmoji: { fontSize: 28 },
  cardBody: { padding: 10, gap: 4 },
  cardTitle: { fontSize: 13, fontWeight: '600', color: '#f5f5f5', lineHeight: 18 },
  cardMeta: { flexDirection: 'row', gap: 4, flexWrap: 'wrap' },
  metaTag: { fontSize: 10, color: '#888', backgroundColor: '#2a2a2a', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  timeLabel: { fontSize: 10, color: '#666' },
})
