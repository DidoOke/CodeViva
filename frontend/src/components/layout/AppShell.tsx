import type { ReactNode } from 'react'
import codevivaLogo from '../../assets/codeviva.png'

export type FlowStep = 'upload' | 'repository' | 'assessment' | 'results'

interface AppShellProps {
  children: ReactNode
  currentStep?: FlowStep
  repositoryName?: string
  hasResults?: boolean
  onNavigateStep?: (step: FlowStep) => void
  onResetRepo?: () => void
  onPrimaryAction?: () => void
}

const flowSteps: Array<{ id: FlowStep; code: string; label: string }> = [
  { id: 'upload', code: '01', label: 'Upload Code' },
  { id: 'repository', code: '02', label: 'Repository Context' },
  { id: 'assessment', code: '03', label: 'Live Assessment Test' },
  { id: 'results', code: '04', label: 'Assessment Results' },
]

export function AppShell({
  children,
  currentStep = 'upload',
  repositoryName,
  hasResults = false,
  onNavigateStep,
  onResetRepo,
  onPrimaryAction,
}: AppShellProps) {
  const stepOrder = flowSteps.map((s) => s.id)
  const currentIdx = stepOrder.indexOf(currentStep)

  return (
    <div className="notion-page-shell">
      <header className="notion-navbar">
        <div className="notion-navbar__inner">
          <div className="notion-navbar__brand-group">
            <a
              href="#top"
              className="notion-brand-link"
              onClick={(event) => {
                if (currentStep !== 'upload' && onResetRepo) {
                  event.preventDefault()
                  onResetRepo()
                }
              }}
              aria-label="CodeViva Home"
            >
              <img src={codevivaLogo} alt="CodeViva" className="notion-brand-logo" />
            </a>
            {repositoryName ? (
              <span className="notion-pill-tag notion-pill-tag--sky">{repositoryName}</span>
            ) : (
              <span className="notion-pill-tag notion-pill-tag--peach">Reply AI on Campus</span>
            )}
          </div>

          {currentStep === 'upload' ? (
            <nav className="notion-navbar__links" aria-label="Primary navigation">
              <a href="#workspace-upload" className="notion-nav-link">
                Upload Workspace
              </a>
              <a href="#examiner-grid" className="notion-nav-link">
                Capabilities
              </a>
              <a href="#pipeline-section" className="notion-nav-link">
                How it works
              </a>
              <a href="#responsible-ai" className="notion-nav-link">
                Responsible AI
              </a>
            </nav>
          ) : (
            <nav className="notion-navbar__links" aria-label="Assessment loop steps">
              {flowSteps.map((step, idx) => {
                const isActive = step.id === currentStep
                const isReachable =
                  idx <= currentIdx ||
                  step.id === 'repository' ||
                  step.id === 'assessment' ||
                  (step.id === 'results' && hasResults)
                return (
                  <button
                    key={step.id}
                    type="button"
                    disabled={!isReachable}
                    className={`notion-step-nav-item${isActive ? ' notion-step-nav-item--active' : ''}${
                      idx < currentIdx ? ' notion-step-nav-item--done' : ''
                    }`}
                    onClick={() => {
                      if (step.id === 'upload' && onResetRepo) {
                        onResetRepo()
                      } else if (isReachable && onNavigateStep) {
                        onNavigateStep(step.id)
                      }
                    }}
                  >
                    <span className="notion-step-nav-item__code">{step.code}</span>
                    <span>{step.label}</span>
                  </button>
                )
              })}
            </nav>
          )}

          <div className="notion-navbar__actions">
            {currentStep === 'upload' ? (
              <button type="button" className="notion-btn notion-btn--primary" onClick={onPrimaryAction}>
                Upload repository
              </button>
            ) : (
              <>
                {currentStep === 'repository' && onPrimaryAction ? (
                  <button type="button" className="notion-btn notion-btn--primary" onClick={onPrimaryAction}>
                    Start Live Assessment Test →
                  </button>
                ) : null}
                <button type="button" className="notion-btn notion-btn--ghost-cta" onClick={onResetRepo}>
                  New submission
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      <main id="top" className="notion-main-container">
        {children}
      </main>

      <footer className="notion-footer">
        <div className="notion-footer__inner">
          <div className="notion-footer__brand">
            <img src={codevivaLogo} alt="CodeViva" className="notion-brand-logo notion-brand-logo--footer" />
            <p className="notion-footer__tagline">
              Don’t detect the AI. Verify the understanding. An adaptive, grounded technical defence workspace for
              university coding projects.
            </p>
          </div>

          <div className="notion-footer__meta">
            <div className="notion-footer__col">
              <span className="notion-footer__heading">Assessment Pipeline</span>
              <span>GitHub &amp; ZIP Archive Intake</span>
              <span>AST &amp; Commit Fact Extraction</span>
              <span>Grounded Oral Viva &amp; Grading</span>
            </div>
            <div className="notion-footer__col">
              <span className="notion-footer__heading">Assessment Guarantee</span>
              <span>Zero AI-Authorship Accusations</span>
              <span>Verified Code Line References</span>
              <span>Educator-in-the-Loop Review</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
