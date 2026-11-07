interface SectionHeadingProps {
  eyebrow?: string
  title: string
  description?: string
  centered?: boolean
}

export function SectionHeading({ eyebrow, title, description, centered = false }: SectionHeadingProps) {
  return (
    <div className={`notion-section-header${centered ? ' notion-section-header--centered' : ''}`}>
      {eyebrow ? <span className="notion-eyebrow">{eyebrow}</span> : null}
      <h2 className="notion-section-title">{title}</h2>
      {description ? <p className="notion-lyon-subhead">{description}</p> : null}
    </div>
  )
}
