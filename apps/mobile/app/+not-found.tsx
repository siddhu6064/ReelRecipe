import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

export default function NotFoundScreen() {
  const router = useRouter()
  return (
    <View style={s.container}>
      <Text style={s.icon}>🍳</Text>
      <Text style={s.title}>Page not found</Text>
      <Text style={s.sub}>This screen doesn't exist.</Text>
      <Pressable style={s.btn} onPress={() => router.replace('/')}>
        <Text style={s.btnText}>Go home</Text>
      </Pressable>
    </View>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f0f', justifyContent: 'center', alignItems: 'center', gap: 12 },
  icon: { fontSize: 48 },
  title: { fontSize: 22, fontWeight: '700', color: '#f5f5f5' },
  sub: { fontSize: 14, color: '#888' },
  btn: { marginTop: 8, backgroundColor: '#ff6b35', borderRadius: 12, paddingHorizontal: 24, paddingVertical: 12 },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
})
