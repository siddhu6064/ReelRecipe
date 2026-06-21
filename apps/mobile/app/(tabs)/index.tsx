/**
 * app/tabs/index.tsx — Import Tab
 *
 * Primary entry screen. Handles two flows:
 *   1. User pastes a cooking video URL manually
 *   2. Share intent arrives from another app (iOS Share Sheet / Android intent)
 *
 * On submit → POST /api/jobs/import → navigate to /processing/:jobId
 */

import { useEffect, useState } from 'react'
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { useRouter } from 'expo-router'
import { useAuth } from '@clerk/clerk-expo'
import { useAppStore } from '../../stores/appStore'
import { useShareIntent } from '../../hooks/useShareIntent'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

const PLATFORMS = [
  { icon: '▶️', label: 'YouTube' },
  { icon: '🎵', label: 'TikTok' },
  { icon: '📸', label: 'Instagram' },
  { icon: '📘', label: 'Facebook' },
  { icon: '𝕏', label: 'X' },
]

export default function ImportScreen() {
  const router = useRouter()
  const { getToken } = useAuth()
  const setActiveJobId = useAppStore(s => s.setActiveJobId)
  const { sharedUrl, clearSharedUrl } = useShareIntent()

  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Auto-submit when a share intent arrives
  useEffect(() => {
    if (sharedUrl) {
      setUrl(sharedUrl)
      clearSharedUrl()
      submitUrl(sharedUrl)
    }
  }, [sharedUrl])

  async function submitUrl(target?: string) {
    const finalUrl = (target ?? url).trim()
    if (!finalUrl) return

    setLoading(true)
    setError(null)

    try {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/jobs/import`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ url: finalUrl }),
      })

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail ?? `Error ${res.status}`)
      }

      const { data } = await res.json()
      setActiveJobId(data.jobId)
      setUrl('')
      router.push(`/processing/${data.jobId}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.hero}>
          <Text style={styles.heading}>Paste a cooking video.</Text>
          <Text style={styles.headingAccent}>Get a full recipe.</Text>
          <Text style={styles.sub}>
            Extracts ingredients, steps and nutrition in under 60 seconds.
          </Text>
        </View>

        <View style={styles.inputCard}>
          <TextInput
            style={styles.input}
            placeholder="https://youtube.com/watch?v=…"
            placeholderTextColor="#555"
            value={url}
            onChangeText={setUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="go"
            onSubmitEditing={() => submitUrl()}
            editable={!loading}
          />
          <Pressable
            style={[styles.btn, (!url.trim() || loading) && styles.btnDisabled]}
            onPress={() => submitUrl()}
            disabled={!url.trim() || loading}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.btnText}>Extract Recipe</Text>}
          </Pressable>
        </View>

        {error && <Text style={styles.error}>{error}</Text>}

        <View style={styles.platformRow}>
          {PLATFORMS.map(p => (
            <View key={p.label} style={styles.platformBadge}>
              <Text style={styles.platformText}>{p.icon} {p.label}</Text>
            </View>
          ))}
        </View>

        <View style={styles.features}>
          {[
            { icon: '🧄', title: 'Smart Pantry', desc: 'Track ingredients. See what you can cook.' },
            { icon: '🤖', title: 'AI Suggestions', desc: 'Generate recipes from your pantry.' },
            { icon: '👨‍🍳', title: 'Cook Mode', desc: 'Step-by-step full-screen with timers.' },
          ].map(f => (
            <View key={f.title} style={styles.feature}>
              <Text style={styles.featureIcon}>{f.icon}</Text>
              <View style={styles.featureText}>
                <Text style={styles.featureTitle}>{f.title}</Text>
                <Text style={styles.featureDesc}>{f.desc}</Text>
              </View>
            </View>
          ))}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#0f0f0f' },
  scroll: { flex: 1 },
  container: { padding: 24, paddingBottom: 40 },
  hero: { marginTop: 16, marginBottom: 28 },
  heading: { fontSize: 30, fontWeight: '700', color: '#f5f5f5', lineHeight: 36 },
  headingAccent: { fontSize: 30, fontWeight: '700', color: '#ff6b35', lineHeight: 36, marginBottom: 10 },
  sub: { fontSize: 15, color: '#888', lineHeight: 22 },
  inputCard: { backgroundColor: '#1a1a1a', borderRadius: 16, padding: 16, gap: 10, marginBottom: 12 },
  input: {
    backgroundColor: '#111', borderWidth: 1.5, borderColor: '#2a2a2a',
    borderRadius: 12, padding: 14, fontSize: 15, color: '#f5f5f5',
  },
  btn: {
    backgroundColor: '#ff6b35', borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', justifyContent: 'center',
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  error: { color: '#ff5555', fontSize: 13, marginBottom: 10, textAlign: 'center' },
  platformRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 28, justifyContent: 'center' },
  platformBadge: { backgroundColor: '#1a1a1a', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5 },
  platformText: { color: '#666', fontSize: 12 },
  features: { gap: 12 },
  feature: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1a1a1a', borderRadius: 14, padding: 16, gap: 14 },
  featureIcon: { fontSize: 24 },
  featureText: { flex: 1 },
  featureTitle: { fontSize: 15, fontWeight: '600', color: '#f5f5f5' },
  featureDesc: { fontSize: 13, color: '#888', marginTop: 2 },
})
