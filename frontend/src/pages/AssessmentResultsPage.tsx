import { useState } from 'react'
import type {
  AssessmentPlanResponse,
  AssessmentReportResponse,
  RepositorySummary,
} from '../types/repository'
import { AppShell, type FlowStep } from '../components/layout/AppShell'
import { SectionHeading } from '../components/primitives/SectionHeading'
import codevivaLogo from '../assets/codeviva.png'

interface AssessmentResultsPageProps {
  repository: RepositorySummary
  reportData: AssessmentReportResponse
  planData: AssessmentPlanResponse | null
  onNavigateStep: (step: FlowStep) => void
  onRetakeAssessment: () => void
  onReset: () => void
}

const dimensionColors: Record<string, { bg: string; text: string }> = {
  decision_rationale: { bg: '#ffb110', text: '#000000' },
  code_understanding: { bg: '#e6f3fe', text: '#0075de' },
  debugging_failure_handling: { bg: '#f64932', text: '#ffffff' },
  communication_under_follow_up: { bg: '#f6d5b8', text: '#000000' },
  consistency_across_rounds: { bg: '#62aef0', text: '#000000' },
}

export function AssessmentResultsPage({
  repository,
  reportData,
  planData,
  onNavigateStep,
  onRetakeAssessment,
  onReset,
}: AssessmentResultsPageProps) {
  const [copiedMarkdown, setCopiedMarkdown] = useState(false)
  const { report, transcript, markdown } = reportData

  return (
    <AppShell
      currentStep="results"
      repositoryName={repository.display_name}
      onNavigateStep={onNavigateStep}
      onResetRepo={onReset}
    >
      <div className="notion-results-container">
        {/* Top Navigation & Summary Window */}
        <section className="notion-mockup-window">
          <div className="notion-mockup-window__topbar">
            <div className="notion-mockup-window__breadcrumbs">
              <img src={codevivaLogo} alt="" className="notion-mockup-window__mini-logo" />
              <span className="notion-breadcrumb-sep">/</span>
              <span className="notion-breadcrumb-item">{repository.display_name}</span>
              <span className="notion-breadcrumb-sep">/</span>
              <strong className="notion-breadcrumb-active">
                Step 04 · Assessment Results &amp; Educator Evidence Report
              </strong>
            </div>

            <div className="notion-mockup-window__pills">
              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                onClick={onRetakeAssessment}
              >
                ↻ Retake Viva Assessment
              </button>
              <button
                type="button"
                className="notion-btn notion-btn--primary"
                onClick={onReset}
              >
                Upload New Repository
              </button>
            </div>
          </div>

          {/* Midnight Ink (#02093a) Dark Feature Island Header */}
          <div className="notion-dark-island" style={{ borderRadius: '0 0 12px 12px' }}>
            <div className="notion-dark-island__header">
              <div>
                <div className="notion-pill-cluster">
                  <span className="notion-pill-tag notion-pill-tag--marigold">
                    Stage 07 · Double-Pass Quote-Verified Report
                  </span>
                  <span
                    className={`notion-pill-tag ${
                      report.needs_human_review ? 'notion-pill-tag--coral' : 'notion-pill-tag--sky'
                    }`}
                  >
                    {report.needs_human_review
                      ? 'Flagged for Mandatory Academic Review'
                      : 'Pass 1 & Pass 2 Aligned'}
                  </span>
                </div>

                <h1 className="notion-dark-island__title" style={{ fontSize: 'clamp(36px, 5vw, 54px)' }}>
                  Draft Total: {report.total ?? 0} / {report.max_total}
                </h1>
                <p className="notion-dark-island__subhead">{report.disclaimer}</p>
              </div>

              <div className="notion-report-summary-badges">
                {report.coding_challenge ? (
                  <div className="notion-report-stat-box">
                    <span>Coding Exercise</span>
                    <strong>
                      {report.coding_challenge.passed_count} / {report.coding_challenge.total_count} Tests Passed (
                      {report.coding_challenge.runtime_ms} ms)
                    </strong>
                  </div>
                ) : null}
                <div className="notion-report-stat-box">
                  <span>Pass 1 vs Pass 2</span>
                  <strong>
                    {report.pass_totals[0]} / {report.max_total} · {report.pass_totals[1]} / {report.max_total}
                  </strong>
                </div>
                <div className="notion-report-stat-box">
                  <span>Grader Engine</span>
                  <strong>{report.grader}</strong>
                </div>
                <div className="notion-report-stat-box">
                  <span>Quoted Evidence</span>
                  <strong>{report.student_words} student words</strong>
                </div>
              </div>
            </div>

            {report.review_reasons.length > 0 ? (
              <div className="notion-review-reasons-box">
                <strong>Code-computed human review triggers:</strong>
                <ul>
                  {report.review_reasons.map((reason, idx) => (
                    <li key={idx}>{reason}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </section>

        {/* HackerRank Coding Exercise Scorecard */}
        {report.coding_challenge ? (
          <section className="notion-section">
            <SectionHeading
              eyebrow="Part 1 · HackerRank Codebase Exercise Results"
              title={report.coding_challenge.title}
              description={`Executed in isolated Python sandbox against ${report.coding_challenge.total_count} test cases grounded in ${report.coding_challenge.target_lines}.`}
            />

            <div className="notion-two-col">
              <div className="notion-white-card">
                <div className="notion-white-card__top">
                  <span className="notion-eyebrow">Submitted Solution</span>
                  <code className="notion-code-chip notion-code-chip--blue">
                    {report.coding_challenge.target_lines}
                  </code>
                </div>
                <pre className="notion-code-pre" style={{ maxHeight: '320px' }}>
                  <code>{report.coding_challenge.submitted_code}</code>
                </pre>
              </div>

              <div className="notion-stage-stack">
                {report.coding_challenge.test_results.map((tr) => (
                  <div key={tr.id} className="notion-white-card" style={{ padding: '16px 20px' }}>
                    <div className="notion-white-card__top">
                      <div className="notion-pill-cluster">
                        <span className="notion-stage-code">{tr.id}</span>
                        <strong>{tr.name}</strong>
                        <span className="notion-pill-tag notion-pill-tag--xs">{tr.category}</span>
                      </div>
                      <span
                        className={`notion-pill-tag ${
                          tr.passed ? 'notion-pill-tag--sky' : 'notion-pill-tag--coral'
                        }`}
                      >
                        {tr.passed ? `✓ Passed (${tr.runtime_ms} ms)` : '✕ Failed'}
                      </span>
                    </div>
                    <p className="notion-kanban-card__meta">
                      Expected: <code>{tr.expected_display}</code> · Actual: <code>{tr.actual_display}</code>
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>
        ) : null}

        {/* Live Code Modifications Summary */}
        {report.live_modifications && report.live_modifications.length > 0 ? (
          <section className="notion-section">
            <SectionHeading
              eyebrow="Live Code Modifications"
              title="Code changes submitted during your live assessment"
              description="Comparison of the original repository functions and your live modifications made under the 30-second clock."
            />

            <div className="notion-stage-stack">
              {report.live_modifications.map((mod) => (
                <article key={mod.question_id} className="notion-white-card">
                  <div className="notion-white-card__top">
                    <div className="notion-pill-cluster">
                      <span className="notion-stage-code">{mod.question_id}</span>
                      <code className="notion-code-chip notion-code-chip--blue">
                        {mod.target_lines}
                      </code>
                    </div>
                    <span
                      className={`notion-pill-tag ${
                        mod.was_modified ? 'notion-pill-tag--sky' : 'notion-pill-tag--peach'
                      }`}
                    >
                      {mod.was_modified ? '✓ Code Modified Live' : 'Unmodified'}
                    </span>
                  </div>

                  <p className="notion-white-card__body">{mod.prompt}</p>

                  <div className="notion-testcase-io-grid">
                    <div className="notion-chunk-block">
                      <div className="notion-chunk-block__bar">
                        <span>Original Repository Snippet</span>
                      </div>
                      <pre className="notion-code-pre" style={{ maxHeight: '240px' }}>
                        <code>{mod.starter_code}</code>
                      </pre>
                    </div>

                    <div className="notion-chunk-block">
                      <div className="notion-chunk-block__bar">
                        <span>Your Submitted Code Modification</span>
                      </div>
                      <pre className="notion-code-pre" style={{ maxHeight: '240px' }}>
                        <code>{mod.modified_code}</code>
                      </pre>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {/* 5 Rubric Dimensions Breakdown */}
        <section className="notion-section">
          <SectionHeading
            eyebrow="Rubric Dimension Breakdown (0–4 Scale)"
            title="Evidence-backed scores verified against your verbatim answers."
            description="Every dimension score requires verbatim quotes from the student's turns, checked in code by substring verification across two independent grading passes."
          />

          <div className="notion-dimensions-report-grid">
            {report.dimensions.map((dim) => {
              const dimColor = dimensionColors[dim.dimension] ?? { bg: '#e6f3fe', text: '#0075de' }
              return (
                <article key={dim.dimension} className="notion-white-card">
                  <div className="notion-white-card__top">
                    <span
                      className="notion-pill-tag"
                      style={{ backgroundColor: dimColor.bg, color: dimColor.text }}
                    >
                      {dim.label}
                    </span>
                    <span className="notion-pill-tag notion-pill-tag--midnight">
                      {dim.score !== null ? `${dim.score} / 4` : 'Not scored'}
                    </span>
                  </div>

                  <div className="notion-pass-split">
                    <span>
                      Pass 1: <strong>{dim.pass_scores[0] ?? '—'}</strong>
                    </span>
                    <span>·</span>
                    <span>
                      Pass 2: <strong>{dim.pass_scores[1] ?? '—'}</strong>
                    </span>
                    {dim.needs_human_review ? (
                      <span className="notion-pill-tag notion-pill-tag--peach">Review flagged</span>
                    ) : (
                      <span className="notion-pill-tag notion-pill-tag--sky">Verified</span>
                    )}
                  </div>

                  {dim.quotes.length > 0 ? (
                    <div className="notion-quote-stack">
                      <span className="notion-eyebrow">Verbatim Student Quotes</span>
                      {dim.quotes.map((quote, qIdx) => (
                        <blockquote key={qIdx} className="notion-student-quote">
                          “{quote}”
                        </blockquote>
                      ))}
                    </div>
                  ) : (
                    <p className="notion-kanban-card__meta">
                      Insufficient verbatim student evidence on this dimension; deferred to academic reviewer.
                    </p>
                  )}

                  {dim.justifications.length > 0 ? (
                    <p className="notion-kanban-card__meta">
                      <strong>Grader rationale:</strong> {dim.justifications[0]}
                    </p>
                  ) : null}
                </article>
              )
            })}
          </div>
        </section>

        {/* Grounded Question Provenance & Full Viva Transcript */}
        <section className="notion-section">
          <div className="notion-two-col">
            {/* Left Column: Full Interview Transcript */}
            <div className="notion-two-col__left">
              <SectionHeading
                eyebrow="Stage 06 · Recorded Transcript"
                title="Complete oral defence conversation"
                description="Every examiner question and student response recorded during the assessment session."
              />

              <div className="notion-white-card">
                <div className="notion-chat-feed" style={{ maxHeight: '540px' }}>
                  {(transcript.turns ?? []).map((turn, idx) => (
                    <div
                      key={idx}
                      className={`notion-chat-turn notion-chat-turn--${turn.speaker}`}
                    >
                      <div className="notion-chat-turn__meta">
                        <strong>
                          {turn.speaker === 'examiner' ? 'CodeViva Examiner' : 'Student Candidate'}
                        </strong>
                        {turn.question_id ? (
                          <code className="notion-code-chip">{turn.question_id}</code>
                        ) : null}
                      </div>
                      <p className="notion-chat-turn__text">{turn.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Right Column: Question Provenance Trail */}
            <div className="notion-two-col__right">
              <SectionHeading
                eyebrow="Stage 05 → 00 · Question Provenance"
                title="Why each question was asked"
                description="Traceable chain from each viva question back to the rule or LLM proposal, AST fact, and line of code."
              />

              <div className="notion-stage-stack">
                {(planData?.questions ?? []).map((q) => {
                  const dimStyle = dimensionColors[q.dimension] ?? { bg: '#f6d5b8', text: '#000000' }
                  return (
                    <article key={q.id} className="notion-white-card">
                      <div className="notion-white-card__top">
                        <div className="notion-pill-cluster">
                          <span className="notion-stage-code">{q.id}</span>
                          <span
                            className="notion-pill-tag"
                            style={{ backgroundColor: dimStyle.bg, color: dimStyle.text }}
                          >
                            {q.dimension_label}
                          </span>
                        </div>
                        <div className="notion-pill-cluster">
                          {q.citations.map((cite) => (
                            <code key={cite} className="notion-code-chip notion-code-chip--blue">
                              {cite}
                            </code>
                          ))}
                        </div>
                      </div>

                      <p className="notion-examiner-quote">“{q.text}”</p>

                      <details className="notion-explain-drawer">
                        <summary className="notion-explain-drawer__summary">
                          View Stage 5 → Stage 0 provenance trail
                        </summary>
                        <pre className="notion-code-pre notion-explain-pre">{q.explain}</pre>
                      </details>
                    </article>
                  )
                })}
              </div>
            </div>
          </div>
        </section>

        {/* Educator Markdown Report Export */}
        <section className="notion-section">
          <div className="notion-white-card">
            <div className="notion-white-card__top">
              <div>
                <span className="notion-eyebrow">Educator Export · report.md</span>
                <h3 className="notion-white-card__title" style={{ marginTop: '4px' }}>
                  Written feedback &amp; academic review dossier
                </h3>
              </div>

              <button
                type="button"
                className="notion-btn notion-btn--primary"
                onClick={() => {
                  navigator.clipboard?.writeText(markdown)
                  setCopiedMarkdown(true)
                  setTimeout(() => setCopiedMarkdown(false), 2000)
                }}
              >
                {copiedMarkdown ? '✓ Copied report.md' : 'Copy Markdown Report'}
              </button>
            </div>

            <pre className="notion-code-pre notion-markdown-preview">{markdown}</pre>
          </div>
        </section>
      </div>
    </AppShell>
  )
}
