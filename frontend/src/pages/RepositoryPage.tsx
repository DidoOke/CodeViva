import type { AnalysisJob, RepositoryFile, RepositorySummary } from '../types/repository'

interface RepositoryPageProps {
  repository: RepositorySummary
  job: AnalysisJob
  files: RepositoryFile[]
  onReset: () => void
}

const stageLabels: Record<string, string> = {
  queued: 'Queued for ingestion',
  cloning: 'Fetching repository source',
  extracting: 'Extracting uploaded archive',
  indexing: 'Building repository context',
  completed: 'Analysis completed',
}

export function RepositoryPage({ repository, job, files, onReset }: RepositoryPageProps) {
  const summary = repository.summary_json ?? {}

  return (
    <div className="app-shell results-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            CV
          </div>
          <div>
            <p className="eyebrow">Repository analysis</p>
            <p className="brand-subtitle">Stored context for later technical defence</p>
          </div>
        </div>
        <button type="button" className="ghost-button" onClick={onReset}>
          Analyse another repository
        </button>
      </header>

      <main className="results-layout">
        <section className="results-hero card-surface">
          <p className="eyebrow">Analysis ready</p>
          <h1>{repository.display_name}</h1>
          <p className="hero-text">
            The repository has been ingested into CodeViva and stored as retrieval-ready project context for later
            assessment generation.
          </p>
          <p className="results-note">
            The current system slice focuses on structure, files, chunks, and repository signals — the grounded
            context layer future assessment agents will use.
          </p>

          <div className="summary-grid">
            <article>
              <span>Status</span>
              <strong>{repository.status}</strong>
            </article>
            <article>
              <span>Current stage</span>
              <strong>{stageLabels[job.stage] ?? job.stage}</strong>
            </article>
            <article>
              <span>Source type</span>
              <strong>{repository.source_type}</strong>
            </article>
            <article>
              <span>Languages</span>
              <strong>{repository.detected_languages.join(', ') || 'Unknown'}</strong>
            </article>
          </div>
        </section>

        <section className="results-grid">
          <article className="card-surface detail-card">
            <p className="section-label">Repository summary</p>
            <ul className="metric-list">
              <li>
                <span>Total files</span>
                <strong>{summary.file_count ?? 0}</strong>
              </li>
              <li>
                <span>Code files</span>
                <strong>{summary.code_file_count ?? 0}</strong>
              </li>
              <li>
                <span>Test files</span>
                <strong>{summary.test_file_count ?? 0}</strong>
              </li>
              <li>
                <span>Entrypoints</span>
                <strong>{(summary.entrypoints ?? []).length || 0}</strong>
              </li>
            </ul>
          </article>

          <article className="card-surface detail-card">
            <p className="section-label">Top-level directories</p>
            <div className="tag-row">
              {(summary.top_level_directories ?? []).length ? (
                (summary.top_level_directories ?? []).map((item) => <span key={item}>{item}</span>)
              ) : (
                <span>No directories detected</span>
              )}
            </div>
          </article>

          <article className="card-surface detail-card">
            <p className="section-label">Entrypoints</p>
            <div className="path-list">
              {(summary.entrypoints ?? []).length ? (
                (summary.entrypoints ?? []).map((entrypoint) => <code key={entrypoint}>{entrypoint}</code>)
              ) : (
                <p>No entrypoints inferred yet.</p>
              )}
            </div>
          </article>

          <article className="card-surface detail-card file-card">
            <p className="section-label">Indexed files</p>
            <div className="file-table">
              {files.slice(0, 12).map((file) => (
                <div key={file.id} className="file-row">
                  <div>
                    <strong>{file.relative_path}</strong>
                    <p>
                      {file.file_type} · {file.language ?? 'unknown'}
                    </p>
                  </div>
                  <span>{file.line_count} lines</span>
                </div>
              ))}
            </div>
          </article>
        </section>
      </main>
    </div>
  )
}
