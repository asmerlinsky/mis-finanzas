import { useMarketStatus } from '../api/hooks'
import { formatDate, formatMoney } from '../lib/format'

/** Shows the MEP rate in use, and warns when the daily download hasn't succeeded lately. */
export function StaleRateBanner() {
  const { data } = useMarketStatus()
  if (!data) return null
  if (!data.latest_rate_date || !data.latest_rate) {
    return (
      <p className="banner warning">
        Todavía no hay cotización MEP descargada: los montos en USD no se pueden calcular.
      </p>
    )
  }
  const day = formatDate(data.latest_rate_date)
  const rate = formatMoney(data.latest_rate, 'ARS')
  if (data.stale) {
    return (
      <p className="banner warning">
        Cotización MEP desactualizada: la última es del {day} ({rate}).
      </p>
    )
  }
  return (
    <p className="banner">
      Dólar MEP {rate} · {day}
    </p>
  )
}
