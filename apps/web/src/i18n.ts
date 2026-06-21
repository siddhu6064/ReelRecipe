/**
 * apps/web/src/i18n.ts
 *
 * Initialises i18next for the web app.
 * Import this file once at the top of main.tsx.
 *
 * Features:
 *  - Browser language auto-detection (navigator.language)
 *  - Falls back to English when the detected language is unsupported
 *  - Language choice persisted in localStorage key "rr_lang"
 *  - All 5 languages bundled (no lazy loading — files are tiny)
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

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

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, es: { translation: es }, ja: { translation: ja }, ko: { translation: ko }, pt: { translation: pt } },
    fallbackLng: 'en',
    supportedLngs: SUPPORTED_LANGUAGES.map(l => l.code),
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'rr_lang',
    },
  })

export default i18n
export { i18n }
