# ReelRecipes — Deployment Guide

Complete step-by-step instructions for deploying ReelRecipes to production.

**Stack:** Railway (API + Worker + Redis) · MongoDB Atlas · Vercel (Web) · EAS (Mobile)

---

## Prerequisites

- Railway account + CLI: `npm install -g @railway/cli && railway login`
- Vercel account + CLI: `npm install -g vercel && vercel login`
- MongoDB Atlas account
- Clerk account (production instance)
- OpenAI API key
- YouTube Data API v3 key
- Nutritionix account
- EAS CLI: `npm install -g eas-cli && eas login`

---

## 1 — MongoDB Atlas

1. Create a new **M0 free cluster** (or M10 for production)
2. **Database Access** → Add database user with `readWrite` on `reelrecipes_production`
3. **Network Access** → Add `0.0.0.0/0` (Railway IPs are dynamic) — or use Atlas Private Endpoint
4. **Connect** → Drivers → copy the `mongodb+srv://...` connection string
5. Replace `<password>` with your database user password
6. Set `MONGODB_DB=reelrecipes_production`

**Indexes are auto-created** by Beanie on first startup — no manual setup needed.

---

## 2 — Clerk

### Create a production instance
1. Clerk Dashboard → **Add application** → name it `ReelRecipes`
2. Enable **Email + Password** sign-in (and optionally Google OAuth)
3. **API Keys** → copy `Publishable key` and `Secret key`

### Configure allowed origins
Go to **JWT Templates** → **Blank template**:
- Name: `reelrecipes`
- Set `Lifetime` to `3600` seconds

Go to **Domains** → add:
- `https://reelrecipes.app`
- `https://www.reelrecipes.app`
- `https://reelrecipes-api.railway.app` (for health checks)

### Webhooks
1. **Webhooks** → **Add endpoint**
2. URL: `https://reelrecipes-api.railway.app/api/clerk/webhooks`
3. Subscribe to: `user.created`, `user.updated`
4. Copy the **Signing Secret** → `CLERK_WEBHOOK_SECRET`

---

## 3 — Railway

### Create project
```bash
railway login
railway init   # name it "reelrecipes"
```

### Add services

**API service:**
```bash
railway add --service reelrecipes-api
railway service reelrecipes-api
railway domain   # generates https://reelrecipes-api.railway.app
```

**Worker service** (ARQ background jobs):
```bash
railway add --service reelrecipes-worker
```

**Redis:**
```bash
railway add --service Redis
# Railway auto-provisions Redis and sets $REDIS_URL
```

### Set environment variables

In Railway Dashboard → Service Variables for **reelrecipes-api** and **reelrecipes-worker**:

```bash
# Use Railway CLI bulk import:
railway variables set \
  ENV=production \
  MONGODB_URL="mongodb+srv://..." \
  MONGODB_DB=reelrecipes_production \
  CLERK_SECRET_KEY=sk_live_... \
  CLERK_WEBHOOK_SECRET=whsec_... \
  OPENAI_API_KEY=sk-... \
  YOUTUBE_API_KEY=AIza... \
  NUTRITIONIX_APP_ID=xxx \
  NUTRITIONIX_API_KEY=xxx \
  SENTRY_DSN=https://... \
  POSTHOG_API_KEY=phc_... \
  CORS_ORIGINS="https://reelrecipes.app,https://www.reelrecipes.app"
```

Railway auto-injects `REDIS_URL` from the Redis service — no need to set it manually.

### Worker start command

In **reelrecipes-worker** service settings → Start Command:
```
cd apps/api && poetry run arq app.workers.job_worker.WorkerSettings
```

### Deploy
```bash
git push origin main   # Triggers CD pipeline via GitHub Actions
# OR manually:
railway up --service reelrecipes-api
railway up --service reelrecipes-worker
```

### Verify
```bash
curl https://reelrecipes-api.railway.app/health
# → {"ok": true, "status": "healthy", ...}
```

---

## 4 — Vercel (Web)

```bash
cd apps/web
vercel --prod
```

Set environment variables in Vercel Dashboard → Project Settings → Environment Variables:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://reelrecipes-api.railway.app` |
| `VITE_CLERK_PUBLISHABLE_KEY` | `pk_live_...` |

**Custom domain** (optional):
```bash
vercel domains add reelrecipes.app
vercel domains add www.reelrecipes.app
```

---

## 5 — GitHub Actions secrets

In your GitHub repo → Settings → Secrets and Variables → Actions:

| Secret | Value |
|---|---|
| `RAILWAY_TOKEN` | From Railway Dashboard → Account → Tokens |
| `VERCEL_TOKEN` | From Vercel Dashboard → Account → Tokens |
| `VERCEL_ORG_ID` | From Vercel project settings |
| `VERCEL_PROJECT_ID` | From Vercel project settings |
| `VITE_CLERK_PUBLISHABLE_KEY` | `pk_live_...` |
| `SMOKE_TEST_TOKEN` | A valid Clerk JWT for a test user |

| Variable | Value |
|---|---|
| `API_URL` | `https://reelrecipes-api.railway.app` |

---

## 6 — EAS Build (Mobile)

```bash
cd apps/mobile
eas build:configure   # creates/updates eas.json

# Update eas.json with your EAS project ID:
eas init
```

Set secrets in **Expo Dashboard → Project → Secrets**:

```bash
eas secret:create --scope project --name EXPO_PUBLIC_API_URL \
  --value https://reelrecipes-api.railway.app

eas secret:create --scope project --name EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY \
  --value pk_live_...
```

**Build for TestFlight (iOS):**
```bash
eas build --platform ios --profile preview
```

**Build for Google Play internal testing:**
```bash
eas build --platform android --profile preview
```

**Submit to stores:**
```bash
eas submit --platform ios     # → App Store Connect
eas submit --platform android # → Google Play
```

---

## 7 — Sentry

1. **sentry.io** → New Project → Select **FastAPI**
2. Copy the DSN → set `SENTRY_DSN` on Railway
3. Set `SENTRY_ENVIRONMENT=production`
4. For the web app, add to `apps/web/src/main.tsx`:

```typescript
import * as Sentry from '@sentry/react'
Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: 'production',
  tracesSampleRate: 0.1,
})
```

---

## 8 — PostHog

1. **app.posthog.com** → New project → `ReelRecipes`
2. Copy the `phc_...` API key → set `POSTHOG_API_KEY` on Railway
3. For the web app, add PostHog snippet to `index.html`:

```html
<script>
  !function(t,e){/* PostHog snippet */}(window, document);
  posthog.init('phc_YOUR_KEY', { api_host: 'https://app.posthog.com' })
</script>
```

---

## 9 — Post-deployment checklist

Run the smoke test suite:
```bash
API_URL=https://reelrecipes-api.railway.app \
SMOKE_TEST_TOKEN=<clerk_jwt> \
pytest scripts/smoke_test.py -v
```

Manual checks:
- [ ] `GET /health` → `200 ok`
- [ ] `GET /version` → returns version string
- [ ] `GET /api/recipes` without token → `401`
- [ ] `GET /api/recipes` with valid token → `200`
- [ ] Import a YouTube cooking video → job created → processing → recipe saved
- [ ] Pantry: add an ingredient, check `/api/pantry/match`
- [ ] AI suggest: returns recipe suggestions
- [ ] Web app loads at `https://reelrecipes.app`
- [ ] Share Extension on iOS: share a YouTube link → app opens → job starts

---

## Rollback

Railway keeps the last 3 successful deployments:
```bash
railway rollback --service reelrecipes-api
```

Vercel rollback:
```bash
vercel rollback
```

---

## Monitoring

| Service | Dashboard |
|---|---|
| API errors | sentry.io → Issues |
| User analytics | app.posthog.com → Insights |
| API logs | Railway → Service → Logs |
| Job queue | Railway → Redis CLI: `LLEN arq:queue` |
| MongoDB metrics | Atlas → Metrics |
