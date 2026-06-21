/**
 * hooks/useShareIntent.ts
 *
 * Unified share intent hook for iOS and Android.
 *
 * Handles three entry paths:
 *   1. iOS Share Extension  — expo-share-intent via useShareIntentContext
 *   2. Android ACTION_SEND  — expo-share-intent via useShareIntentContext
 *   3. Android ACTION_VIEW  — Linking.getInitialURL() cold-start fallback
 *      (when user taps "Open with ReelRoutes" on a link; expo-share-intent
 *      doesn't always catch this, so we check Linking as a fallback)
 *
 * Returns a normalised result regardless of how the URL arrived.
 */

import * as Linking from "expo-linking";
import { useShareIntentContext } from "expo-share-intent";
import { useEffect, useState } from "react";
import { Platform } from "react-native";

export const SUPPORTED_PLATFORMS = [
  { label: "YouTube", pattern: /youtube\.com|youtu\.be/i },
  { label: "Instagram", pattern: /instagram\.com/i },
  { label: "TikTok", pattern: /tiktok\.com|vm\.tiktok\.com/i },
  { label: "Facebook", pattern: /facebook\.com|fb\.watch/i },
  { label: "X", pattern: /twitter\.com|x\.com/i },
] as const;

export type PlatformLabel = (typeof SUPPORTED_PLATFORMS)[number]["label"];

export function detectPlatform(url: string): PlatformLabel | null {
  return SUPPORTED_PLATFORMS.find((p) => p.pattern.test(url))?.label ?? null;
}

/** Extract the first https URL from a string. */
function extractUrl(raw: string): string | null {
  const match = raw.match(/https?:\/\/[^\s"'<>]+/);
  return match ? match[0].trim() : null;
}

/** Check if a URL is a supported video platform URL. */
function isSupportedVideoUrl(url: string): boolean {
  return detectPlatform(url) !== null;
}

interface ShareIntentResult {
  /** Clean URL extracted from the share, or null if nothing shared. */
  incomingUrl: string | null;
  /** Human-readable source name, e.g. "YouTube" or "Instagram". */
  sourceName: string | null;
  /** Detected platform for the URL. */
  platform: PlatformLabel | null;
  /** Whether a share intent is waiting to be handled. */
  hasIntent: boolean;
  /** Call this after import starts to dismiss the intent. */
  clearIntent: () => void;
}

export function useShareIntent(): ShareIntentResult {
  const { hasShareIntent, shareIntent, resetShareIntent } = useShareIntentContext();

  // Android ACTION_VIEW fallback — cold-start with a video URL
  const [linkingUrl, setLinkingUrl] = useState<string | null>(null);
  const [linkingCleared, setLinkingCleared] = useState(false);

  useEffect(() => {
    if (Platform.OS !== "android" || linkingCleared) return;

    // Check if the app was opened via a direct URL (ACTION_VIEW)
    void Linking.getInitialURL().then((url) => {
      if (url && isSupportedVideoUrl(url)) {
        setLinkingUrl(url);
      }
    });

    // Also listen for URLs while the app is already running (singleTask mode
    // sends new intents to the foreground instance via onNewIntent)
    const sub = Linking.addEventListener("url", ({ url }) => {
      if (isSupportedVideoUrl(url)) {
        setLinkingUrl(url);
        setLinkingCleared(false);
      }
    });

    return () => sub.remove();
  }, [linkingCleared]);

  // ── expo-share-intent result (iOS + Android ACTION_SEND) ──────────
  if (hasShareIntent && shareIntent) {
    const raw = shareIntent.webUrl ?? shareIntent.text ?? "";
    const incomingUrl = extractUrl(raw);
    const platform = incomingUrl ? detectPlatform(incomingUrl) : null;
    const sourceName =
      (shareIntent.meta as { title?: string } | undefined)?.title ?? platform ?? "another app";

    return {
      incomingUrl,
      sourceName,
      platform,
      hasIntent: true,
      clearIntent: () => {
        resetShareIntent();
        setLinkingUrl(null);
        setLinkingCleared(true);
      },
    };
  }

  // ── Android ACTION_VIEW fallback (Linking) ────────────────────────
  if (Platform.OS === "android" && linkingUrl && !linkingCleared) {
    const platform = detectPlatform(linkingUrl);
    return {
      incomingUrl: linkingUrl,
      sourceName: platform ?? "link",
      platform,
      hasIntent: true,
      clearIntent: () => {
        setLinkingUrl(null);
        setLinkingCleared(true);
      },
    };
  }

  // ── No intent ─────────────────────────────────────────────────────
  return {
    incomingUrl: null,
    sourceName: null,
    platform: null,
    hasIntent: false,
    clearIntent: () => {
      resetShareIntent();
      setLinkingUrl(null);
      setLinkingCleared(true);
    },
  };
}
