/**
 * components/StepTimer.tsx
 *
 * Countdown timer for a single Cook Mode step.
 * Features:
 *   - Start / Pause / Reset
 *   - Visual ring that pulses at ≤10s
 *   - Schedules a LOCAL NOTIFICATION when started so the timer fires
 *     even if the user switches to another app or the screen locks.
 *   - Cancels the notification if the user pauses or resets.
 */

import { useEffect, useRef, useState } from 'react'
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native'

interface Props {
  totalSeconds: number
  stepTitle?: string          // used as notification title
  onComplete?: () => void
  autoStart?: boolean
}

// Lazy-load expo-notifications — only available in native builds
async function scheduleNotification(
  seconds: number,
  title: string,
): Promise<string | null> {
  try {
    const N = await import('expo-notifications')
    const id = await N.scheduleNotificationAsync({
      content: {
        title: '⏱ Timer done!',
        body: title ? `"${title}" is ready.` : 'Your cooking timer has finished.',
        sound: 'default',
        data: { type: 'cook_timer' },
      },
      trigger: { type: 'timeInterval', seconds, repeats: false } as unknown,
    })
    return id
  } catch {
    return null
  }
}

async function cancelNotification(id: string | null) {
  if (!id) return
  try {
    const N = await import('expo-notifications')
    await N.cancelScheduledNotificationAsync(id)
  } catch { /* ignore */ }
}

export function StepTimer({ totalSeconds, stepTitle = '', onComplete, autoStart = false }: Props) {
  const [remaining, setRemaining] = useState(totalSeconds)
  const [running, setRunning] = useState(autoStart)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const notifIdRef = useRef<string | null>(null)
  const pulseAnim = useRef(new Animated.Value(1)).current

  // Pulse when 10s remaining
  useEffect(() => {
    if (remaining === 10 && running) {
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.08, duration: 200, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 200, useNativeDriver: true }),
      ]).start()
    }
  }, [remaining])

  // Start/stop interval
  useEffect(() => {
    if (running) {
      intervalRef.current = setInterval(() => {
        setRemaining(r => {
          if (r <= 1) {
            clearInterval(intervalRef.current!)
            setRunning(false)
            notifIdRef.current = null   // notification already fired
            onComplete?.()
            return 0
          }
          return r - 1
        })
      }, 1000)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [running])

  async function handleStartPause() {
    if (running) {
      // Pause — cancel the background notification
      await cancelNotification(notifIdRef.current)
      notifIdRef.current = null
      setRunning(false)
    } else {
      // Start — schedule background notification
      if (remaining > 0) {
        const id = await scheduleNotification(remaining, stepTitle)
        notifIdRef.current = id
        setRunning(true)
      }
    }
  }

  async function handleReset() {
    await cancelNotification(notifIdRef.current)
    notifIdRef.current = null
    if (intervalRef.current) clearInterval(intervalRef.current)
    setRemaining(totalSeconds)
    setRunning(false)
  }

  const mins = Math.floor(remaining / 60)
  const secs = remaining % 60
  const timeStr = mins > 0
    ? `${mins}:${String(secs).padStart(2, '0')}`
    : `${secs}s`
  const isDone = remaining === 0
  const isWarning = remaining <= 10 && remaining > 0

  return (
    <Animated.View style={[s.container, { transform: [{ scale: pulseAnim }] }]}>
      <View style={[s.ring, isDone && s.ringDone, isWarning && s.ringWarning]}>
        <Text style={[s.time, isDone && s.timeDone, isWarning && s.timeWarning]}>
          {isDone ? '✓' : timeStr}
        </Text>
        <Text style={s.label}>
          {isDone ? 'Done!' : running ? 'running' : 'paused'}
        </Text>
      </View>

      <View style={s.btnRow}>
        <Pressable
          style={[s.btn, isDone && s.btnDisabled]}
          onPress={handleStartPause}
          disabled={isDone}
        >
          <Text style={s.btnText}>{running ? '⏸ Pause' : '▶ Start'}</Text>
        </Pressable>
        <Pressable style={[s.btn, s.btnSecondary]} onPress={handleReset}>
          <Text style={[s.btnText, s.btnTextSecondary]}>↺ Reset</Text>
        </Pressable>
      </View>

      {running && !isDone && (
        <Text style={s.bgNote}>Timer runs in background</Text>
      )}
    </Animated.View>
  )
}

const s = StyleSheet.create({
  container: { alignItems: 'center', gap: 12 },
  ring: {
    width: 100, height: 100, borderRadius: 50,
    borderWidth: 4, borderColor: '#ff6b35',
    justifyContent: 'center', alignItems: 'center',
  },
  ringDone: { borderColor: '#6dbf85' },
  ringWarning: { borderColor: '#ff5555' },
  time: { fontSize: 22, fontWeight: '700', color: '#ff6b35' },
  timeDone: { color: '#6dbf85' },
  timeWarning: { color: '#ff5555' },
  label: { fontSize: 10, color: '#666', marginTop: 2 },
  btnRow: { flexDirection: 'row', gap: 8 },
  btn: { backgroundColor: '#ff6b35', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  btnDisabled: { opacity: 0.4 },
  btnSecondary: { backgroundColor: '#2a2a2a' },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 13 },
  btnTextSecondary: { color: '#aaa' },
  bgNote: { fontSize: 10, color: '#555', fontStyle: 'italic' },
})
