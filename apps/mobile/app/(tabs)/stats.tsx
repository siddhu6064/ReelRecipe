/**
 * app/(tabs)/stats.tsx — Stats Tab (mobile)
 * Full parity with web StatsPage.tsx — Wrapped-style cooking stats.
 */

import {
  ActivityIndicator, SafeAreaView, ScrollView,
  StyleSheet, Text, View,
} from 'react-native'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-expo'
import { useTranslation } from 'react-i18next'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

interface Stats {
  total_recipes: number; public_recipes: number; unique_cuisines: number
  top_cuisines: string[]; top_tags: string[]; favourite_ingredient: string | null
  cook_sessions: number; most_cooked_cuisine: string | null
  recipes_this_month: number; recipes_this_year: number
  avg_cook_time_minutes: number | null; current_streak_days: number
  generated_at: string
}

export default function StatsTab() {
  const { getToken } = useAuth()
  const { t } = useTranslation()

  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats-mobile'],
    queryFn: async () => {
      const token = await getToken()
      const r = await fetch(`${API_URL}/api/users/me/stats`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await r.json()
      return data as Stats
    },
  })

  if (isLoading) {
    return <SafeAreaView style={s.container}><ActivityIndicator color="#ff6b35" style={s.loader} /></SafeAreaView>
  }
  if (!stats) return null

  const timeLabel = stats.avg_cook_time_minutes
    ? stats.avg_cook_time_minutes < 60
      ? `${stats.avg_cook_time_minutes}m`
      : `${Math.floor(stats.avg_cook_time_minutes / 60)}h ${stats.avg_cook_time_minutes % 60}m`
    : null

  return (
    <SafeAreaView style={s.container}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Header */}
        <View style={s.header}>
          <Text style={s.headerEmoji}>👨‍🍳</Text>
          <Text style={s.heading}>Your Cooking Wrapped</Text>
          <Text style={s.subheading}>Everything you've cooked with ReelRecipes</Text>
        </View>

        {/* Big 3 */}
        <View style={s.bigRow}>
          <BigStat value={stats.total_recipes} label="Recipes" emoji="📖" accent />
          <BigStat value={stats.cook_sessions} label="Sessions" emoji="🍳" />
          <BigStat value={stats.unique_cuisines} label="Cuisines" emoji="🌍" />
        </View>

        {/* Detail cards */}
        <View style={s.detailGrid}>
          {stats.favourite_ingredient && (
            <DetailCard emoji="❤️" label="Fav ingredient" value={stats.favourite_ingredient} />
          )}
          {stats.most_cooked_cuisine && (
            <DetailCard emoji="🏆" label="Most cooked" value={stats.most_cooked_cuisine} />
          )}
          {timeLabel && (
            <DetailCard emoji="⏱" label="Avg cook time" value={timeLabel} />
          )}
          {stats.current_streak_days > 0 && (
            <DetailCard emoji="🔥" label="Streak" value={`${stats.current_streak_days} day${stats.current_streak_days > 1 ? 's' : ''}`} />
          )}
          <DetailCard emoji="📅" label="This month" value={String(stats.recipes_this_month)} />
          <DetailCard emoji="🌟" label="Public" value={String(stats.public_recipes)} />
        </View>

        {/* Top cuisines */}
        {stats.top_cuisines.length > 0 && (
          <View style={s.tagsSection}>
            <Text style={s.tagsLabel}>CUISINES EXPLORED</Text>
            <View style={s.tagRow}>
              {stats.top_cuisines.map(c => <Text key={c} style={s.tag}>{c}</Text>)}
            </View>
          </View>
        )}

        {/* Top tags */}
        {stats.top_tags.length > 0 && (
          <View style={s.tagsSection}>
            <Text style={s.tagsLabel}>FAVOURITE STYLES</Text>
            <View style={s.tagRow}>
              {stats.top_tags.map(tag => <Text key={tag} style={[s.tag, s.tagAccent]}>#{tag}</Text>)}
            </View>
          </View>
        )}

        <Text style={s.footer}>
          Generated {new Date(stats.generated_at).toLocaleDateString()}
        </Text>
      </ScrollView>
    </SafeAreaView>
  )
}

function BigStat({ value, label, emoji, accent }: { value: number; label: string; emoji: string; accent?: boolean }) {
  return (
    <View style={[s.bigStat, accent && s.bigStatAccent]}>
      <Text style={s.bigStatEmoji}>{emoji}</Text>
      <Text style={[s.bigStatValue, accent && s.bigStatValueAccent]}>{value}</Text>
      <Text style={s.bigStatLabel}>{label}</Text>
    </View>
  )
}

function DetailCard({ emoji, label, value }: { emoji: string; label: string; value: string }) {
  return (
    <View style={s.detailCard}>
      <Text style={s.detailEmoji}>{emoji}</Text>
      <View>
        <Text style={s.detailValue}>{value}</Text>
        <Text style={s.detailLabel}>{label}</Text>
      </View>
    </View>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  loader: { marginTop: 60 },
  scroll: { padding: 0, paddingBottom: 30 },
  header: { backgroundColor: '#ff6b35', padding: 24, alignItems: 'center', gap: 6 },
  headerEmoji: { fontSize: 40 },
  heading: { fontSize: 22, fontWeight: '800', color: '#fff' },
  subheading: { fontSize: 13, color: 'rgba(255,255,255,0.8)', textAlign: 'center' },
  bigRow: { flexDirection: 'row', padding: 12, gap: 8 },
  bigStat: { flex: 1, backgroundColor: '#1a1a1a', borderRadius: 14, padding: 14, alignItems: 'center', gap: 4 },
  bigStatAccent: { backgroundColor: '#2a1a0a', borderWidth: 1.5, borderColor: '#ff6b35' },
  bigStatEmoji: { fontSize: 22 },
  bigStatValue: { fontSize: 28, fontWeight: '800', color: '#888' },
  bigStatValueAccent: { color: '#ff6b35' },
  bigStatLabel: { fontSize: 10, color: '#666', textTransform: 'uppercase', letterSpacing: 0.5 },
  detailGrid: { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: 12, gap: 8 },
  detailCard: { width: '47%', backgroundColor: '#1a1a1a', borderRadius: 12, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10 },
  detailEmoji: { fontSize: 20 },
  detailValue: { fontSize: 15, fontWeight: '700', color: '#f5f5f5' },
  detailLabel: { fontSize: 10, color: '#666', marginTop: 2 },
  tagsSection: { padding: 16, paddingBottom: 0 },
  tagsLabel: { fontSize: 10, fontWeight: '700', color: '#555', letterSpacing: 1, marginBottom: 8 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  tag: { backgroundColor: '#1a1a1a', color: '#aaa', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20, fontSize: 12 },
  tagAccent: { backgroundColor: '#1a2a1a', color: '#6dbf85' },
  footer: { textAlign: 'right', color: '#333', fontSize: 11, padding: 16, paddingTop: 20 },
})
