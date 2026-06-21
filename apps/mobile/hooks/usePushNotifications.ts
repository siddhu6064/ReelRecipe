// @ts-nocheck — expo-notifications types added at EAS build time
/**
 * hooks/usePushNotifications.ts
 *
 * Registers the device's Expo push token with the ReelRecipes API so the
 * server can send "Your recipe is ready!" notifications when a job completes.
 *
 * Call once from the root layout after the user is signed in.
 *   • Requests permission on first call
 *   • Caches the token in SecureStore — subsequent calls are no-ops
 *   • Sets up a tap handler: tapping the notification → /recipe/:id
 */

import { useEffect } from 'react'
import { Platform } from 'react-native'
import { useRouter } from 'expo-router'
import { useAuth } from '@clerk/clerk-expo'
import * as SecureStore from 'expo-secure-store'

const PUSH_TOKEN_KEY = 'rr_expo_push_token'
const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

export function usePushNotifications() {
  const { userId, getToken, isSignedIn } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isSignedIn || !userId) return
    registerForPushNotifications(userId, getToken)
    setupNotificationHandler(router)
  }, [isSignedIn, userId])
}

async function registerForPushNotifications(
  userId: string,
  getToken: () => Promise<string | null>,
) {
  try {
    // Avoid re-registering if token already cached
    const cached = await SecureStore.getItemAsync(PUSH_TOKEN_KEY)
    if (cached) return

    const Notifications = await import('expo-notifications')

    // Request permission
    const { status: existing } = await Notifications.getPermissionsAsync()
    let finalStatus = existing
    if (existing !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync()
      finalStatus = status
    }
    if (finalStatus !== 'granted') return

    // Android needs a notification channel
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('recipes', {
        name: 'Recipe notifications',
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        sound: 'default',
      })
    }

    // Get token
    const tokenData = await Notifications.getExpoPushTokenAsync({
      projectId: process.env.EXPO_PUBLIC_PROJECT_ID,
    })
    const pushToken = tokenData.data

    // Register with API
    const authToken = await getToken()
    await fetch(`${API_URL}/api/users/me/push-token`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      body: JSON.stringify({ push_token: pushToken }),
    })

    // Cache so we don't re-register on every launch
    await SecureStore.setItemAsync(PUSH_TOKEN_KEY, pushToken)
  } catch (err) {
    console.warn('Push notification registration failed:', err)
  }
}

function setupNotificationHandler(router: ReturnType<typeof useRouter>) {
  import('expo-notifications').then(Notifications => {
    // Handle notification taps
    Notifications.addNotificationResponseReceivedListener(response => {
      const data = response.notification.request.content.data as Record<string, unknown>
      // When a recipe extraction job completes, navigate to the recipe
      if (data?.recipeId) {
        router.push(`/recipe/${data.recipeId}`)
      }
    })

    // Show foreground notifications as banners
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: true,
      }),
    })
  })
}
