/**
 * components/UndoSheet.tsx
 *
 * Bottom sheet that shows the recipe edit history and lets the user
 * undo the most recent edit. Called from the recipe detail FAB area.
 *
 * Usage:
 *   <UndoSheet recipeId={id} onClose={() => setOpen(false)} />
 */

import { useEffect, useState } from 'react'
import {
  ActivityIndicator,
  Animated,
  Dimensions,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native'
import { useAuth } from '@clerk/clerk-expo'
import { useQueryClient } from '@tanstack/react-query'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'
const { height: SCREEN_H } = Dimensions.get('window')

interface HistoryEntry {
  snapshot_id: string
  label: string
  created_at: string
}

interface Props {
  recipeId: string
  onClose: () => void
}

export function UndoSheet({ recipeId, onClose }: Props) {
  const { getToken } = useAuth()
  const qc = useQueryClient()
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [undoing, setUndoing] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const slideAnim = useState(new Animated.Value(SCREEN_H))[0]

  useEffect(() => {
    Animated.spring(slideAnim, { toValue: 0, useNativeDriver: true, tension: 60, friction: 10 }).start()
    fetchHistory()
  }, [])

  async function fetchHistory() {
    try {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/recipes/${recipeId}/history`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const { data } = await res.json()
      setHistory(data)
    } catch { /* silent */ } finally {
      setLoading(false)
    }
  }

  async function handleUndo() {
    setUndoing(true)
    try {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/recipes/${recipeId}/undo`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (res.ok) {
        const { undid } = await res.json()
        setFeedback(`Undid: ${undid}`)
        qc.invalidateQueries({ queryKey: ['recipe', recipeId] })
        await fetchHistory()
        setTimeout(() => { setFeedback(null); if (history.length <= 1) onClose() }, 1500)
      }
    } catch { /* silent */ } finally {
      setUndoing(false)
    }
  }

  function close() {
    Animated.timing(slideAnim, { toValue: SCREEN_H, duration: 220, useNativeDriver: true }).start(onClose)
  }

  return (
    <View style={s.backdrop}>
      <Pressable style={StyleSheet.absoluteFill} onPress={close} />
      <Animated.View style={[s.sheet, { transform: [{ translateY: slideAnim }] }]}>
        <SafeAreaView>
          <View style={s.handle} />
          <View style={s.header}>
            <Text style={s.title}>Edit History</Text>
            <Pressable onPress={close}>
              <Text style={s.closeText}>Done</Text>
            </Pressable>
          </View>

          {feedback && (
            <View style={s.feedbackBox}>
              <Text style={s.feedbackText}>{feedback}</Text>
            </View>
          )}

          {loading && <ActivityIndicator style={s.loader} color="#ff6b35" />}

          {!loading && history.length === 0 && (
            <Text style={s.empty}>No edits to undo.</Text>
          )}

          <ScrollView style={s.list} showsVerticalScrollIndicator={false}>
            {history.map((entry, i) => (
              <View key={entry.snapshot_id} style={[s.entry, i === 0 && s.entryLatest]}>
                <View style={s.entryLeft}>
                  {i === 0 && <Text style={s.latestBadge}>Latest</Text>}
                  <Text style={s.entryLabel}>{entry.label}</Text>
                  <Text style={s.entryTime}>
                    {new Date(entry.created_at).toLocaleString([], {
                      month: 'short', day: 'numeric',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </Text>
                </View>
              </View>
            ))}
          </ScrollView>

          {history.length > 0 && (
            <View style={s.undoWrap}>
              <Pressable
                style={[s.undoBtn, undoing && s.undoBtnDisabled]}
                onPress={handleUndo}
                disabled={undoing}
              >
                {undoing
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={s.undoBtnText}>↩ Undo most recent edit</Text>}
              </Pressable>
            </View>
          )}
        </SafeAreaView>
      </Animated.View>
    </View>
  )
}

const s = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end', zIndex: 100 },
  sheet: { backgroundColor: '#1a1a1a', borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: SCREEN_H * 0.65 },
  handle: { width: 40, height: 4, backgroundColor: '#333', borderRadius: 2, alignSelf: 'center', marginTop: 10 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingVertical: 14 },
  title: { fontSize: 17, fontWeight: '700', color: '#f5f5f5' },
  closeText: { fontSize: 15, color: '#ff6b35', fontWeight: '600' },
  feedbackBox: { backgroundColor: '#2d6b3a', marginHorizontal: 16, borderRadius: 10, padding: 10, marginBottom: 8 },
  feedbackText: { color: '#fff', fontSize: 13, textAlign: 'center' },
  loader: { padding: 24 },
  empty: { color: '#666', fontSize: 14, textAlign: 'center', padding: 24 },
  list: { maxHeight: 280 },
  entry: { flexDirection: 'row', padding: 14, borderBottomWidth: 0.5, borderBottomColor: '#111', marginHorizontal: 16 },
  entryLatest: { backgroundColor: '#111', borderRadius: 10 },
  entryLeft: { flex: 1, gap: 3 },
  latestBadge: { fontSize: 10, color: '#ff6b35', fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  entryLabel: { fontSize: 14, color: '#f5f5f5' },
  entryTime: { fontSize: 12, color: '#666' },
  undoWrap: { padding: 16 },
  undoBtn: { backgroundColor: '#ff6b35', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  undoBtnDisabled: { opacity: 0.5 },
  undoBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
})
