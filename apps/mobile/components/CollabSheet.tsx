/**
 * components/CollabSheet.tsx
 *
 * Bottom sheet for sharing a recipe with collaborators.
 * Generates viewer/editor invite links, lists current collaborators,
 * and allows role changes and removal.
 */

import { useEffect, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  Animated,
  Clipboard,
  Dimensions,
  Pressable,
  SafeAreaView,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native'
import { useAuth } from '@clerk/clerk-expo'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'
const { height: SCREEN_H } = Dimensions.get('window')

interface Collaborator {
  user_id: string; email: string | null; role: string
  accepted: boolean; invited_at: string
}

interface Props {
  recipeId: string
  onClose: () => void
}

export function CollabSheet({ recipeId, onClose }: Props) {
  const { getToken } = useAuth()
  const [accepted, setAccepted] = useState<Collaborator[]>([])
  const [pending, setPending] = useState<Collaborator[]>([])
  const [loading, setLoading] = useState(true)
  const [inviting, setInviting] = useState(false)
  const [inviteLink, setInviteLink] = useState<string | null>(null)
  const slideAnim = useState(new Animated.Value(SCREEN_H))[0]

  useEffect(() => {
    Animated.spring(slideAnim, { toValue: 0, useNativeDriver: true, tension: 60, friction: 10 }).start()
    fetchCollaborators()
  }, [])

  async function apiFetch(path: string, init: RequestInit = {}) {
    const token = await getToken()
    return fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  }

  async function fetchCollaborators() {
    try {
      const r = await apiFetch(`/api/recipes/${recipeId}/collaborators`)
      const { data } = await r.json()
      setAccepted(data.accepted ?? [])
      setPending(data.pending ?? [])
    } catch {} finally { setLoading(false) }
  }

  async function createInvite(role: 'viewer' | 'editor') {
    setInviting(true)
    setInviteLink(null)
    try {
      const r = await apiFetch(`/api/recipes/${recipeId}/invite`, {
        method: 'POST', body: JSON.stringify({ role }),
      })
      const { data } = await r.json()
      const link = data.invite_url as string
      setInviteLink(link)
      await fetchCollaborators()
    } catch {} finally { setInviting(false) }
  }

  async function shareInvite() {
    if (!inviteLink) return
    await Share.share({ message: `Join my recipe on ReelRecipes: ${inviteLink}`, url: inviteLink })
  }

  async function copyInvite() {
    if (!inviteLink) return
    Clipboard.setString(inviteLink)
    Alert.alert('Copied!', 'Invite link copied to clipboard.')
  }

  async function changeRole(userId: string, newRole: string) {
    await apiFetch(`/api/recipes/${recipeId}/collaborators/${userId}`, {
      method: 'PATCH', body: JSON.stringify({ role: newRole }),
    })
    fetchCollaborators()
  }

  async function removeCollaborator(userId: string) {
    Alert.alert('Remove collaborator?', 'They will lose access to this recipe.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: async () => {
        await apiFetch(`/api/recipes/${recipeId}/collaborators/${userId}`, { method: 'DELETE' })
        fetchCollaborators()
      }},
    ])
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
            <Text style={s.title}>👥 Share Recipe</Text>
            <Pressable onPress={close}><Text style={s.closeText}>Done</Text></Pressable>
          </View>

          <ScrollView style={s.scroll} showsVerticalScrollIndicator={false}>

            {/* Invite buttons */}
            <Text style={s.sectionLabel}>GENERATE INVITE LINK</Text>
            <View style={s.inviteRow}>
              <Pressable
                style={[s.inviteBtn, inviting && s.inviteBtnDisabled]}
                onPress={() => createInvite('viewer')}
                disabled={inviting}
              >
                <Text style={s.inviteBtnText}>👁 Invite Viewer</Text>
              </Pressable>
              <Pressable
                style={[s.inviteBtn, s.inviteBtnEditor, inviting && s.inviteBtnDisabled]}
                onPress={() => createInvite('editor')}
                disabled={inviting}
              >
                <Text style={s.inviteBtnText}>✏️ Invite Editor</Text>
              </Pressable>
            </View>

            {inviting && <ActivityIndicator color="#ff6b35" style={{ marginVertical: 8 }} />}

            {inviteLink && (
              <View style={s.linkBox}>
                <Text style={s.linkText} numberOfLines={1}>{inviteLink}</Text>
                <View style={s.linkActions}>
                  <Pressable style={s.linkBtn} onPress={copyInvite}>
                    <Text style={s.linkBtnText}>📋 Copy</Text>
                  </Pressable>
                  <Pressable style={[s.linkBtn, s.linkBtnShare]} onPress={shareInvite}>
                    <Text style={s.linkBtnText}>↗ Share</Text>
                  </Pressable>
                </View>
              </View>
            )}

            {/* Active collaborators */}
            {loading
              ? <ActivityIndicator color="#ff6b35" style={{ marginTop: 16 }} />
              : <>
                {accepted.length > 0 && (
                  <>
                    <Text style={s.sectionLabel}>ACTIVE COLLABORATORS</Text>
                    {accepted.map(c => (
                      <View key={c.user_id} style={s.collabRow}>
                        <View style={s.collabInfo}>
                          <Text style={s.collabEmail}>{c.email ?? c.user_id}</Text>
                          <View style={[s.roleBadge, c.role === 'editor' && s.roleBadgeEditor]}>
                            <Text style={s.roleText}>{c.role}</Text>
                          </View>
                        </View>
                        <View style={s.collabActions}>
                          <Pressable
                            style={s.roleToggle}
                            onPress={() => changeRole(c.user_id, c.role === 'viewer' ? 'editor' : 'viewer')}
                          >
                            <Text style={s.roleToggleText}>
                              → {c.role === 'viewer' ? 'editor' : 'viewer'}
                            </Text>
                          </Pressable>
                          <Pressable onPress={() => removeCollaborator(c.user_id)}>
                            <Text style={s.removeText}>✕</Text>
                          </Pressable>
                        </View>
                      </View>
                    ))}
                  </>
                )}

                {pending.length > 0 && (
                  <>
                    <Text style={s.sectionLabel}>PENDING ({pending.length})</Text>
                    {pending.map((c, i) => (
                      <View key={i} style={[s.collabRow, s.pendingRow]}>
                        <Text style={s.pendingText}>Invite link generated — {c.role}</Text>
                        <Pressable onPress={() => removeCollaborator(c.user_id)}>
                          <Text style={s.removeText}>✕</Text>
                        </Pressable>
                      </View>
                    ))}
                  </>
                )}

                {accepted.length === 0 && pending.length === 0 && !inviteLink && (
                  <Text style={s.emptyText}>No collaborators yet. Generate an invite link above.</Text>
                )}
              </>
            }

            <View style={{ height: 20 }} />
          </ScrollView>
        </SafeAreaView>
      </Animated.View>
    </View>
  )
}

const s = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end', zIndex: 100 },
  sheet: { backgroundColor: '#1a1a1a', borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: SCREEN_H * 0.75 },
  handle: { width: 40, height: 4, backgroundColor: '#333', borderRadius: 2, alignSelf: 'center', marginTop: 10 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingVertical: 14 },
  title: { fontSize: 17, fontWeight: '700', color: '#f5f5f5' },
  closeText: { fontSize: 15, color: '#ff6b35', fontWeight: '600' },
  scroll: { paddingHorizontal: 20 },
  sectionLabel: { fontSize: 10, fontWeight: '700', color: '#555', letterSpacing: 1, marginTop: 14, marginBottom: 8 },
  inviteRow: { flexDirection: 'row', gap: 8 },
  inviteBtn: { flex: 1, backgroundColor: '#2a1a0a', borderWidth: 1.5, borderColor: '#ff6b35', borderRadius: 10, paddingVertical: 11, alignItems: 'center' },
  inviteBtnEditor: { backgroundColor: '#1a1a2a', borderColor: '#aac' },
  inviteBtnDisabled: { opacity: 0.5 },
  inviteBtnText: { color: '#f5f5f5', fontWeight: '600', fontSize: 13 },
  linkBox: { backgroundColor: '#111', borderRadius: 10, padding: 12, marginTop: 8, gap: 8 },
  linkText: { color: '#888', fontSize: 11, fontFamily: 'Courier' },
  linkActions: { flexDirection: 'row', gap: 8 },
  linkBtn: { backgroundColor: '#1a1a1a', borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8 },
  linkBtnShare: { backgroundColor: '#ff6b35' },
  linkBtnText: { color: '#f5f5f5', fontSize: 12, fontWeight: '600' },
  collabRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 0.5, borderBottomColor: '#111', gap: 10 },
  pendingRow: { opacity: 0.6 },
  collabInfo: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 },
  collabEmail: { fontSize: 13, color: '#ddd', flex: 1 },
  roleBadge: { backgroundColor: '#2a2a2a', borderRadius: 6, paddingHorizontal: 7, paddingVertical: 3 },
  roleBadgeEditor: { backgroundColor: '#1a1a2a' },
  roleText: { fontSize: 10, color: '#888', fontWeight: '600' },
  collabActions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  roleToggle: { backgroundColor: '#2a2a2a', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 },
  roleToggleText: { color: '#888', fontSize: 11 },
  removeText: { color: '#666', fontSize: 16, paddingHorizontal: 4 },
  pendingText: { flex: 1, fontSize: 12, color: '#666' },
  emptyText: { color: '#555', fontSize: 13, textAlign: 'center', paddingVertical: 20 },
})
