import '../i18n'
/**
 * app/_layout.tsx — Root Layout
 *
 * Provider tree (outermost → innermost):
 *   ClerkProvider          — JWT auth
 *   ShareIntentProvider    — iOS Share Sheet + Android intents
 *   QueryClientProvider    — server-state cache
 *   AuthGuard              — redirect to /sign-in when not signed in
 *   ShareIntentHandler     — auto-submits shared URLs to /api/jobs/import
 *   PushNotificationSetup  — registers device token on sign-in
 *   Slot                   — Expo Router renders active route here
 */

import { useCallback, useEffect } from 'react'
import { ActivityIndicator, View } from 'react-native'
import { Slot, useRouter, useSegments } from 'expo-router'
import { ClerkProvider, useAuth } from '@clerk/clerk-expo'
import * as SecureStore from 'expo-secure-store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ShareIntentProvider, useShareIntentContext } from 'expo-share-intent'
import { useAppStore } from '../stores/appStore'
import { usePushNotifications } from '../hooks/usePushNotifications'

const CLERK_KEY = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY ?? ''
const API_URL   = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Clerk SecureStore token cache ──────────────────────────────────────────

const tokenCache = {
  async getToken(key: string) {
    try { return await SecureStore.getItemAsync(key) } catch { return null }
  },
  async saveToken(key: string, value: string) {
    try { await SecureStore.setItemAsync(key, value) } catch { /* ignore */ }
  },
}

// ── TanStack Query client ──────────────────────────────────────────────────

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 1000 * 60 * 5, retry: 2, gcTime: 1000 * 60 * 30 },
  },
})

// ── Auth guard — redirects unauthenticated users to /sign-in ──────────────

function AuthGuard() {
  const { isLoaded, isSignedIn } = useAuth()
  const segments = useSegments()
  const router   = useRouter()

  useEffect(() => {
    if (!isLoaded) return
    const inAuth = segments[0] === 'sign-in'
    if (!isSignedIn && !inAuth) router.replace('/sign-in')
    if (isSignedIn && inAuth)  router.replace('/(tabs)')
  }, [isLoaded, isSignedIn, segments])

  if (!isLoaded) {
    return (
      <View style={{ flex: 1, backgroundColor: '#0f0f0f', justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator color="#ff6b35" size="large" />
      </View>
    )
  }

  return <Slot />
}

// ── Share intent handler — fires when user shares a video URL into the app ─

function ShareIntentHandler() {
  const { hasShareIntent, shareIntent, resetShareIntent } = useShareIntentContext()
  const router         = useRouter()
  const { getToken }   = useAuth()
  const { isSignedIn } = useAuth()
  const setActiveJobId = useAppStore(s => s.setActiveJobId)

  useEffect(() => {
    if (!hasShareIntent || !isSignedIn) return

    const rawUrl = shareIntent?.webUrl ?? shareIntent?.text ?? ''
    const match  = rawUrl.match(/https?:\/\/[^\s"'<>]+/)
    const url    = match ? match[0].trim() : ''
    if (!url) return

    resetShareIntent()

    ;(async () => {
      try {
        const token = await getToken()
        const res = await fetch(`${API_URL}/api/jobs/import`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ url }),
        })
        const { data } = await res.json()
        setActiveJobId(data.jobId)
        router.push(`/processing/${data.jobId}`)
      } catch (err) {
        console.error('Share intent import failed:', err)
      }
    })()
  }, [hasShareIntent, isSignedIn])

  return null
}

// ── Push notification setup ────────────────────────────────────────────────

function PushSetup() {
  const { isSignedIn } = useAuth()
  usePushNotifications()   // no-op until signed in
  return null
}

// ── Root layout ────────────────────────────────────────────────────────────

export default function RootLayout() {
  return (
    <ClerkProvider publishableKey={CLERK_KEY} tokenCache={tokenCache}>
      <QueryClientProvider client={queryClient}>
        <ShareIntentProvider>
          <ShareIntentHandler />
          <PushSetup />
          <AuthGuard />
        </ShareIntentProvider>
      </QueryClientProvider>
    </ClerkProvider>
  )
}
