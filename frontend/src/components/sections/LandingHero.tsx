import { CharacterMarksRow } from '../primitives/CharacterMarks'

interface LandingHeroProps {
  onFocusUpload?: () => void
}

export function LandingHero({ onFocusUpload }: LandingHeroProps) {
  return (
    <section className="notion-hero">
      <CharacterMarksRow />

      <div className="notion-hero__copy">
        <h1 className="notion-hero__headline">
          Don’t detect the AI.{' '}
          <span className="notion-hero__line2">
            <span className="notion-hero-pill">Verify</span> the understanding.
          </span>
        </h1>

        <p className="notion-lyon-subhead notion-hero__subhead">
          AI-code detectors guess authorship; CodeViva verifies mastery. Upload a student repository to map its
          architecture, extract AST &amp; commit facts, and conduct a grounded oral technical defence.
        </p>

        <div className="notion-hero__ctas">
          <button type="button" className="notion-btn notion-btn--primary notion-btn--hero" onClick={onFocusUpload}>
            Upload assignment repository
          </button>
          <a href="#pipeline-section" className="notion-btn notion-btn--ghost-cta notion-btn--hero">
            How the assessment works
          </a>
        </div>
      </div>
    </section>
  )
}
