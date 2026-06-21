/**
 * app/processing/[jobId].tsx
 *
 * Shows live extraction progress by polling GET /api/jobs/:id every 2s.
 * On completion → navigate to /recipe/:resultId
 * On failure    → show error with retry option
 */

import { useEffect, useRef, useState } from 'react'
import { ActivityIndicator, Animated, Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useAuth } from '@clerk/clerk-expo'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'
const POLL_MS = 2000

const STEP_LABELS: Record<string, string> = {
  fetching_video: 'Fetching video…',
  transcribing: 'Transcribing audio…',
  extracting_recipe: 'Extracting recipe with AI…',
  fetching_nutrition: 'Fetching nutrition data…',
  finalizing: 'Saving recipe…',
}

type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'

interface JobState {
  status: JobStatus
  progress: number
  currentStep: string | null
  progressMessage: string | null
  error: string | null
  errorCode: string | null
  resultId: string | null
}

export default function ProcessingScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>()
  const router = useRouter()
  const { getToken } = useAuth()
  const [job, setJob] = useState<JobState | null>(null)
  const progressAnim = useRef(new Animated.Value(0)).current
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    poll()
    intervalRef.current = setInterval(poll, POLL_MS)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [jobId])

  useEffect(() => {
    if (job?.progress != null) {
      Animated.timing(progressAnim, {
        toValue: job.progress / 100,
        duration: 400,
        useNativeDriver: false,
      }).start()
    }
  }, [job?.progress])

  async function poll() {
    try {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/jobs/${jobId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) return
      const { data } = await res.json()
      setJob(data)

      if (data.status === 'completed') {
        if (intervalRef.current) clearInterval(intervalRef.current)
        router.replace(`/recipe/${data.resultId}`)
      } else if (data.status === 'failed') {
        if (intervalRef.current) clearInterval(intervalRef.current)
      }
    } catch { /* network retry handled by interval */ }
  }

  const stepLabel = job?.currentStep
    ? STEP_LABELS[job.currentStep] ?? job.progressMessage ?? 'Processing…'
    : 'Starting…'

  const barWidth = progressAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', '100%'],
  })

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Extracting Recipe</Text>

        {job?.status !== 'failed' && (
          <>
            <View style={styles.progressTrack}>
              <Animated.View style={[styles.progressFill, { width: barWidth }]} />
            </View>
            <Text style={styles.pct}>{job?.progress ?? 0}%</Text>
            <Text style={styles.stepLabel}>{stepLabel}</Text>
            {(!job || job.status === 'queued') && (
              <ActivityIndicator style={styles.spinner} color="#ff6b35" size="large" />
            )}
          </>
        )}

        {job?.status === 'failed' && (
          <View style={styles.errorBox}>
            <Text style={styles.errorIcon}>⚠️</Text>
            <Text style={styles.errorTitle}>Extraction failed</Text>
            <Text style={styles.errorMsg}>
              {job.error ?? 'Something went wrong. Please try a different video.'}
            </Text>
            <Pressable style={styles.retryBtn} onPress={() => router.replace('/import')}>
              <Text style={styles.retryText}>Try another video</Text>
            </Pressable>
          </View>
        )}
      </View>

      <Text style={styles.hint}>
        This usually takes under 60 seconds.{'\n'}You can navigate away — we'll notify you when it's ready.
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f', justifyContent: 'center', padding: 24 },
  card: { backgroundColor: '#1a1a1a', borderRadius: 20, padding: 28, alignItems: 'center', gap: 16 },
  title: { fontSize: 20, fontWeight: '700', color: '#f5f5f5' },
  progressTrack: { width: '100%', height: 8, backgroundColor: '#2a2a2a', borderRadius: 4, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#ff6b35', borderRadius: 4 },
  pct: { fontSize: 32, fontWeight: '700', color: '#ff6b35' },
  stepLabel: { fontSize: 14, color: '#888', textAlign: 'center', lineHeight: 20 },
  spinner: { marginTop: 8 },
  errorBox: { alignItems: 'center', gap: 10 },
  errorIcon: { fontSize: 36 },
  errorTitle: { fontSize: 18, fontWeight: '700', color: '#f5f5f5' },
  errorMsg: { fontSize: 14, color: '#888', textAlign: 'center', lineHeight: 20 },
  retryBtn: { backgroundColor: '#ff6b35', borderRadius: 12, paddingHorizontal: 24, paddingVertical: 12, marginTop: 8 },
  retryText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  hint: { color: '#444', fontSize: 12, textAlign: 'center', marginTop: 20, lineHeight: 18 },
})
