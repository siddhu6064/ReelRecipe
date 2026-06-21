/**
 * apps/mobile/i18n.ts
 *
 * Initialises i18next for Expo React Native.
 * Import this once from app/_layout.tsx.
 *
 * Language detection: expo-localization → AsyncStorage fallback
 * Persisted in AsyncStorage key "rr_lang"
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '../../packages/shared/src/i18n/en.json'
import es from '../../packages/shared/src/i18n/es.json'
import ja from '../../packages/shared/src/i18n/ja.json'
import ko from '../../packages/shared/src/i18n/ko.json'
import pt from '../../packages/shared/src/i18n/pt.json'

export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Español' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'pt', label: 'Português' },
] as const

export type LangCode = typeof SUPPORTED_LANGUAGES[number]['code']

// Detect device locale and map to supported language
function detectLocale(): LangCode {
  try {
    const loc = require('expo-localization')
    const lang = (loc.getLocales?.()[0]?.languageCode ?? 'en').toLowerCase()
    const match = (['en','es','ja','ko','pt'] as LangCode[]).find(c => lang.startsWith(c))
    return match ?? 'en'
  } catch {
    return 'en'
  }
}

i18n
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, es: { translation: es }, ja: { translation: ja }, ko: { translation: ko }, pt: { translation: pt } },
    lng: detectLocale(),
    fallbackLng: 'en',
    supportedLngs: ['en','es','ja','ko','pt'],
    interpolation: { escapeValue: false },
  })

export default i18n
export { i18n }
