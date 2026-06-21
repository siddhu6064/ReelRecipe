# ReelRecipes — Mobile App Setup

**Stack:** Expo 51 · React Native 0.74 · Expo Router · EAS Build

One TypeScript codebase → native **iOS** (`.ipa`) + **Android** (`.apk` / `.aab`)

---

## What "Expo React Native" means

```
Your TypeScript code (this repo)
        ↓
   Expo / Metro
        ↓
  EAS Build (cloud)
    ↙        ↘
iOS .ipa    Android .aab
(Xcode)    (Gradle)
    ↓           ↓
App Store  Google Play
```

You **do not** need Xcode or Android Studio on your machine to build. EAS Build runs in the cloud. You only need Xcode locally to run the iOS Simulator or test the Share Extension.

---

## Prerequisites

```bash
# Node + pnpm
node --version   # ≥ 20
pnpm --version   # ≥ 9

# Expo + EAS
npm install -g expo-cli eas-cli
eas login   # expo.dev account

# Install app dependencies
cd apps/mobile
pnpm install
```

---

## Part 1 — Local Development

### Run on iOS Simulator (macOS only)
```bash
cd apps/mobile
pnpm ios
# Or: expo start → press 'i'
```

### Run on Android Emulator
```bash
cd apps/mobile
pnpm android
# Or: expo start → press 'a'
```

### Run on physical device (Expo Go)
```bash
pnpm start
# Scan QR code with Expo Go app
# ⚠️ Share Extension and push notifications require a dev build — see below
```

### Run as development build (recommended)
Development builds include all native modules (share intent, notifications, keep-awake):

```bash
# Build dev client (one-time, runs on device)
eas build --profile development --platform ios
# Install on device via TestFlight / direct QR

# Then start the dev server
pnpm start
```

---

## Part 2 — iOS Setup

### 1. Apple Developer account
Requires a paid Apple Developer account ($99/year) at developer.apple.com.

### 2. Bundle identifier
Already set in `app.json`:
```json
"bundleIdentifier": "com.reelrecipes.app"
```
Register this at **developer.apple.com → Certificates, Identifiers & Profiles → Identifiers → App IDs**.

### 3. App Groups (for Share Extension)
The iOS Share Extension needs an App Group to pass data to the main app.

In **developer.apple.com → Identifiers → App Groups**:
- Create group: `group.com.reelrecipes.app`
- Enable it on your App ID `com.reelrecipes.app`
- Enable it on your Share Extension App ID `com.reelrecipes.app.ShareExtension`

This is already declared in `app.json` entitlements — EAS handles provisioning.

### 4. Push notifications
In **developer.apple.com → Identifiers → com.reelrecipes.app**:
- Enable **Push Notifications** capability

EAS automatically creates an APNs key when you first build with `eas build`.

### 5. Build for TestFlight

```bash
cd apps/mobile

# Preview build (internal testing — no App Store review)
eas build --platform ios --profile preview
# → Installs via TestFlight URL

# Production build (App Store submission)
eas build --platform ios --profile production
```

### 6. Submit to App Store

```bash
# Fill in eas.json submit.production.ios fields first:
# appleId, ascAppId, appleTeamId

eas submit --platform ios --profile production
```

This uploads to App Store Connect. Then:
1. Go to **appstoreconnect.apple.com**
2. Select your build → **Add for Review**
3. Fill in metadata (screenshots, description)
4. Submit for review (typically 1–3 days)

### Share Extension — manual step required

After first `eas build`:
1. Open Xcode → your project
2. **Signing & Capabilities** → ReelRecipes target:
   - Add **App Groups** → `group.com.reelrecipes.app`
3. **Signing & Capabilities** → ShareExtension target:
   - Add **App Groups** → `group.com.reelrecipes.app`

The `ShareViewController.swift` is already at `ios/ShareExtension/ShareViewController.swift`.

---

## Part 3 — Android Setup

### 1. Keystore (signing key)
Your keystore signs the app. Keep it safe — you can never change it for an existing Play Store app.

```bash
# Generate keystore (one-time)
keytool -genkey -v \
  -keystore reelrecipes-release.keystore \
  -alias reelrecipes \
  -keyalg RSA -keysize 2048 -validity 10000

# Store it as an EAS secret:
eas secret:create --scope project \
  --name ANDROID_KEYSTORE \
  --type file \
  --value ./reelrecipes-release.keystore

eas secret:create --scope project \
  --name ANDROID_KEYSTORE_PASSWORD \
  --value "your_keystore_password"

eas secret:create --scope project \
  --name ANDROID_KEY_ALIAS \
  --value "reelrecipes"

eas secret:create --scope project \
  --name ANDROID_KEY_PASSWORD \
  --value "your_key_password"
```

### 2. Google Play setup
1. Create account at **play.google.com/console** ($25 one-time fee)
2. Create app → `com.reelrecipes.app`
3. Set up **Internal Testing** track
4. Create a **Service Account** for EAS Submit:
   - Google Play Console → Setup → API access → Link to Google Cloud
   - Create service account with **Release Manager** role
   - Download the JSON key → `google-play-service-account.json`
   - Add path to `eas.json` submit config

### 3. Build APK (sideload / internal testing)
```bash
eas build --platform android --profile preview
# Downloads: reelrecipes.apk
# Install directly: adb install reelrecipes.apk
```

### 4. Build AAB (Google Play submission)
```bash
eas build --platform android --profile production
# Downloads: reelrecipes.aab
```

### 5. Submit to Google Play
```bash
eas submit --platform android --profile production
# Uploads to Internal Testing track
```

Then in Google Play Console:
1. **Release** → **Testing** → **Internal testing**
2. Promote to **Closed testing** → **Open testing** → **Production**

### Intent filters (already in app.json)
The `android.intentFilters` in `app.json` handle:
- **ACTION_SEND** with `text/plain` — catches YouTube/TikTok/etc. shares
- **ACTION_SEND** with `video/*` — catches video file shares
- **ACTION_VIEW** with `https://reelrecipes.app` — universal links

---

## Part 4 — Build All Platforms

```bash
# Preview builds for both platforms simultaneously
cd apps/mobile
eas build --platform all --profile preview

# Production builds
eas build --platform all --profile production
```

EAS Build runs in the cloud — you don't need Xcode or Android Studio installed.
Builds take approximately 15–25 minutes.

---

## Part 5 — OTA Updates (no App Store review)

For JS-only changes (no native code), use Expo Updates:

```bash
# Push an update to preview channel
eas update --channel preview --message "Fix pantry bug"

# Push to production
eas update --channel production --message "Recipe extraction improvement"
```

Users receive the update silently on next app launch.

---

## Part 6 — Environment Variables

Set production secrets in EAS:

```bash
# API URL
eas secret:create --scope project --name EXPO_PUBLIC_API_URL \
  --value https://reelrecipes-api.railway.app

# Clerk publishable key (from Clerk Dashboard)
eas secret:create --scope project --name EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY \
  --value pk_live_...

# EAS Project ID (from expo.dev)
eas secret:create --scope project --name EXPO_PUBLIC_PROJECT_ID \
  --value YOUR_EAS_PROJECT_ID
```

Update `app.json` extra.eas.projectId with your EAS Project ID from expo.dev.

---

## Part 7 — ⚠️ Required rename before first build

Expo Router requires the tab group directory to use parentheses:

```bash
cd apps/mobile/app
mv tabs "(tabs)"
```

Shell parentheses caused the directory to be created as `tabs/` — rename it before running `expo start` or `eas build`.

---

## Part 8 — Troubleshooting

### "Cannot find module 'expo-router/entry'"
```bash
pnpm install
```

### Share Extension not appearing in iOS Share Sheet
- Ensure App Groups are enabled on both targets in Xcode
- Re-build with `eas build --platform ios --profile preview --clear-cache`

### Push notifications not working
- Check `EXPO_PUBLIC_PROJECT_ID` is set correctly
- Ensure Push Notifications capability is enabled in Apple Developer portal
- Test with Expo's push notification tool: https://expo.dev/notifications

### Android intent filters not working
- Ensure you're testing on a physical device (emulators behave differently)
- Check `autoVerify: true` — requires a verified domain (add `assetlinks.json`)

### `assetlinks.json` for Android App Links
Create `apps/web/public/.well-known/assetlinks.json`:
```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.reelrecipes.app",
    "sha256_cert_fingerprints": ["YOUR_CERT_FINGERPRINT"]
  }
}]
```
Get fingerprint: `eas credentials --platform android`

---

## Quick reference

| Command | What it does |
|---|---|
| `pnpm start` | Start Metro + open Expo Go |
| `pnpm ios` | Run on iOS Simulator |
| `pnpm android` | Run on Android Emulator |
| `eas build --platform ios --profile preview` | Build iOS TestFlight |
| `eas build --platform android --profile preview` | Build Android APK |
| `eas build --platform all --profile production` | Build both for stores |
| `eas submit --platform ios` | Submit to App Store |
| `eas submit --platform android` | Submit to Google Play |
| `eas update --channel production` | OTA update (JS-only) |
