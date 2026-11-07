interface MetricCardProps {
  label: string
  value: string | number
  supportingText?: string
  accent?: 'white' | 'marigold' | 'sky-tint' | 'peach'
}

export function MetricCard({ label, value, supportingText, accent = 'white' }: MetricCardProps) {
  return (
    <article className={`notion-metric-card notion-metric-card--${accent}`}>
      <span className="notion-metric-card__label">{label}</span>
      <strong className="notion-metric-card__value">{value}</strong>
      {supportingText ? <p className="notion-metric-card__meta">{supportingText}</p> : null}
    </article>
  )
}
