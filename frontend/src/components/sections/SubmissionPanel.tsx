import { useState, type DragEvent } from 'react'

import { submitGithubRepository, submitZipRepository } from '../../api/client'
import type { AnalysisJob, RepositorySummary } from '../../types/repository'
import codevivaLogo from '../../assets/codeviva.png'

interface SubmissionPanelProps {
  onRepositoryCreated: (repository: RepositorySummary, job: AnalysisJob) => void
  inputRef?: React.RefObject<HTMLInputElement | null>
}

export function SubmissionPanel({ onRepositoryCreated, inputRef }: SubmissionPanelProps) {
  const [githubUrl, setGithubUrl] = useState('')
  const [zipFile, setZipFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    if (!githubUrl.trim() && !zipFile) {
      setError('Enter a GitHub repository URL or choose a .zip archive to begin ingestion.')
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
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : 'Could not reach the ingestion service. Please verify the repository URL or ZIP file.'
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setIsDragging(false)
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setIsDragging(false)
    const dropped = event.dataTransfer.files?.[0]
    if (dropped) {
      if (!dropped.name.toLowerCase().endsWith('.zip')) {
        setError('Please drop a valid .zip archive.')
        return
      }
      setZipFile(dropped)
      setGithubUrl('')
      setError(null)
    }
  }

  const readySource = githubUrl.trim()
    ? 'GitHub URL ready'
    : zipFile
      ? `ZIP ready (${(zipFile.size / 1024).toFixed(1)} KB)`
      : 'Awaiting source'

  return (
    <section id="workspace-upload" className="notion-mockup-window" aria-label="Repository upload workspace">
      {/* Notion Document Chrome Header */}
      <div className="notion-mockup-window__topbar">
        <div className="notion-mockup-window__breadcrumbs">
          <img src={codevivaLogo} alt="" className="notion-mockup-window__mini-logo" />
          <span className="notion-breadcrumb-sep">/</span>
          <span className="notion-breadcrumb-item">Coursework Defence</span>
          <span className="notion-breadcrumb-sep">/</span>
          <strong className="notion-breadcrumb-active">Step 01 · Repository Upload</strong>
        </div>

        <div className="notion-mockup-window__pills">
          <span className="notion-pill-tag notion-pill-tag--sky">{readySource}</span>
          <span className="notion-pill-tag notion-pill-tag--warning">Python &amp; Polyglot</span>
        </div>
      </div>

      {/* Main 2-Column Workspace Inside Product Mockup */}
      <div className="notion-mockup-window__body">
        <div className="notion-upload-console">
          <div className="notion-upload-console__header">
            <span className="notion-eyebrow">Step 01 · Codebase Intake</span>
            <h2 className="notion-upload-console__title">Upload your assignment repository</h2>
            <p className="notion-upload-console__subtitle">
              Submit a public GitHub URL or upload a local <code>.zip</code> snapshot. CodeViva indexes your files,
              entrypoints, and AST facts to prepare your live technical defence.
            </p>
          </div>

          <div className="notion-upload-form">
            <div className="notion-field-group">
              <div className="notion-field-group__label-row">
                <label className="notion-field-label" htmlFor="github-url">
                  GitHub repository URL
                </label>
              </div>

              <div className="notion-input-wrapper">
                <span className="notion-input-prefix" aria-hidden="true">
                  git
                </span>
                <input
                  ref={inputRef}
                  id="github-url"
                  name="github-url"
                  type="url"
                  className="notion-input"
                  value={githubUrl}
                  onChange={(event) => {
                    setGithubUrl(event.target.value)
                    if (event.target.value.trim()) {
                      setZipFile(null)
                    }
                    setError(null)
                  }}
                  placeholder="https://github.com/username/coursework-project"
                />
                {githubUrl && (
                  <button
                    type="button"
                    className="notion-input-clear"
                    onClick={() => setGithubUrl('')}
                    aria-label="Clear GitHub URL"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            <div className="notion-or-divider" aria-hidden="true">
              <span>or upload local snapshot</span>
            </div>

            <label
              className={`notion-dropzone${isDragging ? ' notion-dropzone--dragging' : ''}${zipFile ? ' notion-dropzone--selected' : ''}`}
              htmlFor="zip-upload"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input
                id="zip-upload"
                name="zip-upload"
                type="file"
                accept=".zip"
                onChange={(event) => {
                  const selected = event.target.files?.[0] ?? null
                  setZipFile(selected)
                  if (selected) {
                    setGithubUrl('')
                    setError(null)
                  }
                }}
              />
              <div className="notion-dropzone__badge-row">
                <span className="notion-pill-tag notion-pill-tag--peach">ZIP Archive</span>
                <span className="notion-caption-muted">Max 100 MB · Text &amp; source files indexed</span>
              </div>

              <div className="notion-dropzone__main">
                <span className="notion-dropzone__icon" aria-hidden="true">
                  {zipFile ? '✓' : '↑'}
                </span>
                <div>
                  <strong className="notion-dropzone__title">
                    {zipFile ? zipFile.name : 'Drop your project .zip archive here, or click to browse'}
                  </strong>
                  <p className="notion-dropzone__hint">
                    {zipFile
                      ? `${(zipFile.size / 1024).toFixed(1)} KB archive selected and ready for extraction.`
                      : 'Automatically strips .git, node_modules, __pycache__, .venv, and binary assets.'}
                  </p>
                </div>
              </div>
            </label>

            {error ? (
              <div className="notion-error-banner" role="alert">
                <div className="notion-error-banner__content">
                  <strong>Submission notice:</strong> <span>{error}</span>
                </div>
              </div>
            ) : null}

            <div className="notion-upload-actions">
              <button
                type="button"
                className="notion-btn notion-btn--primary notion-btn--lg"
                onClick={handleSubmit}
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Ingesting & mapping codebase…' : 'Upload & analyse repository'}
              </button>
            </div>
          </div>
        </div>

        {/* Right Side inside Product Mockup: Notion Kanban Board Preview */}
        <aside className="notion-kanban-preview" aria-label="Assessment loop overview">
          <div className="notion-kanban-preview__header">
            <span className="notion-eyebrow">Operational Loop</span>
            <span className="notion-caption-muted">4-page student journey</span>
          </div>

          <div className="notion-kanban-columns">
            <div className="notion-kanban-group">
              <div className="notion-kanban-group__title">
                <span className="notion-pill-tag notion-pill-tag--sky">01 · Upload &amp; Ingest</span>
                <span className="notion-caption-muted">Isolated</span>
              </div>

              <div className="notion-kanban-card">
                <div className="notion-kanban-card__top">
                  <span className="notion-kanban-card__emoji">📦</span>
                  <span className="notion-pill-tag notion-pill-tag--peach">
                    {githubUrl.trim() ? 'GitHub Clone' : zipFile ? 'ZIP Extract' : 'Ready'}
                  </span>
                </div>
                <strong className="notion-kanban-card__title">
                  {githubUrl.trim()
                    ? githubUrl.trim().replace(/^https?:\/\/github\.com\//, '')
                    : zipFile
                      ? zipFile.name
                      : 'Repository intake & file inventory'}
                </strong>
                <p className="notion-kanban-card__meta">Maps modules, entrypoints, tests &amp; code chunks</p>
              </div>
            </div>

            <div className="notion-kanban-group">
              <div className="notion-kanban-group__title">
                <span className="notion-pill-tag notion-pill-tag--warning">02 · Grounded Plan</span>
                <span className="notion-caption-muted">Stages 0–5</span>
              </div>

              <div className="notion-kanban-card">
                <div className="notion-kanban-card__top">
                  <span className="notion-kanban-card__emoji">🧭</span>
                  <span className="notion-pill-tag notion-pill-tag--sky">AST + Rules + LLM</span>
                </div>
                <strong className="notion-kanban-card__title">Verified code-anchored questions</strong>
                <p className="notion-kanban-card__meta">Extracts AST/commit facts &amp; verifies every line citation</p>
              </div>
            </div>

            <div className="notion-kanban-group">
              <div className="notion-kanban-group__title">
                <span className="notion-pill-tag notion-pill-tag--coral">03 &amp; 04 · Viva &amp; Grade</span>
                <span className="notion-caption-muted">Stages 6–7</span>
              </div>

              <div className="notion-kanban-card">
                <div className="notion-kanban-card__top">
                  <span className="notion-kanban-card__emoji">🎙️</span>
                  <span className="notion-pill-tag notion-pill-tag--warning">Voice &amp; Text</span>
                </div>
                <strong className="notion-kanban-card__title">Live oral defence &amp; results page</strong>
                <p className="notion-kanban-card__meta">
                  One question per turn followed by double-pass quote-verified grading
                </p>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </section>
  )
}
