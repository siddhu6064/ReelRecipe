<div align="center">

# 🍳 ReelRecipes

**Paste any cooking video URL. Get a full structured recipe in under 60 seconds.**

AI-powered extraction · Smart pantry matching · Cook Mode with voice readout · Community feed · 5 languages

[![CI](https://github.com/siddhu6064/ReelRecipe/actions/workflows/ci.yml/badge.svg)](https://github.com/siddhu6064/ReelRecipe/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-365%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-89%25-green)
![Python](https://img.shields.io/badge/python-3.12-blue)
![TypeScript](https://img.shields.io/badge/typescript-5.5-blue)
![Expo](https://img.shields.io/badge/expo-51-black)
![i18n](https://img.shields.io/badge/i18n-EN%20ES%20JA%20KO%20PT-orange)

</div>

---

## What it does

**Import from video** → paste a YouTube, TikTok, Instagram, Facebook, or X cooking video URL → GPT-4o reads the transcript → structured recipe (ingredients + quantities + steps + timers + nutrition) saved in under 60 seconds.

**Pantry-powered cooking** → add what you have at home → every saved recipe is scored by % ingredient match → see what you can cook right now, or let AI generate entirely new recipes from your pantry.

**Cook Mode (mobile)** → full-screen step-by-step interface → voice reads each step aloud → built-in countdown timers fire background notifications → screen stays on.

---

## Features

| | Feature | Detail |
|---|---|---|
| 🎬 | **Video import** | YouTube · TikTok · Instagram · Facebook · X — paste or share |
| 🤖 | **GPT-4o extraction** | Ingredients + quantities + units + steps + timers in < 60 s |
| 🏷️ | **Auto-tagging** | vegan · vegetarian · gluten-free · dairy-free · quick · detected from ingredients |
| 🧄 | **Smart pantry** | Track what you own — fuzzy matching + barcode scanner + expiry dates |
| 📊 | **Pantry match** | Every recipe scored by % — what can I cook right now? |
| ✨ | **AI suggestions** | Generate 3–5 full recipes from your pantry + dietary prefs |
| 💬 | **Recipe chat** | Ask AI about substitutions, techniques, scaling — in recipe context |
| 🔄 | **Substitutions** | Missing an ingredient? Get alternatives with effect notes |
| 🥗 | **Nutrition** | Per-serving macros via Nutritionix — calories, protein, carbs, fat |
| 📅 | **Meal planner** | Plan the week + pantry-aware shopping list |
| 👨‍🍳 | **Cook Mode** | Full-screen · step timers · **voice readout** · background notifications |
| ↩ | **Undo history** | 10-level undo stack · Cmd+Z on web · bottom sheet on mobile |
| ↕ | **Reorder** | Drag-to-reorder steps and ingredients |
| 🌍 | **Explore** | Community recipe feed · trending · save to cookbook |
| 📁 | **Collections** | Organise recipes into named folders with emoji |
| 👥 | **Collaboration** | Invite collaborators with viewer/editor roles |
| 📄 | **PDF export** | Printable A4 recipe card download |
| 📊 | **Cooking stats** | Wrapped-style stats card — streaks, cuisines, favourite ingredients |
| 💰 | **Cost estimate** | Set prices on pantry items → see recipe cost |
| 🏷️ | **Expiry dates** | Track best-before on pantry items · `GET /api/pantry/expiring` |
| 📤 | **Share Extension** | iOS Share Sheet + Android intent — share from any app |
| 🔔 | **Push notifications** | "Your recipe is ready 🍳" when extraction completes |
| 📴 | **Offline** | Web: IndexedDB cache · Mobile: AsyncStorage 24 h cache |
| 🌐 | **i18n** | 5 languages — English · Español · 日本語 · 한국어 · Português |

---

## Tech stack

| Layer | Technology |
|---|---|
| **API** | FastAPI · Python 3.12 · MongoDB Atlas (Beanie ODM) · ARQ/Redis |
| **AI** | GPT-4o (extraction, suggestions, chat, substitutions) · Whisper (fallback transcription) |
| **Nutrition** | Nutritionix Natural Language API |
| **Video** | YouTube Data API v3 · yt-dlp (TikTok / IG / FB / X) |
| **PDF** | fpdf2 — pure Python, no system dependencies |
| **Barcode** | Open Food Facts API — free, no key required |
| **Web** | React 18 · Vite · TypeScript strict · TanStack Query · Zustand · Clerk |
| **Mobile** | Expo 51 · React Native 0.74 · Expo Router · EAS Build |
| **Auth** | Clerk (JWT on all protected routes) |
| **Deploy** | Railway (API + Worker + Redis) · Vercel (Web) · EAS (iOS/Android) |
| **Observability** | Sentry · PostHog |

---

## Monorepo structure

```
reelrecipes/                          220 files · 365 tests · 89% coverage
│
├── apps/
│   ├── api/                          FastAPI backend (Python 3.12)
│   │   └── app/
│   │       ├── adapters/             YouTube · TikTok · Instagram · Facebook · X
│   │       ├── auth/                 Clerk JWT verification
│   │       ├── config/               Settings · DB · Sentry · PostHog · logging
│   │       ├── middleware/           Error handler · rate limit · request logging
│   │       ├── models/               RecipeDocument · PantryDocument · JobDocument
│   │       │                         MealPlanDocument · RecipeCollection
│   │       ├── routers/              13 REST routers (see API reference below)
│   │       ├── services/             14 business-logic services
│   │       └── workers/              ARQ background job — extract_recipe_job()
│   │
│   ├── web/                          React 18 + Vite SPA
│   │   └── src/
│   │       ├── components/           8 standalone reusable components
│   │       │   ├── AIChatPanel       Self-contained recipe Q&A with suggestion chips
│   │       │   ├── IngredientList    Scale · reorder · substitute trigger
│   │       │   ├── NavBar            Responsive navigation
│   │       │   ├── NutritionPanel    Macro breakdown (scale-aware)
│   │       │   ├── OfflineBanner     Detects offline/reconnected events
│   │       │   ├── ShoppingListPanel Queries meal plan shopping list internally
│   │       │   ├── SubstitutionModal Lazy-loads AI substitutions per ingredient
│   │       │   └── UndoButton        Cmd+Z + history dropdown
│   │       ├── pages/                11 pages (Import · Processing · Cookbook ·
│   │       │                         Recipe · Pantry · Discover · Explore ·
│   │       │                         Collections · MealPlanner · Profile · Stats)
│   │       ├── hooks/                useAuth · useJobWebSocket · useOfflineCache
│   │       └── i18n/                 5 language JSON files
│   │
│   └── mobile/                       Expo 51 · React Native 0.74
│       ├── app/
│       │   ├── (tabs)/               9 tabs — Import · Cookbook · Pantry · Discover ·
│       │   │                         Explore · Collections · Planner · Stats · Profile
│       │   ├── cook/[recipeId]        Cook Mode — voice · timers · screen-on
│       │   ├── recipe/[recipeId]      Full recipe detail (full parity with web)
│       │   └── processing/[jobId]     Job progress screen
│       ├── components/
│       │   ├── BarcodeScanner        expo-camera · Open Food Facts lookup
│       │   ├── CollabSheet           Invite links · role management
│       │   ├── PantryScreen          Add · edit · price · expiry · barcode
│       │   ├── StepTimer             Countdown · background notification
│       │   └── UndoSheet             Bottom sheet undo history
│       ├── hooks/                    useOfflineCache · usePushNotifications · useShareIntent
│       └── i18n/                     5 language JSON files
│
└── packages/
    └── shared/                       TypeScript types + i18n translations (5 languages)
        ├── src/types/                job.ts · recipe.ts · user.ts
        └── src/i18n/                 en · es · ja · ko · pt
```

---

## Data models

### RecipeDocument
```
id              ObjectId         Primary key
user_id         str              Clerk user ID (indexed)
title           str              Extracted or user-edited
source_url      str              Original video URL
platform        Enum             youtube|tiktok|instagram|facebook|x
ingredients     RecipeIngredient[]  {id, name, quantity, unit, preparation, optional}
steps           RecipeStep[]     {id, order, text, timer_seconds}
servings        int              Base serving count
cuisine         str              Indexed
difficulty      Enum             easy|medium|hard
tags            str[]            Auto-detected + GPT tags (indexed)
nutrition       NutritionInfo    {calories, protein_g, carbs_g, fat_g, ...}
is_favourite    bool             Starred by user
personal_notes  str?             Free-text cooking diary
is_edited       bool             True after any user edit
edit_snapshots  EditSnapshot[]   10-level undo stack
original_*      *                Snapshot of raw AI extraction (immutable)
is_public       bool             Visible in community explore feed
view_count      int              Incremented on public views
share_count     int              Incremented on duplicates
collaborators   CollaboratorEntry[]  Viewer/editor access
cook_log        datetime[]       Timestamps of Cook Mode completions
```

### PantryDocument
```
user_id   str          Unique — one document per user
items     PantryItem[] {id, name, quantity, unit, category,
                        estimated_cost_per_unit, expiry_date}
```

### JobDocument
```
user_id    str       Owner
url        str       Video URL submitted
platform   Enum      Detected platform
status     Enum      queued|processing|done|failed
progress   int       0–100 (broadcast via WebSocket)
result_id  ObjectId? RecipeDocument on completion
error      str?      Human-readable failure message
```

---

## API reference

```
# Video import
POST /api/jobs/import              Submit video URL → job_id
GET  /api/jobs/:id                 Poll job status / progress
WS   /ws/jobs/:id                  Real-time progress WebSocket

# Cookbook — CRUD + P1-P4 features
GET    /api/recipes                List (search · filter · auto-apply dietary prefs)
GET    /api/recipes/:id            Single recipe
PUT    /api/recipes/:id            Edit (auto-rescales quantities on servings change)
DELETE /api/recipes/:id            Remove
GET    /api/recipes/:id/original   Original AI extraction snapshot
POST   /api/recipes/:id/reset      Restore to original
POST   /api/recipes/:id/undo       Undo last edit
GET    /api/recipes/:id/history    Edit history list
POST   /api/recipes/:id/favourite  Star
DELETE /api/recipes/:id/favourite  Un-star
PUT    /api/recipes/:id/notes      Personal cooking notes
PUT    /api/recipes/:id/steps/reorder        Reorder steps
PUT    /api/recipes/:id/ingredients/reorder  Reorder ingredients
GET    /api/recipes/:id/export/pdf  Download printable A4 PDF
GET    /api/recipes/:id/cost        Estimate ingredient cost from pantry prices
POST   /api/recipes/:id/cook-session  Log Cook Mode completion

# Community
GET    /api/recipes/explore            Public feed (paginated)
GET    /api/recipes/explore/trending   Sorted by view count
PATCH  /api/recipes/:id/visibility     Toggle public/private
POST   /api/recipes/:id/duplicate      Copy to own cookbook
POST   /api/recipes/:id/invite         Generate collaborator invite link
GET    /api/recipes/:id/collaborators  List collaborators
PATCH  /api/recipes/:id/collaborators/:uid  Change role (viewer/editor)
DELETE /api/recipes/:id/collaborators/:uid  Remove collaborator
GET    /api/recipes/:id/can-edit       Permission check
POST   /api/invites/accept/:token      Accept invite

# Pantry
GET    /api/pantry                     User's pantry
POST   /api/pantry/items               Add ingredient (with optional expiry_date)
PUT    /api/pantry/items/:id           Update item
DELETE /api/pantry/items/:id           Remove item
PUT    /api/pantry/items/:id/price     Set price per unit (for cost estimation)
PUT    /api/pantry/items/:id/expiry    Set or clear expiry date
GET    /api/pantry/match               Recipes ranked by % match
GET    /api/pantry/expiring?days=N     Items expiring within N days
GET    /api/pantry/barcode/:code       Resolve EAN/UPC via Open Food Facts

# AI
POST /api/ai/suggest        Generate recipes from pantry (24 h Redis cache)
POST /api/ai/chat/:id       Conversational recipe Q&A
POST /api/ai/substitute     Ingredient substitutions with effect notes

# Meal planner
GET/POST  /api/meal-plans              List / create weekly plan
GET       /api/meal-plans/active       Current active plan
POST/DEL  /api/meal-plans/:id/meals    Add / remove meal
GET       /api/meal-plans/:id/shopping Pantry-aware shopping list

# Collections
GET/POST    /api/collections                     List / create
PUT/DELETE  /api/collections/:id                 Update / delete
GET         /api/collections/:id/recipes         List recipes in collection
POST/DELETE /api/collections/:id/recipes/:rid    Add / remove

# Users
GET  /api/users/me               Profile
PUT  /api/users/me/prefs         Dietary · cuisine · unit system preferences
PUT  /api/users/me/push-token    Register Expo push token
GET  /api/users/me/stats         Cooking stats (Wrapped card)
POST /api/clerk/webhooks         User sync (user.created / user.updated)

GET /health    Health check
```

---

## Local development

### Prerequisites

- Node.js ≥ 20 · pnpm ≥ 9 · Python 3.12 · Poetry · MongoDB · Redis

### Clone and install

```bash
git clone https://github.com/siddhu6064/ReelRecipe.git
cd ReelRecipe
pnpm install --no-frozen-lockfile
```

### API (FastAPI)

```bash
cd apps/api
cp .env.example .env          # fill in your keys
poetry install
poetry run uvicorn app.main:app --reload --port 8000
```

### ARQ worker (separate terminal)

```bash
cd apps/api
poetry run arq app.workers.job_worker.WorkerSettings
```

### Web (React + Vite)

```bash
cd apps/web
cp .env.example .env.local    # set VITE_API_URL and VITE_CLERK_PUBLISHABLE_KEY
pnpm dev                      # http://localhost:5173
```

### Mobile (Expo)

```bash
cd apps/mobile
pnpm start                    # scan QR with Expo Go
# or: pnpm ios / pnpm android (requires simulator)
```

---

## Testing

```bash
cd apps/api
poetry run pytest tests/ -q --cov=app
```

```
365 tests  ·  0 failures  ·  89% coverage
```

All external API calls (GPT-4o · Nutritionix · Open Food Facts · Clerk) are mocked — no real API calls in CI.

### Test files

| File | Area |
|---|---|
| `test_models.py` | Beanie document validation |
| `test_extractor.py` | GPT-4o extraction service |
| `test_unit_normaliser.py` | "2 tbsp" → `{quantity:2, unit:"tbsp"}` |
| `test_parser.py` | Fraction handling, unit synonyms |
| `test_pantry_match.py` | Fuzzy matching + % scoring |
| `test_routers.py` | Core REST endpoints |
| `test_ai_services.py` | Suggest · chat · substitute |
| `test_job_pipeline.py` | End-to-end import job |
| `test_meal_plan.py` | Planner + shopping list |
| `test_users_router.py` | Profile · prefs · webhook |
| `test_push_token.py` | Expo push registration |
| `test_websocket.py` | WebSocket progress events |
| `test_p1_features.py` | Dietary prefs · servings scaler · undo · favourites |
| `test_p2_features.py` | Undo history · reorder · barcode scanner |
| `test_p3_features.py` | Explore feed · collections · visibility |
| `test_p4_features.py` | PDF export · stats · cost · collaboration |
| `test_expiry.py` | Pantry item expiry dates |
| `test_health.py` | Health check |

---

## Environment variables

```env
# apps/api/.env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=reelrecipes
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-...
CLERK_SECRET_KEY=sk_test_...
YOUTUBE_API_KEY=AIza...
NUTRITIONIX_APP_ID=...
NUTRITIONIX_API_KEY=...
SENTRY_DSN=https://...
POSTHOG_API_KEY=phc_...

# apps/web/.env.local
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...

# apps/mobile — EAS secrets
EXPO_PUBLIC_API_URL=http://localhost:8000
EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
```

---

## Deployment

| Service | Platform | Config |
|---|---|---|
| API + ARQ worker | Railway | `apps/api/railway.toml` + `nixpacks.toml` |
| Redis | Railway | Auto-provisioned, link via `REDIS_URL` |
| Web | Vercel | `vercel.json` at root |
| iOS | EAS Build → App Store | `apps/mobile/eas.json` |
| Android | EAS Build → Google Play | `apps/mobile/eas.json` |

```bash
# API + web — auto-deploys on push to main via GitHub Actions
git push origin main

# Mobile builds
cd apps/mobile
eas build --platform all --profile production
eas submit --platform ios
eas submit --platform android
```

Full guides: [DEPLOYMENT.md](./DEPLOYMENT.md) · [MOBILE_SETUP.md](./MOBILE_SETUP.md)

---

## i18n — 5 languages

| Code | Language | Coverage |
|---|---|---|
| `en` | English | ✅ Base |
| `es` | Español | ✅ Full |
| `ja` | 日本語 | ✅ Full |
| `ko` | 한국어 | ✅ Full |
| `pt` | Português | ✅ Full |

Language auto-detected from browser/device locale. User can change in Profile → Language. Persisted in `localStorage` (web) and `AsyncStorage` (mobile). Translation files live in `packages/shared/src/i18n/` and are shared across both apps.

---

## Feature parity — web vs mobile

| Feature | Web | Mobile |
|---|---|---|
| Import / URL paste | ✅ | ✅ |
| Processing screen | ✅ | ✅ |
| Cookbook | ✅ | ✅ |
| Recipe detail (full) | ✅ | ✅ |
| Cook Mode | — *mobile-only* | ✅ |
| Voice readout (TTS) | — | ✅ |
| Pantry management | ✅ | ✅ |
| Barcode scanner | — *camera-native* | ✅ |
| Expiry dates | ✅ | ✅ |
| Set item price | ✅ | ✅ |
| Discover / pantry match | ✅ | ✅ |
| Explore community feed | ✅ | ✅ |
| Collections | ✅ | ✅ |
| Meal planner | ✅ | ✅ |
| Profile | ✅ | ✅ |
| Cooking stats | ✅ | ✅ |
| Favourite | ✅ | ✅ |
| Personal notes | ✅ | ✅ |
| Servings scaler + save | ✅ | ✅ |
| Undo history | ✅ | ✅ |
| Reorder steps/ingredients | ✅ | ✅ |
| Reset to original | ✅ | ✅ |
| AI chat | ✅ | ✅ |
| Substitutions | ✅ | ✅ |
| PDF export | ✅ | ✅ (Share) |
| Visibility toggle | ✅ | ✅ |
| Collaboration invite | ✅ | ✅ |
| Cost estimate display | ✅ | ✅ |
| Log cook session | — *Cook Mode only* | ✅ |
| Language picker | ✅ | ✅ |
| Offline cache | ✅ IndexedDB | ✅ AsyncStorage |
| Push notifications | — | ✅ |
| Share intent | — *paste field* | ✅ |

---

## CI/CD

```
Push to main
  └─ GitHub Actions
       ├─ lint-python     ruff check apps/api/app
       ├─ test-api        365 pytest tests · MongoDB + Redis services · ≥80% coverage gate
       ├─ typecheck-web   tsc --noEmit (TypeScript strict)
       ├─ build-web       vite build
       └─ ci ✅            Gate job — required for branch protection
```

CD: on `ci ✅` green → auto-deploy API to Railway → auto-deploy web to Vercel → smoke tests.

---

## Related

**[ReelRoutes](https://github.com/siddhu6064/ReelRoutes)** — sibling product (trip planning). ReelRecipes shares the core pipeline architecture, platform adapters, auth middleware, and deployment setup.

---

<div align="center">

**[reelrecipes.app](https://reelrecipes.app)** · [DEPLOYMENT.md](./DEPLOYMENT.md) · [MOBILE_SETUP.md](./MOBILE_SETUP.md)

Made by Sid

</div>
