import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { UNAUTHORIZED_EVENT } from './api/client'
import { send, useApiMutation, useAuthStatus } from './api/hooks'

import { StaleRateBanner } from './components/StaleRateBanner'
import { Accounts } from './pages/Accounts'
import { Categories } from './pages/Categories'
import { Dashboard } from './pages/Dashboard'
import { Import } from './pages/Import'
import { Investments } from './pages/Investments'
import { Login } from './pages/Login'
import { Monotributo } from './pages/Monotributo'
import { Transactions } from './pages/Transactions'

const PAGES = {
  resumen: { label: 'Resumen', component: Dashboard },
  movimientos: { label: 'Movimientos', component: Transactions },
  inversiones: { label: 'Inversiones', component: Investments },
  monotributo: { label: 'Monotributo', component: Monotributo },
  importar: { label: 'Importar', component: Import },
  cuentas: { label: 'Cuentas', component: Accounts },
  categorias: { label: 'Categorías', component: Categories },
} as const

type PageKey = keyof typeof PAGES

function pageFromHash(): PageKey {
  const key = window.location.hash.replace('#/', '')
  return key in PAGES ? (key as PageKey) : 'resumen'
}

/** Re-check the login when any request is refused for lack of one (e.g. a session expired). */
function useLoginState() {
  const queryClient = useQueryClient()
  const status = useAuthStatus()
  useEffect(() => {
    const recheck = () => void queryClient.invalidateQueries({ queryKey: ['auth-status'] })
    window.addEventListener(UNAUTHORIZED_EVENT, recheck)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, recheck)
  }, [queryClient])
  return status.data
}

function LogoutButton() {
  const logout = useApiMutation(() => send('POST', '/auth/logout'))
  return (
    <button className="secondary" onClick={() => logout.mutate(undefined)}>
      Salir
    </button>
  )
}

export default function App() {
  const [page, setPage] = useState<PageKey>(pageFromHash)
  const login = useLoginState()

  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  if (!login) return null
  if (!login.authenticated) {
    return (
      <div className="app">
        <header className="topbar">
          <h1>mis-finanzas</h1>
        </header>
        <Login />
      </div>
    )
  }

  const Page = PAGES[page].component
  return (
    <div className="app">
      <header className="topbar">
        <h1>mis-finanzas</h1>
        <nav>
          {Object.entries(PAGES).map(([key, { label }]) => (
            <a key={key} href={`#/${key}`} className={key === page ? 'active' : ''}>
              {label}
            </a>
          ))}
          {login.required && <LogoutButton />}
        </nav>
      </header>
      <StaleRateBanner />
      <main>
        <Page />
      </main>
    </div>
  )
}
