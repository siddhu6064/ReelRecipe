/**
 * app/recipe/[recipeId].tsx — Recipe Detail (FULL PARITY with web)
 *
 * Features: favourite · notes · servings scaler · AI chat · substitutions
 *           undo · reorder · reset to original · PDF share · visibility toggle
 *           cook session log · public/private badge
 */

import { useRef, useState } from 'react'
import {
  Alert, Image, Pressable, SafeAreaView, ScrollView,
  Share, StyleSheet, Text, TextInput, View,
} from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-expo'
import { useTranslation } from 'react-i18next'
import { UndoSheet } from '../../components/UndoSheet'
import { CollabSheet } from '../../components/CollabSheet'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

type Difficulty = 'easy' | 'medium' | 'hard'
const DIFF_COLOR: Record<Difficulty, string> = { easy: '#6dbf85', medium: '#e8a84a', hard: '#ff6b6b' }

interface Recipe {
  id: string; title: string; description: string | null
  cuisine: string | null; difficulty: Difficulty; servings: number
  prep_time_minutes: number | null; cook_time_minutes: number | null
  total_time_minutes: number | null; thumbnail_url: string | null
  source_url: string; is_favourite: boolean; personal_notes: string | null
  is_edited: boolean; is_public: boolean
  ingredients: { id: string; name: string; quantity: number | null; unit: string | null; preparation: string | null; optional: boolean }[]
  steps: { id: string; order: number; text: string; timer_seconds: number | null }[]
  tags: string[]; nutrition: { calories: number | null; protein_g: number | null; carbs_g: number | null; fat_g: number | null } | null
}

export default function RecipeScreen() {
  const { recipeId } = useLocalSearchParams<{ recipeId: string }>()
  const router = useRouter()
  const { getToken } = useAuth()
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [servings, setServings] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [undoOpen, setUndoOpen] = useState(false)
  const [collabOpen, setCollabOpen] = useState(false)
  const [notesOpen, setNotesOpen] = useState(false)
  const [notesText, setNotesText] = useState('')
  const [chatOpen, setChatOpen] = useState(false)
  const [chatMsg, setChatMsg] = useState('')
  const [chatHistory, setChatHistory] = useState<{role:string;content:string}[]>([])
  const [chatLoading, setChatLoading] = useState(false)
  const [subIngredient, setSubIngredient] = useState<string | null>(null)
  const [subs, setSubs] = useState<{name:string;notes:string}[]>([])

  async function apiFetch(path: string, init: RequestInit = {}) {
    const token = await getToken()
    return fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  }

  const { data: cost } = useQuery({
    queryKey: ['recipe-cost-mob', recipeId],
    queryFn: async () => {
      const r = await apiFetch(`/api/recipes/${recipeId}/cost`)
      if (!r.ok) return null
      const { data } = await r.json()
      return data
    },
    enabled: !!recipeId,
  })

  const { data: recipe, isLoading } = useQuery({
    queryKey: ['recipe', recipeId],
    queryFn: async () => {
      const r = await apiFetch(`/api/recipes/${recipeId}`)
      const { data } = await r.json()
      return data as Recipe
    },
    onSuccess: (r) => { setNotesText(r.personal_notes ?? '') },
  })

  const qc2 = useQueryClient()
  async function invalidate() { qc.invalidateQueries({ queryKey: ['recipe', recipeId] }) }

  async function toggleFavourite() {
    const method = recipe?.is_favourite ? 'DELETE' : 'POST'
    await apiFetch(`/api/recipes/${recipeId}/favourite`, { method })
    invalidate()
  }

  async function saveServings(n: number) {
    setSaving(true)
    try {
      await apiFetch(`/api/recipes/${recipeId}`, { method: 'PUT', body: JSON.stringify({ servings: n }) })
      invalidate(); setServings(null)
    } finally { setSaving(false) }
  }

  async function saveNotes() {
    await apiFetch(`/api/recipes/${recipeId}/notes`, { method: 'PUT', body: JSON.stringify({ notes: notesText || null }) })
    invalidate(); setNotesOpen(false)
  }

  async function resetToOriginal() {
    Alert.alert('Reset to original?', 'Your edits will be replaced with the original AI extraction.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Reset', style: 'destructive', onPress: async () => {
        await apiFetch(`/api/recipes/${recipeId}/reset`, { method: 'POST' })
        invalidate()
      }},
    ])
  }

  async function toggleVisibility() {
    await apiFetch(`/api/recipes/${recipeId}/visibility`, { method: 'PATCH' })
    invalidate()
  }

  async function sendChat() {
    if (!chatMsg.trim()) return
    const msg = chatMsg; setChatMsg(''); setChatLoading(true)
    setChatHistory(h => [...h, { role: 'user', content: msg }])
    try {
      const r = await apiFetch(`/api/ai/chat/${recipeId}`, { method: 'POST', body: JSON.stringify({ message: msg, history: chatHistory }) })
      const { data } = await r.json()
      setChatHistory(h => [...h, { role: 'assistant', content: data.reply }])
    } catch {} finally { setChatLoading(false) }
  }

  async function getSubstitutions(ingredientName: string) {
    setSubIngredient(ingredientName); setSubs([])
    try {
      const r = await apiFetch('/api/ai/substitute', { method: 'POST', body: JSON.stringify({ recipe_id: recipeId, ingredient_name: ingredientName }) })
      const { data } = await r.json()
      setSubs(data.substitutions || [])
    } catch {}
  }

  async function sharePDF() {
    try {
      const r = await apiFetch(`/api/recipes/${recipeId}/export/pdf`)
      if (r.ok) {
        const blob = await r.blob()
        await Share.share({ message: `Recipe: ${recipe?.title}\n${recipe?.source_url}`, title: recipe?.title })
      }
    } catch {}
  }

  async function logCookSession() {
    await apiFetch(`/api/recipes/${recipeId}/cook-session`, { method: 'POST' })
  }

  async function moveItem(items: {id:string}[], i: number, dir: 'up'|'down', type: 'ingredients'|'steps') {
    const arr = [...items]
    const j = dir === 'up' ? i - 1 : i + 1
    if (j < 0 || j >= arr.length) return
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
    await apiFetch(`/api/recipes/${recipeId}/${type}/reorder`, { method: 'PUT', body: JSON.stringify({ ids: arr.map(x => x.id) }) })
    invalidate()
  }

  if (isLoading || !recipe) {
    return <SafeAreaView style={s.loadWrap}><Text style={s.loadText}>{isLoading ? t('common.loading') : t('common.notFound')}</Text></SafeAreaView>
  }

  const displayServings = servings ?? recipe.servings
  const scale = displayServings / recipe.servings
  function scaleQty(qty: number | null) {
    if (qty == null) return ''
    const v = Math.round(qty * scale * 100) / 100
    return v % 1 === 0 ? String(v) : v.toFixed(1)
  }
  const t2 = recipe.total_time_minutes
  const timeLabel = t2 ? (t2 < 60 ? `${t2}m` : `${Math.floor(t2/60)}h ${t2%60}m`) : null

  return (
    <SafeAreaView style={s.container}>
      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Hero */}
        {recipe.thumbnail_url
          ? <Image source={{ uri: recipe.thumbnail_url }} style={s.hero} />
          : <View style={s.heroPlaceholder}><Text style={s.heroEmoji}>🍳</Text></View>}

        <View style={s.content}>
          {/* Title + action row */}
          <View style={s.titleRow}>
            <Text style={s.title}>{recipe.title}</Text>
            <Pressable onPress={toggleFavourite} style={s.favBtn}>
              <Text style={[s.favIcon, recipe.is_favourite && s.favIconActive]}>
                {recipe.is_favourite ? '★' : '☆'}
              </Text>
            </Pressable>
          </View>

          {/* Status badges */}
          <View style={s.badges}>
            {recipe.cuisine && <Text style={s.badge}>{recipe.cuisine}</Text>}
            <Text style={[s.badge, { color: DIFF_COLOR[recipe.difficulty] }]}>{recipe.difficulty}</Text>
            {timeLabel && <Text style={s.badge}>⏱ {timeLabel}</Text>}
            {recipe.is_public && <Text style={[s.badge, s.publicBadge]}>🌍 Public</Text>}
            {recipe.is_edited && <Text style={[s.badge, s.editedBadge]}>✏️ Edited</Text>}
          </View>
          {recipe.tags.slice(0,3).map(tag => <Text key={tag} style={s.dietTag}>#{tag}</Text>)}
          {cost?.total_cost != null && (
            <View style={s.costBadge}>
              <Text style={s.costText}>💰 Est. ${cost.total_cost.toFixed(2)} ({Math.round(cost.coverage_pct * 100)}% priced)</Text>
            </View>
          )}

          {/* Action bar */}
          <View style={s.actionBar}>
            <Pressable style={s.actionBtn} onPress={() => setNotesOpen(o => !o)}>
              <Text style={s.actionBtnText}>📝{recipe.personal_notes ? ' •' : ''}</Text>
            </Pressable>
            {recipe.is_edited && <>
              <Pressable style={s.actionBtn} onPress={() => setUndoOpen(true)}>
                <Text style={s.actionBtnText}>↩</Text>
              </Pressable>
              <Pressable style={s.actionBtn} onPress={resetToOriginal}>
                <Text style={s.actionBtnText}>↺</Text>
              </Pressable>
            </>}
            <Pressable style={s.actionBtn} onPress={toggleVisibility}>
              <Text style={s.actionBtnText}>{recipe.is_public ? '🔒' : '🌍'}</Text>
            </Pressable>
            <Pressable style={s.actionBtn} onPress={sharePDF}>
              <Text style={s.actionBtnText}>📄</Text>
            </Pressable>
            <Pressable style={s.actionBtn} onPress={() => setCollabOpen(true)}>
              <Text style={s.actionBtnText}>👥</Text>
            </Pressable>
          </View>

          {/* Notes panel */}
          {notesOpen && (
            <View style={s.notesPanel}>
              <TextInput style={s.notesInput} multiline placeholder="Your notes, tweaks, substitutions…"
                placeholderTextColor="#555" value={notesText}
                onChangeText={setNotesText} />
              <View style={s.notesRow}>
                <Pressable style={s.notesSave} onPress={saveNotes}><Text style={s.notesSaveText}>Save</Text></Pressable>
                <Pressable onPress={() => setNotesOpen(false)}><Text style={s.notesCancel}>Cancel</Text></Pressable>
              </View>
            </View>
          )}
          {recipe.personal_notes && !notesOpen && (
            <Pressable style={s.notesPreview} onPress={() => setNotesOpen(true)}>
              <Text style={s.notesPreviewText}>📝 {recipe.personal_notes}</Text>
            </Pressable>
          )}

          {/* Servings */}
          <View style={s.servingsRow}>
            <Text style={s.servingsLabel}>{t('recipe.servings')}</Text>
            <Pressable style={s.scaleBtn} onPress={() => setServings(s => Math.max(1, (s ?? recipe.servings) - 1))}><Text style={s.scaleBtnText}>−</Text></Pressable>
            <Text style={s.servingsNum}>{displayServings}</Text>
            <Pressable style={s.scaleBtn} onPress={() => setServings(s => (s ?? recipe.servings) + 1)}><Text style={s.scaleBtnText}>+</Text></Pressable>
            {servings && servings !== recipe.servings && (
              <Pressable style={s.saveSrvBtn} onPress={() => saveServings(displayServings)}>
                <Text style={s.saveSrvText}>{saving ? '…' : '💾'}</Text>
              </Pressable>
            )}
          </View>

          {/* Ingredients */}
          <Text style={s.sectionTitle}>{t('recipe.ingredients')}</Text>
          {recipe.ingredients.map((ing, i) => (
            <View key={ing.id} style={[s.ingrRow, ing.optional && s.ingrOptional]}>
              <View style={s.reorderBtns}>
                <Pressable disabled={i === 0} onPress={() => moveItem(recipe.ingredients, i, 'up', 'ingredients')}>
                  <Text style={[s.reorderBtn, i === 0 && s.reorderBtnDisabled]}>↑</Text>
                </Pressable>
                <Pressable disabled={i === recipe.ingredients.length - 1} onPress={() => moveItem(recipe.ingredients, i, 'down', 'ingredients')}>
                  <Text style={[s.reorderBtn, i === recipe.ingredients.length - 1 && s.reorderBtnDisabled]}>↓</Text>
                </Pressable>
              </View>
              <Text style={s.ingrQty}>{scaleQty(ing.quantity)}{ing.unit ? ` ${ing.unit}` : ''}</Text>
              <View style={s.ingrNameWrap}>
                <Text style={s.ingrName}>{ing.name}{ing.preparation ? `, ${ing.preparation}` : ''}{ing.optional ? ' (opt)' : ''}</Text>
                <Pressable onPress={() => getSubstitutions(ing.name)} hitSlop={8}>
                  <Text style={s.subBtn}>↔</Text>
                </Pressable>
              </View>
            </View>
          ))}

          {/* Substitutions panel */}
          {subIngredient && (
            <View style={s.subPanel}>
              <Text style={s.subTitle}>Substitutes for {subIngredient}</Text>
              {subs.length === 0
                ? <Text style={s.subLoading}>Loading…</Text>
                : subs.map((sub, i) => (
                  <View key={i} style={s.subItem}>
                    <Text style={s.subName}>{sub.name}</Text>
                    <Text style={s.subNotes}>{sub.notes}</Text>
                  </View>
                ))}
              <Pressable onPress={() => setSubIngredient(null)}>
                <Text style={s.subClose}>Close ✕</Text>
              </Pressable>
            </View>
          )}

          {/* Nutrition */}
          {recipe.nutrition && (
            <>
              <Text style={s.sectionTitle}>{t('recipe.nutrition')} <Text style={s.perServing}>{t('recipe.perServing')}</Text></Text>
              <View style={s.macroRow}>
                {[['Calories', recipe.nutrition.calories, 'kcal'], ['Protein', recipe.nutrition.protein_g, 'g'],
                  ['Carbs', recipe.nutrition.carbs_g, 'g'], ['Fat', recipe.nutrition.fat_g, 'g']]
                  .filter(([,v]) => v != null)
                  .map(([label, val, unit]) => (
                    <View key={label as string} style={s.macroCard}>
                      <Text style={s.macroVal}>{Math.round((val as number) * scale)}<Text style={s.macroUnit}>{unit}</Text></Text>
                      <Text style={s.macroLabel}>{label}</Text>
                    </View>
                  ))}
              </View>
            </>
          )}

          {/* Steps */}
          <Text style={s.sectionTitle}>{t('recipe.instructions')}</Text>
          {recipe.steps.map((step, i) => (
            <View key={step.id} style={s.stepRow}>
              <View style={s.reorderBtns}>
                <Pressable disabled={i === 0} onPress={() => moveItem(recipe.steps, i, 'up', 'steps')}>
                  <Text style={[s.reorderBtn, i === 0 && s.reorderBtnDisabled]}>↑</Text>
                </Pressable>
                <Pressable disabled={i === recipe.steps.length - 1} onPress={() => moveItem(recipe.steps, i, 'down', 'steps')}>
                  <Text style={[s.reorderBtn, i === recipe.steps.length - 1 && s.reorderBtnDisabled]}>↓</Text>
                </Pressable>
              </View>
              <View style={s.stepNumBadge}><Text style={s.stepNumText}>{step.order}</Text></View>
              <View style={s.stepBody}>
                <Text style={s.stepText}>{step.text}</Text>
                {step.timer_seconds && <Text style={s.timerBadge}>⏱ {Math.round(step.timer_seconds/60)} min</Text>}
              </View>
            </View>
          ))}

          {/* AI Chat */}
          <Pressable style={s.chatToggle} onPress={() => setChatOpen(o => !o)}>
            <Text style={s.chatToggleText}>💬 {chatOpen ? t('recipe.closeChat') : t('recipe.askAI')}</Text>
          </Pressable>
          {chatOpen && (
            <View style={s.chatBox}>
              <ScrollView style={s.chatHistory} showsVerticalScrollIndicator={false}>
                {chatHistory.length === 0 && <Text style={s.chatHint}>Ask about substitutions, techniques, or scaling.</Text>}
                {chatHistory.map((m, i) => (
                  <View key={i} style={[s.chatMsg, m.role === 'user' ? s.userMsg : s.aiMsg]}>
                    <Text style={m.role === 'user' ? s.userMsgText : s.aiMsgText}>{m.content}</Text>
                  </View>
                ))}
                {chatLoading && <Text style={s.chatLoading}>…</Text>}
              </ScrollView>
              <View style={s.chatInputRow}>
                <TextInput style={s.chatInput} placeholder={t('recipe.chatPlaceholder')}
                  placeholderTextColor="#555" value={chatMsg} onChangeText={setChatMsg}
                  returnKeyType="send" onSubmitEditing={sendChat} />
                <Pressable style={s.chatSend} onPress={sendChat} disabled={!chatMsg.trim() || chatLoading}>
                  <Text style={s.chatSendText}>{t('recipe.send')}</Text>
                </Pressable>
              </View>
            </View>
          )}

          <View style={{ height: 100 }} />
        </View>
      </ScrollView>

      {/* FAB row */}
      <View style={s.fabWrap}>
        <Pressable style={s.fab} onPress={() => { logCookSession(); router.push(`/cook/${recipeId}`) }}>
          <Text style={s.fabText}>👨‍🍳 {t('recipe.startCooking')}</Text>
        </Pressable>
        {recipe.is_edited && (
          <Pressable style={s.undoFab} onPress={() => setUndoOpen(true)}>
            <Text style={s.undoFabText}>↩ {t('recipe.undo')}</Text>
          </Pressable>
        )}
      </View>

      {collabOpen && <CollabSheet recipeId={recipeId!} onClose={() => setCollabOpen(false)} />}
      {undoOpen && <UndoSheet recipeId={recipeId!} onClose={() => setUndoOpen(false)} />}
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  loadWrap: { flex: 1, backgroundColor: '#0f0f0f', justifyContent: 'center', alignItems: 'center' },
  loadText: { color: '#888', fontSize: 16 },
  hero: { width: '100%', height: 220, resizeMode: 'cover' },
  heroPlaceholder: { width: '100%', height: 180, backgroundColor: '#1a1a1a', justifyContent: 'center', alignItems: 'center' },
  heroEmoji: { fontSize: 48 },
  content: { padding: 16 },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 8 },
  title: { flex: 1, fontSize: 22, fontWeight: '800', color: '#f5f5f5', lineHeight: 28 },
  favBtn: { padding: 4 },
  favIcon: { fontSize: 24, color: '#555' },
  favIconActive: { color: '#e8a84a' },
  badges: { flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 6 },
  badge: { fontSize: 11, color: '#888', backgroundColor: '#2a2a2a', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  publicBadge: { color: '#6dbf85', backgroundColor: '#1a2a1a' },
  editedBadge: { color: '#e8a84a', backgroundColor: '#2a1a00' },
  dietTag: { fontSize: 11, color: '#8888cc', marginRight: 6, marginBottom: 8 },
  actionBar: { flexDirection: 'row', gap: 6, marginBottom: 12 },
  actionBtn: { backgroundColor: '#1a1a1a', borderWidth: 1.5, borderColor: '#2a2a2a', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 },
  actionBtnText: { fontSize: 15 },
  notesPanel: { backgroundColor: '#1a1a1a', borderRadius: 12, padding: 12, marginBottom: 10, gap: 8 },
  notesInput: { color: '#f5f5f5', fontSize: 14, lineHeight: 20, minHeight: 70 },
  notesRow: { flexDirection: 'row', gap: 10, justifyContent: 'flex-end' },
  notesSave: { backgroundColor: '#ff6b35', borderRadius: 8, paddingHorizontal: 16, paddingVertical: 7 },
  notesSaveText: { color: '#fff', fontWeight: '600', fontSize: 13 },
  notesCancel: { color: '#666', fontSize: 13, paddingVertical: 7 },
  notesPreview: { backgroundColor: '#1a1a1a', borderRadius: 10, padding: 10, marginBottom: 10 },
  notesPreviewText: { color: '#888', fontSize: 13, lineHeight: 18 },
  servingsRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#1a1a1a', borderRadius: 12, padding: 12, marginBottom: 16 },
  servingsLabel: { color: '#888', fontSize: 14, flex: 1 },
  scaleBtn: { backgroundColor: '#2a2a2a', width: 28, height: 28, borderRadius: 14, justifyContent: 'center', alignItems: 'center' },
  scaleBtnText: { color: '#f5f5f5', fontSize: 16, fontWeight: '700' },
  servingsNum: { fontSize: 17, fontWeight: '700', color: '#f5f5f5', minWidth: 20, textAlign: 'center' },
  saveSrvBtn: { backgroundColor: '#ff6b35', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 },
  saveSrvText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  sectionTitle: { fontSize: 15, fontWeight: '700', color: '#f5f5f5', marginBottom: 10, marginTop: 4, borderBottomWidth: 1, borderBottomColor: '#1a1a1a', paddingBottom: 5 },
  perServing: { fontSize: 11, fontWeight: '400', color: '#666' },
  ingrRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 5, borderBottomWidth: 0.5, borderBottomColor: '#1a1a1a', gap: 8 },
  ingrOptional: { opacity: 0.6 },
  reorderBtns: { gap: 2 },
  reorderBtn: { color: '#555', fontSize: 11, textAlign: 'center' },
  reorderBtnDisabled: { color: '#2a2a2a' },
  ingrQty: { fontSize: 12, color: '#e8a84a', fontFamily: 'Courier', minWidth: 55 },
  ingrNameWrap: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  ingrName: { flex: 1, fontSize: 14, color: '#ddd' },
  subBtn: { fontSize: 14, color: '#555', paddingLeft: 8 },
  subPanel: { backgroundColor: '#1a1a2a', borderRadius: 12, padding: 12, marginBottom: 10, gap: 8 },
  subTitle: { fontSize: 13, fontWeight: '600', color: '#aac', marginBottom: 4 },
  subLoading: { color: '#555', fontSize: 13 },
  subItem: { paddingVertical: 4, borderBottomWidth: 0.5, borderBottomColor: '#2a2a4a' },
  subName: { fontSize: 14, fontWeight: '600', color: '#f5f5f5' },
  subNotes: { fontSize: 12, color: '#888', marginTop: 2 },
  subClose: { color: '#666', fontSize: 12, marginTop: 6, textAlign: 'right' },
  macroRow: { flexDirection: 'row', gap: 6, marginBottom: 14 },
  macroCard: { flex: 1, backgroundColor: '#1a1a1a', borderRadius: 10, padding: 8, alignItems: 'center' },
  macroVal: { fontSize: 16, fontWeight: '700', color: '#f5f5f5' },
  macroUnit: { fontSize: 10, color: '#666' },
  macroLabel: { fontSize: 10, color: '#888', marginTop: 2 },
  stepRow: { flexDirection: 'row', gap: 10, marginBottom: 12 },
  stepNumBadge: { width: 26, height: 26, borderRadius: 13, backgroundColor: '#ff6b35', justifyContent: 'center', alignItems: 'center', flexShrink: 0, marginTop: 2 },
  stepNumText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  stepBody: { flex: 1 },
  stepText: { fontSize: 14, color: '#ddd', lineHeight: 21 },
  timerBadge: { fontSize: 11, color: '#8888cc', marginTop: 4 },
  chatToggle: { backgroundColor: '#1a1a1a', borderRadius: 12, padding: 12, alignItems: 'center', marginTop: 8 },
  chatToggleText: { color: '#aaa', fontSize: 14, fontWeight: '600' },
  chatBox: { backgroundColor: '#111', borderRadius: 12, marginTop: 6, overflow: 'hidden' },
  chatHistory: { padding: 12, maxHeight: 220 },
  chatHint: { color: '#444', fontSize: 12, fontStyle: 'italic' },
  chatMsg: { marginBottom: 8, maxWidth: '85%', borderRadius: 10, padding: 8 },
  userMsg: { alignSelf: 'flex-end', backgroundColor: '#ff6b35' },
  aiMsg: { alignSelf: 'flex-start', backgroundColor: '#1a1a1a', borderWidth: 1, borderColor: '#2a2a2a' },
  userMsgText: { color: '#fff', fontSize: 13 },
  aiMsgText: { color: '#ddd', fontSize: 13 },
  chatLoading: { color: '#555', fontSize: 18 },
  chatInputRow: { flexDirection: 'row', borderTopWidth: 1, borderTopColor: '#1a1a1a' },
  chatInput: { flex: 1, color: '#f5f5f5', padding: 12, fontSize: 13 },
  chatSend: { backgroundColor: '#ff6b35', paddingHorizontal: 14, justifyContent: 'center' },
  chatSendText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  fabWrap: { position: 'absolute', bottom: 20, left: 16, right: 16, gap: 8 },
  fab: { backgroundColor: '#ff6b35', borderRadius: 16, paddingVertical: 15, alignItems: 'center' },
  fabText: { color: '#fff', fontSize: 16, fontWeight: '800' },
  undoFab: { backgroundColor: '#1a1a1a', borderRadius: 12, paddingVertical: 10, alignItems: 'center', borderWidth: 1.5, borderColor: '#333' },
  undoFabText: { color: '#aaa', fontSize: 13, fontWeight: '600' },
  costBadge: { backgroundColor: '#1a2a1a', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5, alignSelf: 'flex-start', marginBottom: 8 },
  costText: { color: '#6dbf85', fontSize: 12, fontWeight: '600' },
})
