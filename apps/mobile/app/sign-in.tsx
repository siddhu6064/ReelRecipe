import { useSignIn } from '@clerk/clerk-expo'
import { useRouter } from 'expo-router'
import { useState } from 'react'
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'

export default function SignInScreen() {
  const { signIn, setActive, isLoaded } = useSignIn()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSignIn() {
    if (!isLoaded || !email || !password) return
    setLoading(true)
    setError(null)
    try {
      const result = await signIn.create({ identifier: email, password })
      if (result.status === 'complete') {
        await setActive({ session: result.createdSessionId })
        router.replace('/')
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.inner}>
        <Text style={styles.logo}>🍳</Text>
        <Text style={styles.title}>ReelRecipes</Text>
        <Text style={styles.sub}>Sign in to access your cookbook and pantry.</Text>

        <TextInput
          style={styles.input}
          placeholder="Email"
          placeholderTextColor="#555"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          autoComplete="email"
        />
        <TextInput
          style={styles.input}
          placeholder="Password"
          placeholderTextColor="#555"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          returnKeyType="go"
          onSubmitEditing={handleSignIn}
        />

        {error && <Text style={styles.error}>{error}</Text>}

        <Pressable
          style={[styles.btn, (loading || !email || !password) && styles.btnDisabled]}
          onPress={handleSignIn}
          disabled={loading || !email || !password}
        >
          {loading
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.btnText}>Sign In</Text>}
        </Pressable>

        <Text style={styles.footNote}>
          Use the same account as reelrecipes.app
        </Text>
      </View>
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f' },
  inner: { flex: 1, justifyContent: 'center', padding: 28, gap: 12 },
  logo: { fontSize: 52, textAlign: 'center' },
  title: { fontSize: 28, fontWeight: '800', color: '#f5f5f5', textAlign: 'center' },
  sub: { fontSize: 14, color: '#888', textAlign: 'center', marginBottom: 8 },
  input: {
    backgroundColor: '#1a1a1a', borderWidth: 1.5, borderColor: '#2a2a2a',
    borderRadius: 12, padding: 14, fontSize: 15, color: '#f5f5f5',
  },
  error: { color: '#ff5555', fontSize: 13, textAlign: 'center' },
  btn: {
    backgroundColor: '#ff6b35', borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', marginTop: 4,
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  footNote: { color: '#444', fontSize: 12, textAlign: 'center', marginTop: 8 },
})
