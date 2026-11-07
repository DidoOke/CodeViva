import { trustPrinciples } from '../../lib/content'
import { InfoCard } from '../primitives/InfoCard'

interface FuturePlatformStripProps {
  onFocusUpload?: () => void
}

export function FuturePlatformStrip({ onFocusUpload }: FuturePlatformStripProps) {
  return (
    <section id="responsible-ai" className="notion-section">
      {/* Dark Feature Card ("Dark Mode Island" on Light Warm Canvas — #02093a Midnight Ink) */}
      <div className="notion-dark-island">
        <div className="notion-dark-island__header">
          <div>
            <span className="notion-pill-tag notion-pill-tag--marigold">Responsible Academic AI</span>
            <h2 className="notion-dark-island__title">
              Built for fair technical judgement—never automated accusation.
            </h2>
            <p className="notion-dark-island__subhead">
              AI detectors produce false positives because clean implementations of standard algorithms look structurally
              similar. CodeViva shifts assessment from guessing who typed the code to verifying that learning has
              occurred.
            </p>
          </div>

          <div className="notion-dark-island__ctas">
            <button type="button" className="notion-btn notion-btn--primary" onClick={onFocusUpload}>
              Upload repository to begin
            </button>
          </div>
        </div>

        <div className="notion-trust-grid">
          {trustPrinciples.map((item) => (
            <InfoCard
              key={item.title}
              eyebrow={item.eyebrow}
              title={item.title}
              description={item.description}
              pill={item.pill}
              pillBg={item.pillBg}
            />
          ))}
        </div>
      </div>
    </section>
  )
}
