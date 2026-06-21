/**
 * app/(tabs)/explore.tsx — Explore Tab
 *
 * Community recipe feed — public recipes shared by all users.
 * Tabs: Trending · Recent
 */

import { useState } from 'react'
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-expo'
import { useTranslation } from 'react-i18next'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

const DIFF_COLOR: Record<string, string> = {
  easy: '#6dbf85', medium: '#e8a84a', hard: '#ff6b6b',
}

interface PublicRecipe {
  id: string; title: string; cuisine: string | null
  difficulty: string; total_time_minutes: number | null
  thumbnail_url: string | null; ingredients: { name: string }[]
  view_count: number; share_count: number; is_public: boolean
}

export default function ExploreTab() {
  const { getToken } = useAuth()
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [tab, setTab] = useState<'trending' | 'recent'>('trending')
  const [saved, setSaved] = useState<Set<string>>(new Set())

  const endpoint = tab === 'trending'
    ? '/api/recipes/explore/trending'
    : '/api/recipes/explore'

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['explore-mobile', tab],
    queryFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}${endpoint}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const json = await res.json()
      const recipes = json.data?.recipes ?? json.data
      return recipes as PublicRecipe[]
    },
  })

  const duplicateMutation = useMutation({
    mutationFn: async (recipeId: string) => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/recipes/${recipeId}/duplicate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })
      if (!res.ok) throw new Error('Failed')
      return recipeId
    },
    onSuccess: (recipeId) => {
      setSaved(s => new Set([...s, recipeId]))
      qc.invalidateQueries({ queryKey: ['recipes'] })
    },
  })

  return (
    <View style={s.container}>
      {/* Tab switcher */}
      <View style={s.tabs}>
        <Pressable
          style={[s.tab, tab === 'trending' && s.tabActive]}
          onPress={() => setTab('trending')}
        >
          <Text style={[s.tabText, tab === 'trending' && s.tabTextActive]}>
            🔥 {t('explore.trending')}
          </Text>
        </Pressable>
        <Pressable
          style={[s.tab, tab === 'recent' && s.tabActive]}
          onPress={() => setTab('recent')}
        >
          <Text style={[s.tabText, tab === 'recent' && s.tabTextActive]}>
            🆕 {t('explore.recent')}
          </Text>
        </Pressable>
      </View>

      {isLoading && <ActivityIndicator style={s.loader} color="#ff6b35" size="large" />}

      <FlatList
        data={data ?? []}
        keyExtractor={r => r.id}
        onRefresh={refetch}
        refreshing={isLoading}
        contentContainerStyle={s.list}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          !isLoading ? (
            <Text style={s.empty}>{t('explore.empty')}</Text>
          ) : null
        }
        renderItem={({ item: recipe }) => {
          const alreadySaved = saved.has(recipe.id)
          const timeLabel = recipe.total_time_minutes
            ? recipe.total_time_minutes < 60
              ? `${recipe.total_time_minutes}m`
              : `${Math.floor(recipe.total_time_minutes / 60)}h`
            : null

          return (
            <View style={s.card}>
              {recipe.thumbnail_url
                ? <Image source={{ uri: recipe.thumbnail_url }} style={s.thumb} />
                : <View style={s.thumbPlaceholder}><Text style={s.thumbEmoji}>🍳</Text></View>}

              <View style={s.cardBody}>
                <Text style={s.cardTitle} numberOfLines={2}>{recipe.title}</Text>

                <View style={s.cardMeta}>
                  {recipe.cuisine && (
                    <Text style={s.metaTag}>{recipe.cuisine}</Text>
                  )}
                  <Text style={[s.metaTag, { color: DIFF_COLOR[recipe.difficulty] ?? '#aaa' }]}>
                    {recipe.difficulty}
                  </Text>
                  {timeLabel && <Text style={s.metaTag}>⏱ {timeLabel}</Text>}
                </View>

                <View style={s.statsRow}>
                  {recipe.view_count > 0 && (
                    <Text style={s.stat}>👁 {recipe.view_count}</Text>
                  )}
                  {recipe.share_count > 0 && (
                    <Text style={s.stat}>📋 {recipe.share_count}</Text>
                  )}
                  <Text style={s.stat}>{recipe.ingredients.length} ingredients</Text>
                </View>

                <Pressable
                  style={[s.saveBtn, alreadySaved && s.saveBtnDone]}
                  onPress={() => !alreadySaved && duplicateMutation.mutate(recipe.id)}
                  disabled={alreadySaved || duplicateMutation.isPending}
                >
                  <Text style={s.saveBtnText}>
                    {alreadySaved
                      ? `✓ ${t('explore.duplicated')}`
                      : `📋 ${t('explore.duplicate')}`}
                  </Text>
                </Pressable>
              </View>
            </View>
          )
        }}
      />
    </View>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  tabs: { flexDirection: 'row', gap: 8, padding: 16, paddingBottom: 8 },
  tab: { flex: 1, paddingVertical: 10, borderRadius: 12, backgroundColor: '#1a1a1a', alignItems: 'center' },
  tabActive: { backgroundColor: '#ff6b35' },
  tabText: { fontSize: 13, color: '#888', fontWeight: '600' },
  tabTextActive: { color: '#fff' },
  loader: { marginTop: 40 },
  list: { padding: 16, gap: 12, paddingTop: 8 },
  empty: { textAlign: 'center', color: '#555', padding: 40, fontSize: 14 },
  card: { flexDirection: 'row', backgroundColor: '#1a1a1a', borderRadius: 14, overflow: 'hidden', gap: 0 },
  thumb: { width: 100, height: 110, resizeMode: 'cover', flexShrink: 0 },
  thumbPlaceholder: { width: 100, height: 110, backgroundColor: '#111', justifyContent: 'center', alignItems: 'center', flexShrink: 0 },
  thumbEmoji: { fontSize: 28 },
  cardBody: { flex: 1, padding: 12, gap: 6 },
  cardTitle: { fontSize: 14, fontWeight: '600', color: '#f5f5f5', lineHeight: 19 },
  cardMeta: { flexDirection: 'row', gap: 4, flexWrap: 'wrap' },
  metaTag: { fontSize: 10, color: '#888', backgroundColor: '#2a2a2a', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  statsRow: { flexDirection: 'row', gap: 8 },
  stat: { fontSize: 11, color: '#555' },
  saveBtn: { backgroundColor: '#2a1a0a', borderWidth: 1.5, borderColor: '#ff6b35', borderRadius: 8, paddingVertical: 6, alignItems: 'center', marginTop: 2 },
  saveBtnDone: { backgroundColor: '#1a2a1a', borderColor: '#6dbf85' },
  saveBtnText: { fontSize: 12, color: '#ff6b35', fontWeight: '600' },
})
