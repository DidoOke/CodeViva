import { useMemo, useState } from 'react'
import type { AnalysisJob, CodeChunk, RepositoryFile, RepositorySummary } from '../../types/repository'
import { MetricCard } from '../primitives/MetricCard'
import { SectionHeading } from '../primitives/SectionHeading'
import { StatusBadge } from '../primitives/StatusBadge'
import codevivaLogo from '../../assets/codeviva.png'

interface RepositoryInsightsProps {
  repository: RepositorySummary
  job: AnalysisJob
  files: RepositoryFile[]
  chunks?: CodeChunk[]
  onStartAssessment: () => void
  onReset: () => void
}

const stageLabels: Record<string, string> = {
  queued: 'Queued for ingestion',
  cloning: 'Fetching repository source',
  extracting: 'Extracting uploaded archive',
  indexing: 'Building repository context',
  completed: 'Grounded context ready',
}

export function RepositoryInsights({
  repository,
  job,
  files,
  chunks = [],
  onStartAssessment,
  onReset,
}: RepositoryInsightsProps) {
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null)
  const [fileTypeFilter, setFileTypeFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const summary = repository.summary_json ?? {}
  const dominantLanguages = summary.dominant_languages ?? repository.detected_languages ?? []
  const entrypoints = summary.entrypoints ?? []
  const topDirectories = summary.top_level_directories ?? []

  const filteredFiles = useMemo(() => {
    return files.filter((file) => {
      const matchesType = fileTypeFilter === 'all' || file.file_type === fileTypeFilter
      const matchesQuery =
        !searchQuery.trim() ||
        file.relative_path.toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
        (file.language ?? '').toLowerCase().includes(searchQuery.trim().toLowerCase())
      return matchesType && matchesQuery
    })
  }, [files, fileTypeFilter, searchQuery])

  const activeFile = useMemo(() => {
    if (selectedFileId !== null) {
      return files.find((f) => f.id === selectedFileId) ?? null
    }
    return filteredFiles[0] ?? files[0] ?? null
  }, [selectedFileId, files, filteredFiles])

  const displayedChunks = useMemo(() => {
    if (!chunks.length) return []
    if (activeFile) {
      const matching = chunks.filter(
        (c) => c.repository_file_id === activeFile.id || c.metadata_json?.path === activeFile.relative_path
      )
      if (matching.length > 0) return matching
    }
    return chunks.slice(0, 6)
  }, [chunks, activeFile])

  return (
    <div className="notion-results-container">
      {/* Top Repository Header Card */}
      <section id="repo-overview" className="notion-mockup-window">
        <div className="notion-mockup-window__topbar">
          <div className="notion-mockup-window__breadcrumbs">
            <img src={codevivaLogo} alt="" className="notion-mockup-window__mini-logo" />
            <span className="notion-breadcrumb-sep">/</span>
            <span className="notion-breadcrumb-item">Step 02 · Repository Context</span>
            <span className="notion-breadcrumb-sep">/</span>
            <strong className="notion-breadcrumb-active">{repository.display_name}</strong>
          </div>

          <div className="notion-mockup-window__pills">
            <StatusBadge
              label={stageLabels[job.stage] ?? repository.status}
              tone={repository.status === 'completed' ? 'sky' : 'warning'}
            />
            <button type="button" className="notion-btn notion-btn--ghost-cta" onClick={onReset}>
              ← Upload different repository
            </button>
            <button type="button" className="notion-btn notion-btn--primary" onClick={onStartAssessment}>
              Start Live Assessment Test →
            </button>
          </div>
        </div>

        <div className="notion-results-hero-body">
          <div className="notion-results-hero-body__main">
            <div className="notion-results-hero-body__badges">
              <span className="notion-pill-tag notion-pill-tag--peach">
                Source: {repository.source_type === 'github' ? 'GitHub Clone' : 'ZIP Archive'}
              </span>
              {dominantLanguages.map((lang) => (
                <span key={lang} className="notion-pill-tag notion-pill-tag--sky">
                  {lang}
                </span>
              ))}
            </div>

            <h1 className="notion-results-title">
              {repository.display_name}{' '}
              <span className="notion-hero-pill notion-hero-pill--sm">Ingested</span>
            </h1>

            <p className="notion-lyon-subhead">
              Your repository has been mapped into structured file metadata and line-referenced code chunks. Review your
              indexed project structure below, then proceed to the live oral assessment test.
            </p>
          </div>

          <div className="notion-metric-grid">
            <MetricCard
              label="Indexed files"
              value={summary.file_count ?? files.length}
              supportingText="Text & source files in working tree"
            />
            <MetricCard
              label="Source code"
              value={summary.code_file_count ?? files.filter((f) => f.file_type === 'source').length}
              supportingText="Implementation modules mapped"
            />
            <MetricCard
              label="Test suites"
              value={summary.test_file_count ?? files.filter((f) => f.file_type === 'test').length}
              supportingText="Verification & test files detected"
            />
            <MetricCard
              label="Retrieval chunks"
              value={chunks.length || Math.max(files.length, 1)}
              supportingText="Line-indexed context blocks"
              accent="marigold"
            />
          </div>

          <div className="notion-signals-strip">
            <div className="notion-signal-group">
              <span className="notion-eyebrow">Top-level directories</span>
              <div className="notion-pill-cluster">
                {topDirectories.length ? (
                  topDirectories.map((dir) => (
                    <code key={dir} className="notion-code-chip">
                      /{dir}
                    </code>
                  ))
                ) : (
                  <span className="notion-caption-muted">Root-level files</span>
                )}
              </div>
            </div>

            <div className="notion-signal-group">
              <span className="notion-eyebrow">Inferred entrypoints</span>
              <div className="notion-pill-cluster">
                {entrypoints.length ? (
                  entrypoints.map((entry) => (
                    <code key={entry} className="notion-code-chip notion-code-chip--blue">
                      {entry}
                    </code>
                  ))
                ) : (
                  <span className="notion-caption-muted">Module library structure</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Prominent Call-to-Action Banner to Launch Live Assessment Test */}
      <section className="notion-section">
        <div className="notion-accent-card notion-accent-card--marigold">
          <div className="notion-accent-card__header-row" style={{ alignItems: 'center' }}>
            <div>
              <span className="notion-pill-tag notion-pill-tag--white">Next Step · Operational Loop</span>
              <h2 className="notion-section-title" style={{ marginTop: '10px', fontSize: '36px' }}>
                Ready to begin your live code-grounded assessment?
              </h2>
              <p className="notion-lyon-subhead" style={{ marginTop: '8px' }}>
                CodeViva will extract AST &amp; git history facts from <strong>{repository.display_name}</strong>,
                generate verified code-anchored questions, and conduct a one-question-per-turn viva via voice or text.
              </p>
            </div>

            <button
              type="button"
              className="notion-btn notion-btn--primary notion-btn--hero"
              onClick={onStartAssessment}
            >
              Start Live Assessment Test →
            </button>
          </div>
        </div>
      </section>

      {/* Interactive File Inventory + Code Chunk Inspector */}
      <section id="repo-inspector" className="notion-section">
        <SectionHeading
          eyebrow="Retrieval Context Explorer"
          title="Inspect indexed files and extracted code chunks."
          description="Select any file from the repository inventory on the left to inspect the exact line-indexed chunks stored in PostgreSQL."
        />

        <div className="notion-inspector-grid">
          {/* Left Panel: File Inventory */}
          <div className="notion-white-card notion-inspector-files">
            <div className="notion-inspector-files__controls">
              <input
                type="search"
                className="notion-input notion-input--sm"
                placeholder="Filter files by path or language…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />

              <div className="notion-filter-tabs" role="tablist" aria-label="File type filter">
                {['all', 'source', 'test', 'docs', 'config'].map((type) => (
                  <button
                    key={type}
                    type="button"
                    className={`notion-filter-tab${fileTypeFilter === type ? ' notion-filter-tab--active' : ''}`}
                    onClick={() => setFileTypeFilter(type)}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>

            <div className="notion-file-list" role="listbox" aria-label="Repository files">
              {filteredFiles.length === 0 ? (
                <p className="notion-empty-state">No files match the current filter.</p>
              ) : (
                filteredFiles.map((file) => {
                  const isSelected = activeFile?.id === file.id
                  return (
                    <button
                      key={file.id}
                      type="button"
                      className={`notion-file-row${isSelected ? ' notion-file-row--active' : ''}`}
                      onClick={() => setSelectedFileId(file.id)}
                    >
                      <div className="notion-file-row__main">
                        <code className="notion-file-row__path">{file.relative_path}</code>
                        <div className="notion-file-row__sub">
                          <span className="notion-pill-tag notion-pill-tag--xs">
                            {file.file_type}
                          </span>
                          <span>{file.language ?? 'text'}</span>
                          <span>· {(file.size_bytes / 1024).toFixed(1)} KB</span>
                        </div>
                      </div>
                      <span className="notion-file-row__lines">{file.line_count} lines</span>
                    </button>
                  )
                })
              )}
            </div>
          </div>

          {/* Right Panel: Extracted Code Chunks Viewer */}
          <div className="notion-white-card notion-inspector-chunks">
            <div className="notion-inspector-chunks__header">
              <div>
                <span className="notion-eyebrow">Retrieval Context Blocks</span>
                <h3 className="notion-white-card__title">
                  {activeFile ? activeFile.relative_path : 'Repository Chunks'}
                </h3>
              </div>
              {activeFile ? (
                <span className="notion-pill-tag notion-pill-tag--sky">
                  {activeFile.line_count} lines · SHA {String(activeFile.sha256).slice(0, 8)}
                </span>
              ) : null}
            </div>

            {displayedChunks.length > 0 ? (
              <div className="notion-chunk-stack">
                {displayedChunks.map((chunk) => (
                  <article key={chunk.id} className="notion-chunk-block">
                    <div className="notion-chunk-block__bar">
                      <span className="notion-chunk-block__meta">
                        Chunk #{chunk.chunk_index + 1} ·{' '}
                        <code>
                          L{chunk.start_line}–L{chunk.end_line}
                        </code>
                      </span>
                      <span className="notion-pill-tag notion-pill-tag--peach">{chunk.chunk_type}</span>
                    </div>
                    <pre className="notion-code-pre">
                      <code>{chunk.content}</code>
                    </pre>
                  </article>
                ))}
              </div>
            ) : (
              <div className="notion-chunk-block">
                <div className="notion-chunk-block__bar">
                  <span className="notion-chunk-block__meta">
                    {activeFile ? `${activeFile.relative_path} (L1–L${activeFile.line_count})` : 'File indexed'}
                  </span>
                  <span className="notion-pill-tag notion-pill-tag--sky">Indexed</span>
                </div>
                <p className="notion-white-card__body" style={{ padding: '16px' }}>
                  File metadata and retrieval context are stored in PostgreSQL (`repository_files` &amp; `code_chunks`).
                </p>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
