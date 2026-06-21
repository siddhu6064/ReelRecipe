/**
 * components/BarcodeScanner.tsx
 *
 * Full-screen barcode scanner using expo-camera.
 * On a successful scan, calls the ReelRecipes API to resolve the barcode
 * via Open Food Facts, then passes the result back to the parent.
 *
 * Usage:
 *   <BarcodeScanner
 *     onResult={(name, category) => addIngredient(name, category)}
 *     onClose={() => setShowScanner(false)}
 *   />
 */

import { useEffect, useRef, useState } from 'react'
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native'
import { useAuth } from '@clerk/clerk-expo'

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

interface Props {
  onResult: (name: string, category: string, brand?: string) => void
  onClose: () => void
}

interface BarcodeResult {
  name: string
  category: string
  brand?: string
}

// Lazy-load expo-camera to avoid import errors in environments
// where it's not yet installed (dev without native build)
let CameraView: React.ComponentType<{
  style?: object
  facing?: string
  onBarcodeScanned?: (data: { type: string; data: string }) => void
}> | null = null

try {
  const cam = require('expo-camera')
  CameraView = cam.CameraView
} catch { /* not installed yet — show fallback UI */ }

export function BarcodeScanner({ onResult, onClose }: Props) {
  const { getToken } = useAuth()
  const [permission, setPermission] = useState<'granted' | 'denied' | 'pending'>('pending')
  const [scanning, setScanning] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lastScannedRef = useRef<string | null>(null)

  useEffect(() => {
    requestPermission()
  }, [])

  async function requestPermission() {
    try {
      const cam = require('expo-camera')
      const { status } = await cam.Camera.requestCameraPermissionsAsync()
      setPermission(status === 'granted' ? 'granted' : 'denied')
    } catch {
      setPermission('denied')
    }
  }

  async function handleBarcodeScan({ data: barcode }: { type: string; data: string }) {
    // Debounce — same barcode within 2s is ignored
    if (!scanning || loading || barcode === lastScannedRef.current) return
    lastScannedRef.current = barcode
    setScanning(false)
    setLoading(true)
    setError(null)

    try {
      const token = await getToken()
      const res = await fetch(`${API_URL}/api/pantry/barcode/${barcode}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      if (res.ok) {
        const { data } = await res.json()
        onResult(data.name, data.category, data.brand)
        return
      } else if (res.status === 404) {
        setError(`Barcode ${barcode} not found. Try adding manually.`)
      } else {
        setError('Lookup failed. Try again.')
      }
    } catch {
      setError('Could not reach server. Check connection.')
    } finally {
      setLoading(false)
      // Allow rescanning after 2s if not found
      setTimeout(() => {
        lastScannedRef.current = null
        setScanning(true)
      }, 2000)
    }
  }

  // expo-camera not installed — show manual entry fallback
  if (!CameraView) {
    return (
      <View style={s.container}>
        <View style={s.notInstalled}>
          <Text style={s.notInstalledTitle}>📷 Barcode Scanner</Text>
          <Text style={s.notInstalledText}>
            Barcode scanning requires a native build.{'\n'}
            Run: <Text style={s.code}>eas build --profile development</Text>
          </Text>
          <Pressable style={s.closeBtn} onPress={onClose}>
            <Text style={s.closeBtnText}>Close</Text>
          </Pressable>
        </View>
      </View>
    )
  }

  if (permission === 'denied') {
    return (
      <View style={s.container}>
        <View style={s.notInstalled}>
          <Text style={s.notInstalledTitle}>Camera access denied</Text>
          <Text style={s.notInstalledText}>
            Allow camera access in device Settings to use the barcode scanner.
          </Text>
          <Pressable style={s.closeBtn} onPress={onClose}>
            <Text style={s.closeBtnText}>Close</Text>
          </Pressable>
        </View>
      </View>
    )
  }

  if (permission === 'pending') {
    return (
      <View style={s.container}>
        <ActivityIndicator color="#ff6b35" size="large" />
      </View>
    )
  }

  return (
    <View style={s.container}>
      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        onBarcodeScanned={scanning && !loading ? handleBarcodeScan : undefined}
      />

      {/* Viewfinder overlay */}
      <View style={s.overlay}>
        <View style={s.topBar}>
          <Pressable style={s.xBtn} onPress={onClose}>
            <Text style={s.xBtnText}>✕ Cancel</Text>
          </Pressable>
        </View>

        <View style={s.viewfinder}>
          <View style={s.corner} />
          <View style={[s.corner, s.cornerTR]} />
          <View style={[s.corner, s.cornerBL]} />
          <View style={[s.corner, s.cornerBR]} />
        </View>

        <View style={s.bottomBar}>
          {loading && (
            <View style={s.statusBox}>
              <ActivityIndicator color="#fff" size="small" />
              <Text style={s.statusText}> Looking up barcode…</Text>
            </View>
          )}
          {error && !loading && (
            <View style={s.errorBox}>
              <Text style={s.errorText}>{error}</Text>
              <Pressable onPress={() => { setError(null); setScanning(true) }}>
                <Text style={s.retryText}>Try again</Text>
              </Pressable>
            </View>
          )}
          {!loading && !error && (
            <Text style={s.hint}>Point camera at a product barcode</Text>
          )}
        </View>
      </View>
    </View>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' },
  overlay: { ...StyleSheet.absoluteFillObject, justifyContent: 'space-between' },
  topBar: { paddingTop: 56, paddingHorizontal: 20 },
  xBtn: { alignSelf: 'flex-start', backgroundColor: 'rgba(0,0,0,0.5)', borderRadius: 20, paddingHorizontal: 16, paddingVertical: 8 },
  xBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  viewfinder: { alignSelf: 'center', width: 250, height: 250, position: 'relative' },
  corner: { position: 'absolute', width: 30, height: 30, borderColor: '#ff6b35', borderTopWidth: 3, borderLeftWidth: 3, top: 0, left: 0 },
  cornerTR: { top: 0, left: undefined, right: 0, borderLeftWidth: 0, borderRightWidth: 3 },
  cornerBL: { top: undefined, bottom: 0, left: 0, borderTopWidth: 0, borderBottomWidth: 3 },
  cornerBR: { top: undefined, bottom: 0, left: undefined, right: 0, borderTopWidth: 0, borderLeftWidth: 0, borderBottomWidth: 3, borderRightWidth: 3 },
  bottomBar: { paddingBottom: 60, paddingHorizontal: 20, alignItems: 'center', gap: 12 },
  hint: { color: 'rgba(255,255,255,0.7)', fontSize: 14, textAlign: 'center' },
  statusBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: 10, paddingHorizontal: 16, paddingVertical: 10 },
  statusText: { color: '#fff', fontSize: 14 },
  errorBox: { backgroundColor: 'rgba(60,0,0,0.8)', borderRadius: 12, padding: 14, alignItems: 'center', gap: 8 },
  errorText: { color: '#ff9999', fontSize: 13, textAlign: 'center' },
  retryText: { color: '#ff6b35', fontWeight: '600', fontSize: 14 },
  notInstalled: { padding: 32, alignItems: 'center', gap: 12 },
  notInstalledTitle: { fontSize: 20, fontWeight: '700', color: '#f5f5f5' },
  notInstalledText: { fontSize: 14, color: '#888', textAlign: 'center', lineHeight: 22 },
  code: { fontFamily: 'Courier', color: '#ff6b35' },
  closeBtn: { marginTop: 8, backgroundColor: '#1a1a1a', borderRadius: 12, paddingHorizontal: 24, paddingVertical: 12 },
  closeBtnText: { color: '#f5f5f5', fontWeight: '600' },
})
