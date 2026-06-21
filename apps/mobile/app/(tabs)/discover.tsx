/**
 * app/tabs/discover.tsx — Discover Tab
 * Shows pantry match results and AI recipe suggestions.
 */
import { useState } from 'react'
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-expo'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

interface MatchResult {
  recipe_id: string; title: string; match_pct: number
  missing_ingredients: string[]; cuisine: string | null
}
interface SuggestedRecipe { title: string; description: string | null; difficulty: string; total_time_minutes: number | null; ingredients: unknown[] }

export default function DiscoverTab() {
  const router = useRouter()
  const { getToken } = useAuth()
  const [tab, setTab] = useState<'match'|'suggest'>('match')

  const { data: matches, isLoading: matchLoading, refetch } = useQuery({
    queryKey: ['pantry-match'],
    queryFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/pantry/match`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await res.json()
      return data as MatchResult[]
    },
    enabled: tab === 'match',
  })

  const suggestMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/ai/suggest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ dietary_prefs: [], cuisine_prefs: [], max_recipes: 5 }),
      })
      const { data } = await res.json()
      return data as SuggestedRecipe[]
    },
  })

  return (
    <View style={s.container}>
      <View style={s.tabs}>
        <Pressable style={[s.tab, tab==='match'&&s.tabActive]} onPress={()=>setTab('match')}>
          <Text style={[s.tabText, tab==='match'&&s.tabTextActive]}>🎯 What can I cook?</Text>
        </Pressable>
        <Pressable style={[s.tab, tab==='suggest'&&s.tabActive]} onPress={()=>setTab('suggest')}>
          <Text style={[s.tabText, tab==='suggest'&&s.tabTextActive]}>🤖 AI ideas</Text>
        </Pressable>
      </View>

      {tab === 'match' && (
        matchLoading
          ? <ActivityIndicator style={s.loader} color="#ff6b35" />
          : <FlatList
              data={matches ?? []}
              keyExtractor={m => m.recipe_id}
              onRefresh={refetch}
              refreshing={matchLoading}
              contentContainerStyle={s.list}
              ListEmptyComponent={<Text style={s.empty}>No recipes yet. Import some videos!</Text>}
              renderItem={({ item: m }) => {
                const pct = Math.round(m.match_pct * 100)
                const color = pct >= 80 ? '#6dbf85' : pct >= 50 ? '#e8a84a' : '#ff6b6b'
                return (
                  <Pressable style={s.matchCard} onPress={() => router.push(`/recipe/${m.recipe_id}`)}>
                    <View style={s.matchInfo}>
                      <Text style={s.matchTitle}>{m.title}</Text>
                      {m.cuisine && <Text style={s.matchCuisine}>{m.cuisine}</Text>}
                      {m.missing_ingredients.length > 0 && (
                        <Text style={s.missing}>Missing: {m.missing_ingredients.slice(0,2).join(', ')}{m.missing_ingredients.length > 2 ? ` +${m.missing_ingredients.length-2}` : ''}</Text>
                      )}
                    </View>
                    <View style={[s.pctBadge, { borderColor: color }]}>
                      <Text style={[s.pctText, { color }]}>{pct}%</Text>
                    </View>
                  </Pressable>
                )
              }}
            />
      )}

      {tab === 'suggest' && (
        <View style={s.suggestContainer}>
          {!suggestMutation.data && !suggestMutation.isPending && (
            <View style={s.suggestPrompt}>
              <Text style={s.suggestPromptText}>Generate recipes from your pantry with AI.</Text>
              <Pressable style={s.genBtn} onPress={() => suggestMutation.mutate()}>
                <Text style={s.genBtnText}>Generate suggestions</Text>
              </Pressable>
            </View>
          )}
          {suggestMutation.isPending && <ActivityIndicator style={s.loader} color="#ff6b35" />}
          {suggestMutation.data && (
            <FlatList
              data={suggestMutation.data}
              keyExtractor={(_, i) => String(i)}
              contentContainerStyle={s.list}
              renderItem={({ item: r }) => (
                <View style={s.suggestCard}>
                  <Text style={s.suggestTitle}>{r.title}</Text>
                  {r.description && <Text style={s.suggestDesc}>{r.description}</Text>}
                  <View style={s.suggestMeta}>
                    <Text style={s.metaTag}>{r.difficulty}</Text>
                    {r.total_time_minutes && <Text style={s.metaTag}>⏱ {r.total_time_minutes}m</Text>}
                    <Text style={s.metaTag}>{(r.ingredients as unknown[]).length} ingredients</Text>
                  </View>
                </View>
              )}
            />
          )}
        </View>
      )}
    </View>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  tabs: { flexDirection: 'row', gap: 8, padding: 16, paddingBottom: 8 },
  tab: { flex: 1, padding: 10, borderRadius: 12, backgroundColor: '#1a1a1a', alignItems: 'center' },
  tabActive: { backgroundColor: '#ff6b35' },
  tabText: { fontSize: 13, color: '#888', fontWeight: '600' },
  tabTextActive: { color: '#fff' },
  loader: { marginTop: 40 },
  list: { padding: 16, gap: 8 },
  empty: { textAlign: 'center', color: '#555', padding: 40, fontSize: 14 },
  matchCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1a1a1a', borderRadius: 14, padding: 14, gap: 12 },
  matchInfo: { flex: 1, gap: 3 },
  matchTitle: { fontSize: 15, fontWeight: '600', color: '#f5f5f5' },
  matchCuisine: { fontSize: 12, color: '#888' },
  missing: { fontSize: 11, color: '#e8a84a' },
  pctBadge: { width: 50, height: 50, borderRadius: 25, borderWidth: 2.5, justifyContent: 'center', alignItems: 'center' },
  pctText: { fontSize: 14, fontWeight: '700' },
  suggestContainer: { flex: 1 },
  suggestPrompt: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40, gap: 16 },
  suggestPromptText: { fontSize: 15, color: '#888', textAlign: 'center' },
  genBtn: { backgroundColor: '#ff6b35', borderRadius: 14, paddingHorizontal: 24, paddingVertical: 14 },
  genBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  suggestCard: { backgroundColor: '#1a1a1a', borderRadius: 14, padding: 14, gap: 6 },
  suggestTitle: { fontSize: 15, fontWeight: '600', color: '#f5f5f5' },
  suggestDesc: { fontSize: 13, color: '#888', lineHeight: 19 },
  suggestMeta: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  metaTag: { fontSize: 11, color: '#888', backgroundColor: '#2a2a2a', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
})
