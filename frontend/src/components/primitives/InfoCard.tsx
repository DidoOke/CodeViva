import type { ReactNode } from 'react'

interface InfoCardProps {
  eyebrow?: string
  title: string
  description?: string
  pill?: string
  pillBg?: string
  children?: ReactNode
}

export function InfoCard({ eyebrow, title, description, pill, pillBg, children }: InfoCardProps) {
  return (
    <article className="notion-white-card">
      <div className="notion-white-card__top">
        {eyebrow ? <span className="notion-eyebrow">{eyebrow}</span> : null}
        {pill ? (
          <span className="notion-pill-tag" style={pillBg ? { backgroundColor: pillBg, color: '#000000' } : undefined}>
            {pill}
          </span>
        ) : null}
      </div>
      <h3 className="notion-white-card__title">{title}</h3>
      {description ? <p className="notion-white-card__body">{description}</p> : null}
      {children}
    </article>
  )
}
