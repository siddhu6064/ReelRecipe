import { useAuth as useClerkAuth, useUser } from '@clerk/clerk-react'

export function useAuth() {
  const { getToken, isLoaded, isSignedIn, signOut } = useClerkAuth()
  const { user } = useUser()

  async function authFetch(input: RequestInfo, init: RequestInit = {}): Promise<Response> {
    const token = await getToken()
    return fetch(input, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init.headers as Record<string, string>),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  }

  return { getToken, isLoaded, isSignedIn, signOut, user, authFetch }
}
