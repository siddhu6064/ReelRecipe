/**
 * app/cook/[recipeId].tsx — Cook Mode
 *
 * Full-screen cooking interface:
 *   • One step visible at a time — tap next/prev or swipe dots
 *   • Built-in countdown timer for timed steps (background notifications)
 *   • Screen stays on (activateKeepAwakeAsync)
 *   • Progress bar across all steps
 *   • Voice readout of each step via expo-speech (toggle on/off)
 *   • Ingredient quick-reference sheet
 *   • Logs cook session on completion
 */

import { useEffect, useRef, useState } from 'react'
import {
  Animated,
  Dimensions,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useAuth } from '@clerk/clerk-expo'
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake'
import { StepTimer } from '../../components/StepTimer'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

interface Ingredient { name: string; quantity: number | null; unit: string | null }
interface Step { order: number; text: string; timer_seconds: number | null }
interface Recipe { title: string; servings: number; ingredients: Ingredient[]; steps: Step[] }

// ── expo-speech lazy loader ────────────────────────────────────────────────
// Lazy-loaded so the screen doesn't crash in Expo Go if speech isn't available
async function speakStep(text: string): Promise<void> {
  try {
    const Speech = await import('expo-speech')
    await Speech.stop()
    Speech.speak(text, {
      language: 'en',
      pitch: 1.0,
      rate: 0.9,
      onError: () => { /* silent */ },
    })
  } catch { /* expo-speech not available in this build */ }
}

async function stopSpeech(): Promise<void> {
  try {
    const Speech = await import('expo-speech')
    await Speech.stop()
  } catch { /* ignore */ }
}

// ── Main component ─────────────────────────────────────────────────────────
export default function CookModeScreen() {
  const { recipeId } = useLocalSearchParams<{ recipeId: string }>()
  const router = useRouter()
  const { getToken } = useAuth()
  const [recipe, setRecipe]           = useState<Recipe | null>(null)
  const [stepIndex, setStepIndex]     = useState(0)
  const [showIngredients, setShowIngredients] = useState(false)
  const [completed, setCompleted]     = useState(false)
  const [voiceOn, setVoiceOn]         = useState(false)   // TTS toggle
  const fadeAnim = useRef(new Animated.Value(1)).current

  // Keep screen awake while cooking
  useEffect(() => {
    activateKeepAwakeAsync()
    loadRecipe()
    return () => {
      deactivateKeepAwake()
      stopSpeech()
    }
  }, [])

  // Auto-read step aloud when index changes and voice is on
  useEffect(() => {
    if (!recipe || !voiceOn) return
    const step = recipe.steps[stepIndex]
    if (step) speakStep(step.text)
  }, [stepIndex, voiceOn, recipe])

  // Stop speech when voice is toggled off
  useEffect(() => {
    if (!voiceOn) stopSpeech()
  }, [voiceOn])

  async function loadRecipe() {
    try {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/recipes/${recipeId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await res.json()
      setRecipe(data)
    } catch { /* handle offline */ }
  }

  async function logCookSession() {
    try {
      const token = await getToken()
      await fetch(`${API_URL}/api/recipes/${recipeId}/cook-session`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
    } catch { /* non-critical */ }
  }

  function goToStep(index: number) {
    if (!recipe) return
    const next = Math.max(0, Math.min(index, recipe.steps.length - 1))
    Animated.sequence([
      Animated.timing(fadeAnim, { toValue: 0, duration: 110, useNativeDriver: true }),
      Animated.timing(fadeAnim, { toValue: 1, duration: 160, useNativeDriver: true }),
    ]).start()
    setStepIndex(next)
  }

  function handleDone() {
    stopSpeech()
    logCookSession()
    setCompleted(true)
  }

  // ── Loading ──────────────────────────────────────────────────────────────
  if (!recipe) {
    return (
      <SafeAreaView style={s.loadWrap}>
        <Text style={s.loadText}>Loading…</Text>
      </SafeAreaView>
    )
  }

  const steps       = recipe.steps
  const currentStep = steps[stepIndex]
  const isFirst     = stepIndex === 0
  const isLast      = stepIndex === steps.length - 1
  const progress    = (stepIndex + 1) / steps.length

  // ── Completed screen ─────────────────────────────────────────────────────
  if (completed) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.doneCard}>
          <Text style={s.doneIcon}>🎉</Text>
          <Text style={s.doneTitle}>You did it!</Text>
          <Text style={s.doneSub}>{recipe.title} is ready to serve.</Text>
          <Text style={s.doneServings}>Serves {recipe.servings}</Text>
          <Pressable style={s.doneBtn} onPress={() => router.back()}>
            <Text style={s.doneBtnText}>Back to Recipe</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    )
  }

  // ── Cook Mode UI ──────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={s.container}>

      {/* Header */}
      <View style={s.header}>
        <Pressable onPress={() => { stopSpeech(); router.back() }} hitSlop={12}>
          <Text style={s.closeBtn}>✕</Text>
        </Pressable>

        <View style={s.headerCenter}>
          <Text style={s.headerTitle} numberOfLines={1}>{recipe.title}</Text>
          <Text style={s.headerStep}>Step {stepIndex + 1} of {steps.length}</Text>
        </View>

        <View style={s.headerRight}>
          {/* Voice toggle */}
          <Pressable
            onPress={() => setVoiceOn(v => !v)}
            hitSlop={10}
            style={[s.voiceBtn, voiceOn && s.voiceBtnOn]}
          >
            <Text style={s.voiceIcon}>{voiceOn ? '🔊' : '🔇'}</Text>
          </Pressable>
          {/* Ingredients toggle */}
          <Pressable onPress={() => setShowIngredients(i => !i)} hitSlop={10}>
            <Text style={s.ingrBtn}>🧄</Text>
          </Pressable>
        </View>
      </View>

      {/* Progress bar */}
      <View style={s.progressTrack}>
        <Animated.View style={[s.progressFill, { width: `${progress * 100}%` }]} />
      </View>

      {/* Voice status badge */}
      {voiceOn && (
        <View style={s.voiceBadge}>
          <Text style={s.voiceBadgeText}>🔊 Reading step aloud</Text>
        </View>
      )}

      {/* Ingredient quick-reference */}
      {showIngredients && (
        <ScrollView style={s.ingrSheet} showsVerticalScrollIndicator={false}>
          <Text style={s.ingrTitle}>Ingredients</Text>
          {recipe.ingredients.map((ing, i) => (
            <Text key={i} style={s.ingrItem}>
              {ing.quantity != null ? `${ing.quantity} ${ing.unit ?? ''} ` : ''}{ing.name}
            </Text>
          ))}
        </ScrollView>
      )}

      {/* Step card */}
      <Animated.View style={[s.stepCard, { opacity: fadeAnim }]}>
        <Text style={s.stepLabel}>Step {currentStep.order}</Text>
        <Text style={s.stepText}>{currentStep.text}</Text>

        {currentStep.timer_seconds && (
          <View style={s.timerWrap}>
            <StepTimer
              totalSeconds={currentStep.timer_seconds}
              stepTitle={`Step ${currentStep.order}`}
              onComplete={() => { if (voiceOn) speakStep('Timer done! Ready to move on.') }}
            />
          </View>
        )}
      </Animated.View>

      {/* Navigation */}
      <View style={s.navRow}>
        <Pressable
          style={[s.navBtn, isFirst && s.navBtnDisabled]}
          onPress={() => goToStep(stepIndex - 1)}
          disabled={isFirst}
        >
          <Text style={[s.navBtnText, isFirst && s.navBtnTextDisabled]}>← Prev</Text>
        </Pressable>

        {/* Step dots */}
        <View style={s.stepDots}>
          {steps.map((_, i) => (
            <Pressable key={i} onPress={() => goToStep(i)} hitSlop={6}>
              <View style={[s.dot, i === stepIndex && s.dotActive, i < stepIndex && s.dotDone]} />
            </Pressable>
          ))}
        </View>

        {isLast ? (
          <Pressable style={s.doneNavBtn} onPress={handleDone}>
            <Text style={s.doneNavText}>Done 🎉</Text>
          </Pressable>
        ) : (
          <Pressable style={s.navBtn} onPress={() => goToStep(stepIndex + 1)}>
            <Text style={s.navBtnText}>Next →</Text>
          </Pressable>
        )}
      </View>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  container:    { flex: 1, backgroundColor: '#0f0f0f' },
  loadWrap:     { flex: 1, backgroundColor: '#0f0f0f', justifyContent: 'center', alignItems: 'center' },
  loadText:     { color: '#888', fontSize: 16 },

  /* Header */
  header:       { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12 },
  closeBtn:     { fontSize: 20, color: '#888', width: 34 },
  headerCenter: { flex: 1, alignItems: 'center' },
  headerTitle:  { fontSize: 15, fontWeight: '700', color: '#f5f5f5' },
  headerStep:   { fontSize: 11, color: '#666', marginTop: 2 },
  headerRight:  { flexDirection: 'row', gap: 10, alignItems: 'center', width: 68, justifyContent: 'flex-end' },
  voiceBtn:     { padding: 4, borderRadius: 8 },
  voiceBtnOn:   { backgroundColor: '#1a2a1a' },
  voiceIcon:    { fontSize: 20 },
  ingrBtn:      { fontSize: 22 },

  /* Progress */
  progressTrack: { height: 3, backgroundColor: '#1a1a1a', marginHorizontal: 16, borderRadius: 2, marginBottom: 6 },
  progressFill:  { height: '100%', backgroundColor: '#ff6b35', borderRadius: 2 },

  /* Voice badge */
  voiceBadge:     { alignSelf: 'center', backgroundColor: '#1a2a1a', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 4, marginBottom: 4 },
  voiceBadgeText: { fontSize: 11, color: '#6dbf85', fontWeight: '600' },

  /* Ingredient sheet */
  ingrSheet: { backgroundColor: '#1a1a1a', marginHorizontal: 16, borderRadius: 14, padding: 14, marginBottom: 6, maxHeight: 200 },
  ingrTitle: { fontSize: 11, fontWeight: '700', color: '#888', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.6 },
  ingrItem:  { fontSize: 13, color: '#ccc', lineHeight: 22 },

  /* Step card */
  stepCard:  { flex: 1, marginHorizontal: 16, backgroundColor: '#1a1a1a', borderRadius: 20, padding: 28, justifyContent: 'center', alignItems: 'center', gap: 18 },
  stepLabel: { fontSize: 12, fontWeight: '700', color: '#ff6b35', textTransform: 'uppercase', letterSpacing: 1.2 },
  stepText:  { fontSize: 22, color: '#f5f5f5', textAlign: 'center', lineHeight: 34, fontWeight: '500' },
  timerWrap: { marginTop: 12 },

  /* Navigation */
  navRow:        { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14 },
  navBtn:        { backgroundColor: '#1a1a1a', borderRadius: 12, paddingHorizontal: 18, paddingVertical: 12, minWidth: 80, alignItems: 'center' },
  navBtnDisabled: { opacity: 0.25 },
  navBtnText:    { color: '#f5f5f5', fontSize: 15, fontWeight: '600' },
  navBtnTextDisabled: { color: '#555' },
  doneNavBtn:    { backgroundColor: '#6dbf85', borderRadius: 12, paddingHorizontal: 18, paddingVertical: 12, minWidth: 80, alignItems: 'center' },
  doneNavText:   { color: '#fff', fontSize: 15, fontWeight: '700' },
  stepDots:      { flexDirection: 'row', gap: 5, flex: 1, justifyContent: 'center', flexWrap: 'wrap' },
  dot:           { width: 7, height: 7, borderRadius: 4, backgroundColor: '#2a2a2a' },
  dotActive:     { backgroundColor: '#ff6b35', width: 20, borderRadius: 10 },
  dotDone:       { backgroundColor: '#2a4a2a' },

  /* Done screen */
  doneCard:     { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40, gap: 12 },
  doneIcon:     { fontSize: 60 },
  doneTitle:    { fontSize: 32, fontWeight: '800', color: '#f5f5f5' },
  doneSub:      { fontSize: 16, color: '#888', textAlign: 'center' },
  doneServings: { fontSize: 14, color: '#ff6b35', fontWeight: '600' },
  doneBtn:      { marginTop: 20, backgroundColor: '#ff6b35', borderRadius: 14, paddingHorizontal: 32, paddingVertical: 14 },
  doneBtnText:  { color: '#fff', fontSize: 16, fontWeight: '700' },
})
