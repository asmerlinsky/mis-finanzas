import { useEffect, useState } from 'react'

import { StaleRateBanner } from './components/StaleRateBanner'
import { Accounts } from './pages/Accounts'
import { Categories } from './pages/Categories'
import { Dashboard } from './pages/Dashboard'
import { Import } from './pages/Import'
import { Transactions } from './pages/Transactions'

const PAGES = {
  resumen: { label: 'Resumen', component: Dashboard },
  movimientos: { label: 'Movimientos', component: Transactions },
  importar: { label: 'Importar', component: Import },
  cuentas: { label: 'Cuentas', component: Accounts },
  categorias: { label: 'Categorías', component: Categories },
} as const

type PageKey = keyof typeof PAGES

function pageFromHash(): PageKey {
  const key = window.location.hash.replace('#/', '')
  return key in PAGES ? (key as PageKey) : 'resumen'
}

export default function App() {
  const [page, setPage] = useState<PageKey>(pageFromHash)

  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

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
        </nav>
      </header>
      <StaleRateBanner />
      <main>
        <Page />
      </main>
    </div>
  )
}
