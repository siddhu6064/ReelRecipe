/**
 * components/OfflineBanner.tsx
 *
 * Displays a sticky banner when the browser loses network connectivity.
 * Automatically dismisses when the connection returns.
 */

import { useEffect, useState } from 'react'
import styles from './OfflineBanner.module.css'

export function OfflineBanner() {
  const [offline, setOffline] = useState(!navigator.onLine)
  const [justReconnected, setJustReconnected] = useState(false)

  useEffect(() => {
    function onOffline() {
      setOffline(true)
      setJustReconnected(false)
    }
    function onOnline() {
      setOffline(false)
      setJustReconnected(true)
      setTimeout(() => setJustReconnected(false), 3000)
    }

    window.addEventListener('offline', onOffline)
    window.addEventListener('online', onOnline)
    return () => {
      window.removeEventListener('offline', onOffline)
      window.removeEventListener('online', onOnline)
    }
  }, [])

  if (!offline && !justReconnected) return null

  return (
    <div className={`${styles.banner} ${justReconnected ? styles.reconnected : styles.offline}`}>
      {justReconnected
        ? '✓ Back online'
        : '📶 You\'re offline — showing cached data'}
    </div>
  )
}
