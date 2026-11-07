interface StatusBadgeProps {
  label: string
  tone?: 'default' | 'success' | 'warning' | 'neutral' | 'coral' | 'sky' | 'peach' | 'midnight'
}

export function StatusBadge({ label, tone = 'default' }: StatusBadgeProps) {
  return <span className={`notion-pill-tag notion-pill-tag--${tone}`}>{label}</span>
}
