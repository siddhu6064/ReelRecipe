/**
 * app/(tabs)/planner.tsx — Meal Planner Tab (mobile)
 * Full parity with web MealPlannerPage.tsx
 */

import { useState } from 'react'
import {
  ActivityIndicator, FlatList, Pressable,
  SafeAreaView, ScrollView, StyleSheet, Text, View,
} from 'react-native'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-expo'
import { useTranslation } from 'react-i18next'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

interface Meal { id: string; recipe_id: string; recipe_title: string; slot: string }
interface DayPlan { day_index: number; meals: Meal[] }
interface Plan { id: string; title: string; days: DayPlan[]; is_active: boolean }
interface ShoppingItem { name: string; needed_for: string[] }

export default function PlannerTab() {
  const { getToken } = useAuth()
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [showShopping, setShowShopping] = useState(false)

  const DAYS = [t('planner.days.mon'), t('planner.days.tue'), t('planner.days.wed'),
    t('planner.days.thu'), t('planner.days.fri'), t('planner.days.sat'), t('planner.days.sun')]
  const SLOTS = ['breakfast', 'lunch', 'dinner'] as const

  async function apiFetch(path: string, init: RequestInit = {}) {
    const token = await getToken()
    return fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  }

  const { data: plan, isLoading } = useQuery({
    queryKey: ['active-plan-mobile'],
    queryFn: async () => {
      const r = await apiFetch('/api/meal-plans/active')
      if (r.status === 404) return null
      const { data } = await r.json()
      return data as Plan
    },
  })

  const { data: shopping } = useQuery({
    queryKey: ['shopping-mobile', plan?.id],
    queryFn: async () => {
      const r = await apiFetch(`/api/meal-plans/${plan!.id}/shopping`)
      const { data } = await r.json()
      return data as { items: ShoppingItem[]; total_count: number }
    },
    enabled: !!plan?.id && showShopping,
  })

  const createPlan = useMutation({
    mutationFn: async () => {
      const r = await apiFetch('/api/meal-plans', { method: 'POST', body: JSON.stringify({ title: 'This Week' }) })
      const { data } = await r.json()
      return data as Plan
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['active-plan-mobile'] }),
  })

  if (isLoading) {
    return <SafeAreaView style={s.container}><ActivityIndicator color="#ff6b35" style={s.loader} /></SafeAreaView>
  }

  if (!plan) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.empty}>
          <Text style={s.emptyEmoji}>📅</Text>
          <Text style={s.emptyTitle}>{t('planner.title')}</Text>
          <Text style={s.emptyText}>Plan your meals for the week.</Text>
          <Pressable
            style={[s.createBtn, createPlan.isPending && s.createBtnDisabled]}
            onPress={() => createPlan.mutate()}
            disabled={createPlan.isPending}
          >
            <Text style={s.createBtnText}>
              {createPlan.isPending ? t('planner.creating') : t('planner.createPlan')}
            </Text>
          </Pressable>
        </View>
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <Text style={s.headerTitle}>{plan.title}</Text>
        <Pressable style={s.shoppingBtn} onPress={() => setShowShopping(v => !v)}>
          <Text style={s.shoppingBtnText}>
            🛒 {showShopping ? t('planner.hideShoppingList') : t('planner.shoppingList')}
          </Text>
        </Pressable>
      </View>

      {showShopping && shopping && (
        <View style={s.shoppingPanel}>
          <Text style={s.shoppingTitle}>
            {t('planner.shoppingList')} ({shopping.total_count})
          </Text>
          {shopping.total_count === 0
            ? <Text style={s.allSet}>{t('planner.allSet')}</Text>
            : shopping.items.map((item, i) => (
              <View key={i} style={s.shoppingItem}>
                <Text style={s.shoppingName}>{item.name}</Text>
                <Text style={s.shoppingFor}>{item.needed_for.join(', ')}</Text>
              </View>
            ))}
        </View>
      )}

      <ScrollView style={s.calScroll} showsVerticalScrollIndicator={false}>
        {DAYS.map((dayName, dayIndex) => {
          const day = plan.days.find(d => d.day_index === dayIndex)
          const meals = day?.meals ?? []
          return (
            <View key={dayIndex} style={s.dayRow}>
              <Text style={s.dayName}>{dayName}</Text>
              <View style={s.slots}>
                {SLOTS.map(slot => {
                  const meal = meals.find(m => m.slot === slot)
                  return (
                    <View key={slot} style={s.slot}>
                      <Text style={s.slotLabel}>{slot}</Text>
                      {meal
                        ? <View style={s.mealCard}><Text style={s.mealTitle} numberOfLines={2}>{meal.recipe_title}</Text></View>
                        : <View style={s.emptySlot}><Text style={s.emptySlotText}>+</Text></View>}
                    </View>
                  )
                })}
              </View>
            </View>
          )
        })}
        <View style={{ height: 24 }} />
      </ScrollView>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  loader: { marginTop: 60 },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40, gap: 12 },
  emptyEmoji: { fontSize: 48 },
  emptyTitle: { fontSize: 22, fontWeight: '700', color: '#f5f5f5' },
  emptyText: { fontSize: 14, color: '#888', textAlign: 'center' },
  createBtn: { backgroundColor: '#ff6b35', borderRadius: 14, paddingHorizontal: 28, paddingVertical: 14, marginTop: 8 },
  createBtnDisabled: { opacity: 0.5 },
  createBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, paddingBottom: 8 },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#f5f5f5' },
  shoppingBtn: { backgroundColor: '#1a1a1a', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7 },
  shoppingBtnText: { color: '#aaa', fontSize: 12, fontWeight: '600' },
  shoppingPanel: { backgroundColor: '#1a1a1a', margin: 16, marginTop: 4, borderRadius: 14, padding: 14, gap: 6 },
  shoppingTitle: { fontSize: 14, fontWeight: '700', color: '#f5f5f5', marginBottom: 4 },
  allSet: { color: '#6dbf85', fontSize: 13 },
  shoppingItem: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  shoppingName: { fontSize: 13, color: '#f5f5f5' },
  shoppingFor: { fontSize: 11, color: '#666', maxWidth: '45%', textAlign: 'right' },
  calScroll: { flex: 1 },
  dayRow: { paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 0.5, borderBottomColor: '#1a1a1a' },
  dayName: { fontSize: 11, fontWeight: '700', color: '#ff6b35', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 },
  slots: { flexDirection: 'row', gap: 6 },
  slot: { flex: 1 },
  slotLabel: { fontSize: 9, color: '#555', textTransform: 'uppercase', marginBottom: 3 },
  mealCard: { backgroundColor: '#1a1a2a', borderRadius: 8, padding: 6, minHeight: 38 },
  mealTitle: { fontSize: 11, color: '#aac', lineHeight: 15 },
  emptySlot: { backgroundColor: '#111', borderRadius: 8, minHeight: 38, borderWidth: 1, borderColor: '#2a2a2a', borderStyle: 'dashed', justifyContent: 'center', alignItems: 'center' },
  emptySlotText: { color: '#333', fontSize: 16 },
})
