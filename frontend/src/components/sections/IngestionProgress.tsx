import { ingestionStages } from '../../lib/content'
import type { AnalysisJob, RepositorySummary } from '../../types/repository'
import { StatusBadge } from '../primitives/StatusBadge'

interface IngestionProgressProps {
  repository: RepositorySummary
  job: AnalysisJob
  onReset: () => void
}

const stageToIndex: Record<string, number> = {
  queued: 0,
  cloning: 0,
  extracting: 0,
  indexing: 1,
  completed: 2,
}

export function IngestionProgress({ repository, job, onReset }: IngestionProgressProps) {
  const activeIndex = stageToIndex[job.stage] ?? 0
  const progressValue = Math.round(((activeIndex + 1) / ingestionStages.length) * 100)

  return (
    <section className="notion-section">
      <div className="notion-white-card notion-progress-card">
        <div className="notion-progress-card__top">
          <div>
            <span className="notion-eyebrow">Repository Ingestion in Progress</span>
            <h1 className="notion-results-title">{repository.display_name}</h1>
            <p className="notion-lyon-subhead">
              Extracting source tree, identifying entrypoints, and slicing files into overlapping retrieval chunks.
            </p>
          </div>

          <div className="notion-progress-card__actions">
            <StatusBadge
              label={job.status === 'completed' ? 'Completed' : `Stage: ${job.stage}`}
              tone={job.status === 'completed' ? 'sky' : 'warning'}
            />
            <button type="button" className="notion-btn notion-btn--ghost-cta" onClick={onReset}>
              Cancel &amp; return
            </button>
          </div>
        </div>

        <div className="notion-progress-track" aria-label={`Ingestion progress ${progressValue}%`}>
          <div className="notion-progress-track__fill" style={{ width: `${progressValue}%` }} />
        </div>

        <div className="notion-trust-grid">
          {ingestionStages.map((stage, index) => {
            const state = index < activeIndex ? 'Done' : index === activeIndex ? 'Active' : 'Queued'
            const pillTone = index < activeIndex ? '#e6f3fe' : index === activeIndex ? '#ffb110' : '#f6f5f4'
            return (
              <article key={stage.id} className="notion-kanban-card">
                <div className="notion-kanban-card__top">
                  <strong>
                    {stage.code} · {stage.label}
                  </strong>
                  <span className="notion-pill-tag" style={{ backgroundColor: pillTone, color: '#000000' }}>
                    {state}
                  </span>
                </div>
                <p className="notion-kanban-card__meta">{stage.description}</p>
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}
