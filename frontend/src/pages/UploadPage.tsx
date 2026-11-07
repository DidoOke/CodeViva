import { useState } from 'react'

import { submitGithubRepository, submitZipRepository } from '../api/client'
import type { AnalysisJob, RepositorySummary } from '../types/repository'

interface UploadPageProps {
  onRepositoryCreated: (repository: RepositorySummary, job: AnalysisJob) => void
}

const pipelineSteps = [
  'Validate repository source',
  'Extract and normalize files',
  'Map structure, languages, and entrypoints',
  'Chunk code for retrieval-ready context',
]

const capabilityCards = [
  {
    title: 'Fast ingestion',
    description:
      'Upload a ZIP or paste a GitHub link to turn a codebase into structured analysis context within minutes.',
  },
  {
    title: 'Retrieval-ready storage',
    description:
      'Code, tests, configs, and docs are normalized into file metadata and chunks for later reasoning.',
  },
  {
    title: 'Built for technical defence',
    description:
      'This first system slice gives future assessment agents grounded, project-specific context instead of guessing.',
  },
]

export function UploadPage({ onRepositoryCreated }: UploadPageProps) {
  const [githubUrl, setGithubUrl] = useState('')
  const [zipFile, setZipFile] = useState<File | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    if (!githubUrl.trim() && !zipFile) {
      setError('Add a GitHub repository URL or choose a ZIP archive first.')
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      const result = githubUrl.trim()
        ? await submitGithubRepository(githubUrl.trim())
        : await submitZipRepository(zipFile as File)

      onRepositoryCreated(result.repository, result.job)
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : 'Failed to analyse repository.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            CV
          </div>
          <div>
            <p className="eyebrow">CodeViva</p>
            <p className="brand-subtitle">Repository ingestion for technical defence</p>
          </div>
        </div>
        <div className="status-pill">Initial system slice</div>
      </header>

      <main className="main-layout">
        <section className="hero-copy">
          <p className="eyebrow">Codebase context engine</p>
          <h1>Upload a repository. Build grounded analysis before the assessment begins.</h1>
          <p className="hero-text">
            CodeViva ingests a student project, extracts structure, files, languages, and retrieval-ready chunks,
            then stores the result for later agent reasoning. No viva yet — just the pipeline that gives the
            system real context.
          </p>
          <p className="results-note">
            Built for a calm, deliberate workflow: upload once, inspect the repository context, and move into
            grounded analysis with confidence.
          </p>

          <div className="hero-meta-grid">
            {capabilityCards.map((card) => (
              <article key={card.title} className="meta-card">
                <h2>{card.title}</h2>
                <p>{card.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="upload-panel" aria-label="Repository submission">
          <div className="panel-header">
            <p className="section-label">Analyse codebase</p>
            <h2>Submit a GitHub repository or ZIP archive</h2>
            <p>
              Start with the repository only. The system will validate the source, map the project, and store it
              for retrieval.
            </p>
          </div>

          <div className="upload-form">
            <label className="field-group" htmlFor="github-url">
              <span>GitHub repository</span>
              <input
                id="github-url"
                name="github-url"
                type="url"
                value={githubUrl}
                onChange={(event) => setGithubUrl(event.target.value)}
                placeholder="https://github.com/username/project"
              />
              <p className="form-hint">Use this for live repositories you want CodeViva to clone and map.</p>
            </label>

            <div className="divider">
              <span>or</span>
            </div>

            <label className="dropzone" htmlFor="zip-upload">
              <input
                id="zip-upload"
                name="zip-upload"
                type="file"
                accept=".zip"
                onChange={(event) => setZipFile(event.target.files?.[0] ?? null)}
              />
              <span className="dropzone-title">{zipFile ? zipFile.name : 'Drop a ZIP archive here'}</span>
              <span className="dropzone-subtitle">Python-first for the MVP. Max 100 MB upload.</span>
            </label>

            {error ? <p className="error-text">{error}</p> : null}

            <button type="button" className="primary-button" onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? 'Analysing…' : 'Analyse codebase'}
            </button>
          </div>

          <div className="pipeline-card">
            <div className="pipeline-header">
              <p className="section-label">Analysis pipeline</p>
              <p className="pipeline-caption">Optimised for fast, deterministic repository understanding</p>
            </div>
            <ol>
              {pipelineSteps.map((step, index) => (
                <li key={step}>
                  <span className="step-index">0{index + 1}</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>
    </div>
  )
}
