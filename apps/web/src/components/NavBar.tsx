import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth, useUser } from '@clerk/clerk-react'
import styles from './NavBar.module.css'

const NAV_ITEMS = [
  { to: '/import',       label: '+ Import' },
  { to: '/cookbook',     label: '📖 Cookbook' },
  { to: '/pantry',       label: '🧄 Pantry' },
  { to: '/discover',     label: '✨ Discover' },
  { to: '/meal-planner', label: '📅 Plan' },
  { to: '/explore',      label: '🌍 Explore' },
  { to: '/collections',  label: '📁 Collections' },
  { to: '/stats',         label: '📊 Stats' },
]

export function NavBar() {
  const { isSignedIn } = useAuth()
  const { user } = useUser()
  const navigate = useNavigate()

  if (!isSignedIn) return null

  return (
    <nav className={styles.nav}>
      <div className={styles.brand} onClick={() => navigate('/import')}>
        🍳 <span className={styles.brandName}>ReelRecipes</span>
      </div>

      <div className={styles.links}>
        {NAV_ITEMS.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `${styles.link} ${isActive ? styles.linkActive : ''}`
            }
          >
            {label}
          </NavLink>
        ))}
      </div>

      <button className={styles.avatar} onClick={() => navigate('/profile')}>
        {user?.imageUrl
          ? <img className={styles.avatarImg} src={user.imageUrl} alt="profile" />
          : <span className={styles.avatarInitial}>{user?.firstName?.[0] ?? '?'}</span>}
      </button>
    </nav>
  )
}
