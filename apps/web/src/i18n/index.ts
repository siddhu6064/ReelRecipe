/**
 * src/i18n/index.ts
 *
 * i18next configuration for the ReelRecipes web app.
 * Supported languages: en · es · ja · ko · pt
 * Language is persisted in localStorage so it survives refreshes.
 *
 * Usage in components:
 *   import { useTranslation } from 'react-i18next'
 *   const { t } = useTranslation()
 *   <h1>{t('cookbook.title')}</h1>
 */

import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import es from './locales/es.json'
import ja from './locales/ja.json'
import ko from './locales/ko.json'
import pt from './locales/pt.json'

export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English',    flag: '🇺🇸' },
  { code: 'es', label: 'Español',    flag: '🇪🇸' },
  { code: 'ja', label: '日本語',      flag: '🇯🇵' },
  { code: 'ko', label: '한국어',      flag: '🇰🇷' },
  { code: 'pt', label: 'Português',  flag: '🇧🇷' },
] as const

i18n
  .use(LanguageDetector)     // detects browser language
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      es: { translation: es },
      ja: { translation: ja },
      ko: { translation: ko },
      pt: { translation: pt },
    },
    fallbackLng: 'en',
    supportedLngs: ['en', 'es', 'ja', 'ko', 'pt'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'rr_lang',
    },
  })

export default i18n
