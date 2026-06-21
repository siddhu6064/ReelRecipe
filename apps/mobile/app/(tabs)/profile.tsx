/**
 * app/(tabs)/profile.tsx — Profile & Settings Tab
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES } from '../../i18n'
import {
  Alert,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native'
import { useAuth, useUser } from '@clerk/clerk-expo'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Image } from 'react-native'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

const DIETARY = ['vegan','vegetarian','gluten-free','dairy-free','nut-free','halal','keto','paleo']
const CUISINES = ['Italian','Japanese','Mexican','Indian','Chinese','Thai','French','Mediterranean']

interface UserProfile {
  dietary_prefs: string[]
  cuisine_prefs: string[]
  unit_system: 'metric' | 'imperial'
}

export default function ProfileTab() {
  const { t, i18n } = useTranslation()
  const { getToken, signOut } = useAuth()
  const { user } = useUser()
  const qc = useQueryClient()
  const [saved, setSaved] = useState(false)

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/users/me`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) return null
      const { data } = await res.json()
      return data as UserProfile
    },
  })

  const [dietary, setDietary] = useState<string[]>(profile?.dietary_prefs ?? [])
  const [cuisine, setCuisine] = useState<string[]>(profile?.cuisine_prefs ?? [])
  const [units, setUnits] = useState<'metric' | 'imperial'>(profile?.unit_system ?? 'metric')
  const [synced, setSynced] = useState(false)

  if (profile && !synced) {
    setDietary(profile.dietary_prefs)
    setCuisine(profile.cuisine_prefs)
    setUnits(profile.unit_system)
    setSynced(true)
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/users/me/prefs`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ dietary_prefs: dietary, cuisine_prefs: cuisine, unit_system: units }),
      })
      if (!res.ok) throw new Error('Save failed')
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profile'] }); setSaved(true); setTimeout(() => setSaved(false), 2000) },
  })

  function toggle(arr: string[], setArr: (a: string[]) => void, val: string) {
    setArr(arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val])
    setSaved(false)
  }

  function confirmSignOut() {
    Alert.alert('Sign out', 'Are you sure you want to sign out?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign out', style: 'destructive', onPress: async () => {
        // Deregister push token before signing out so server stops sending notifications
        try {
          const token = await getToken()
          await fetch(`${API_URL}/api/users/me/push-token`, {
            method: 'DELETE',
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          })
        } catch { /* non-critical — sign out regardless */ }
        signOut()
      }},
    ])
  }

  return (
    <SafeAreaView style={s.container}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Account card */}
        <View style={s.accountCard}>
          {user?.imageUrl
            ? <Image source={{ uri: user.imageUrl }} style={s.avatar} />
            : <View style={s.avatarFallback}><Text style={s.avatarInitial}>{user?.firstName?.[0] ?? '?'}</Text></View>}
          <View style={s.accountInfo}>
            <Text style={s.accountName}>{user?.fullName ?? 'User'}</Text>
            <Text style={s.accountEmail}>{user?.primaryEmailAddress?.emailAddress}</Text>
          </View>
        </View>

        {/* Unit system */}
        <View style={s.section}>
          <Text style={s.sectionTitle}>Unit system</Text>
          <View style={s.unitRow}>
            {(['metric', 'imperial'] as const).map(u => (
              <Pressable
                key={u}
                style={[s.unitBtn, units === u && s.unitBtnActive]}
                onPress={() => { setUnits(u); setSaved(false) }}
              >
                <Text style={[s.unitText, units === u && s.unitTextActive]}>
                  {u === 'metric' ? '🌍 Metric' : '🇺🇸 Imperial'}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        {/* Dietary prefs */}
        <View style={s.section}>
          <Text style={s.sectionTitle}>Dietary preferences</Text>
          <View style={s.chipWrap}>
            {DIETARY.map(d => (
              <Pressable key={d} style={[s.chip, dietary.includes(d) && s.chipActive]}
                onPress={() => toggle(dietary, setDietary, d)}>
                <Text style={[s.chipText, dietary.includes(d) && s.chipTextActive]}>{d}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        {/* Cuisine prefs */}
        <View style={s.section}>
          <Text style={s.sectionTitle}>Favourite cuisines</Text>
          <View style={s.chipWrap}>
            {CUISINES.map(c => (
              <Pressable key={c} style={[s.chip, cuisine.includes(c) && s.chipActive]}
                onPress={() => toggle(cuisine, setCuisine, c)}>
                <Text style={[s.chipText, cuisine.includes(c) && s.chipTextActive]}>{c}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        {/* Language picker */}
        <View style={s.section}>
          <Text style={s.sectionTitle}>{t('profile.language').toUpperCase()}</Text>
          <View style={s.chipWrap}>
            {SUPPORTED_LANGUAGES.map(lang => (
              <Pressable
                key={lang.code}
                style={[s.chip, i18n.language.startsWith(lang.code) && s.chipActive]}
                onPress={async () => {
                  await i18n.changeLanguage(lang.code)
                  try {
                    const AS = await import('@react-native-async-storage/async-storage')
                    await AS.default.setItem('rr_lang', lang.code)
                  } catch {}
                }}
              >
                <Text style={[s.chipText, i18n.language.startsWith(lang.code) && s.chipTextActive]}>
                  {lang.label}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        {/* Save button */}
        <Pressable
          style={[s.saveBtn, saveMutation.isPending && s.saveBtnDisabled, saved && s.saveBtnDone]}
          onPress={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
        >
          <Text style={s.saveBtnText}>
            {saveMutation.isPending ? 'Saving…' : saved ? '✓ Saved' : 'Save preferences'}
          </Text>
        </Pressable>

        {/* Sign out */}
        <Pressable style={s.signOutBtn} onPress={confirmSignOut}>
          <Text style={s.signOutText}>Sign out</Text>
        </Pressable>

        <View style={{ height: 20 }} />
      </ScrollView>
    </SafeAreaView>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  scroll: { padding: 20, gap: 0 },
  accountCard: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: '#1a1a1a', borderRadius: 16, padding: 16, marginBottom: 24 },
  avatar: { width: 52, height: 52, borderRadius: 26 },
  avatarFallback: { width: 52, height: 52, borderRadius: 26, backgroundColor: '#ff6b35', justifyContent: 'center', alignItems: 'center' },
  avatarInitial: { color: '#fff', fontSize: 20, fontWeight: '700' },
  accountInfo: { flex: 1 },
  accountName: { fontSize: 16, fontWeight: '700', color: '#f5f5f5' },
  accountEmail: { fontSize: 13, color: '#888', marginTop: 3 },
  section: { marginBottom: 24 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#888', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 },
  unitRow: { flexDirection: 'row', gap: 8 },
  unitBtn: { flex: 1, padding: 12, borderRadius: 12, borderWidth: 1.5, borderColor: '#2a2a2a', alignItems: 'center' },
  unitBtnActive: { borderColor: '#ff6b35', backgroundColor: '#2a1a0a' },
  unitText: { fontSize: 14, color: '#666' },
  unitTextActive: { color: '#f5f5f5', fontWeight: '600' },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20, borderWidth: 1.5, borderColor: '#2a2a2a' },
  chipActive: { borderColor: '#ff6b35', backgroundColor: '#2a1a0a' },
  chipText: { fontSize: 13, color: '#666' },
  chipTextActive: { color: '#ff6b35', fontWeight: '600' },
  saveBtn: { backgroundColor: '#ff6b35', borderRadius: 14, paddingVertical: 14, alignItems: 'center', marginBottom: 12 },
  saveBtnDisabled: { opacity: 0.5 },
  saveBtnDone: { backgroundColor: '#2d6b3a' },
  saveBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  signOutBtn: { borderWidth: 1.5, borderColor: '#2a2a2a', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  signOutText: { color: '#888', fontSize: 15 },
})
