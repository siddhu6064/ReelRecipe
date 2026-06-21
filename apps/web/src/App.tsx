import { ClerkProvider, SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { BrowserRouter, Route, Routes, Navigate } from 'react-router-dom'

import { NavBar } from './components/NavBar'
import { OfflineBanner } from './components/OfflineBanner'
import { ImportPage } from './pages/ImportPage'
import { ProcessingPage } from './pages/ProcessingPage'
import { CookbookPage } from './pages/CookbookPage'
import { RecipePage } from './pages/RecipePage'
import { PantryPage } from './pages/PantryPage'
import { DiscoverPage } from './pages/DiscoverPage'
import { MealPlannerPage } from './pages/MealPlannerPage'
import { ProfilePage } from './pages/ProfilePage'
import { ExplorePage } from './pages/ExplorePage'
import { CollectionsPage } from './pages/CollectionsPage'
import { StatsPage } from './pages/StatsPage'

const CLERK_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 1000 * 60 * 5, retry: 2 } },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SignedIn>{children}</SignedIn>
      <SignedOut><RedirectToSignIn /></SignedOut>
    </>
  )
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <NavBar />
      <OfflineBanner />
      <main>{children}</main>
    </>
  )
}

export default function App() {
  return (
    <ClerkProvider publishableKey={CLERK_KEY}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/import" replace />} />
            {[
              { path: '/import',       el: <ImportPage /> },
              { path: '/processing/:jobId', el: <ProcessingPage /> },
              { path: '/cookbook',     el: <CookbookPage /> },
              { path: '/recipes/:recipeId', el: <RecipePage /> },
              { path: '/pantry',       el: <PantryPage /> },
              { path: '/discover',     el: <DiscoverPage /> },
              { path: '/meal-planner', el: <MealPlannerPage /> },
              { path: '/profile',      el: <ProfilePage /> },
              { path: '/explore',      el: <ExplorePage /> },
              { path: '/collections',  el: <CollectionsPage /> },
              { path: '/stats',         el: <StatsPage /> },
            ].map(({ path, el }) => (
              <Route key={path} path={path} element={
                <ProtectedRoute>
                  <Layout>{el}</Layout>
                </ProtectedRoute>
              } />
            ))}
          </Routes>
        </BrowserRouter>
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </ClerkProvider>
  )
}
