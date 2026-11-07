import { assessmentDimensions, ingestionStages, partnerMarks } from '../../lib/content'
import { SectionHeading } from '../primitives/SectionHeading'

export function IngestionFlow() {
  return (
    <div className="notion-sections-stack">
      {/* Logo / Stack Wall */}
      <section className="notion-logo-wall" aria-label="Architecture and hackathon stack">
        <p className="notion-logo-wall__caption">Built for Reply AI on Campus · Grounded Assessment Architecture</p>
        <div className="notion-logo-wall__grid">
          {partnerMarks.map((mark) => (
            <span key={mark} className="notion-logo-wall__item">
              {mark}
            </span>
          ))}
        </div>
      </section>

      {/* 2x2 Assistant / Capabilities Grid (Top Full-Width Marigold, Bottom 2 Equal Columns) */}
      <section id="examiner-grid" className="notion-section">
        <SectionHeading
          eyebrow="Grounded Examiner Agents"
          title="Every question anchored to the student’s own repository."
          description="Instead of generic trivia or black-box AI detectors, CodeViva turns ingested source files and chunks into a personalised technical defence."
        />

        <div className="notion-assistant-grid">
          {/* Top Full-Width Accent Card (#ffb110 Marigold) */}
          <article className="notion-accent-card notion-accent-card--marigold notion-assistant-grid__full">
            <div className="notion-accent-card__copy">
              <span className="notion-pill-tag notion-pill-tag--white">Adaptive Defence Engine</span>
              <h3 className="notion-accent-card__heading">
                Maps files, symbols, and control flow before asking a single question.
              </h3>
              <p className="notion-accent-card__body">
                When a student uploads a repository, CodeViva builds a complete file inventory and slices source modules
                into overlapping line-indexed chunks. Examiner prompts cite exact file paths and line numbers.
              </p>
            </div>

            <div className="notion-accent-card__mockup">
              <div className="notion-mini-ui">
                <div className="notion-mini-ui__header">
                  <strong>Grounded Viva Prompt · #Q-01</strong>
                  <span className="notion-pill-tag notion-pill-tag--sky">src/engine/minimax.py:L18-L32</span>
                </div>
                <p className="notion-mini-ui__question">
                  “In <code>alphabeta_search</code>, why do you call <code>state.get_ordered_moves()</code> before
                  iterating, and what happens to the <code>alpha &gt;= beta</code> cutoff frequency if moves are
                  un-ordered?”
                </p>
                <div className="notion-mini-ui__branches">
                  <div className="notion-kanban-card">
                    <span className="notion-pill-tag notion-pill-tag--sky">Strong answer</span>
                    <p>Probe transposition table trade-offs &amp; memory complexity</p>
                  </div>
                  <div className="notion-kanban-card">
                    <span className="notion-pill-tag notion-pill-tag--peach">Partial / Unclear</span>
                    <p>Trigger interactive 2-ply execution trace on concrete board state</p>
                  </div>
                </div>
              </div>
            </div>
          </article>

          {/* Bottom Left Accent Card (#f64932 Coral) */}
          <article className="notion-accent-card notion-accent-card--coral">
            <span className="notion-pill-tag notion-pill-tag--white">Practical Verification</span>
            <h3 className="notion-accent-card__heading notion-accent-card__heading--sm">
              Live code modification &amp; concept transfer
            </h3>
            <p className="notion-accent-card__body notion-accent-card__body--light">
              Students complete a small targeted change to their submitted implementation and solve a related DSA transfer
              task—proving they can apply the underlying concept, not just recite explanations.
            </p>
            <div className="notion-kanban-card notion-kanban-card--on-accent">
              <div className="notion-kanban-card__top">
                <strong>Task · Modify cutoff telemetry</strong>
                <span className="notion-pill-tag notion-pill-tag--warning">Sandboxed</span>
              </div>
              <p className="notion-kanban-card__meta">
                Extend <code>alphabeta_search</code> to count pruned branches without mutating <code>BoardState</code>.
              </p>
            </div>
          </article>

          {/* Bottom Right Accent Card (#62aef0 Sky Wash) */}
          <article className="notion-accent-card notion-accent-card--sky">
            <span className="notion-pill-tag notion-pill-tag--white">Educator Evidence Report</span>
            <h3 className="notion-accent-card__heading notion-accent-card__heading--sm">
              Traceable evidence, never a black-box score
            </h3>
            <p className="notion-accent-card__body">
              Lecturers receive the exact question, student response, verified code reference, follow-up probe, and
              confidence notes—keeping human educators in full control of academic marks.
            </p>
            <div className="notion-kanban-card notion-kanban-card--on-accent">
              <div className="notion-kanban-card__top">
                <strong>Criterion · Control &amp; Data Flow</strong>
                <span className="notion-pill-tag notion-pill-tag--sky">Verified</span>
              </div>
              <p className="notion-kanban-card__meta">
                Student traced recursion depth=4 and predicted beta cutoff on 2nd capture move.
              </p>
            </div>
          </article>
        </div>
      </section>

      {/* Alternating 2-Column Section: Ingestion Pipeline Left, Colored Kanban Panel Right */}
      <section id="pipeline-section" className="notion-section notion-two-col">
        <div className="notion-two-col__left">
          <SectionHeading
            eyebrow="Ingestion-First Architecture"
            title="How a codebase becomes retrieval-ready context."
            description="Every stage in our FastAPI + PostgreSQL pipeline is designed for speed, determinism, and traceable grounding."
          />

          <div className="notion-stage-stack">
            {ingestionStages.map((stage) => (
              <article key={stage.id} className="notion-white-card">
                <div className="notion-white-card__top">
                  <span className="notion-stage-code">{stage.code}</span>
                  <span
                    className="notion-pill-tag"
                    style={{ backgroundColor: stage.pillColor, color: stage.pillText }}
                  >
                    {stage.statusPill}
                  </span>
                </div>
                <h3 className="notion-white-card__title">{stage.label}</h3>
                <p className="notion-white-card__body">{stage.description}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="notion-two-col__right">
          <div className="notion-accent-card notion-accent-card--sky-tint">
            <div className="notion-accent-card__header-row">
              <div>
                <span className="notion-eyebrow">Assessment Dimensions</span>
                <h3 className="notion-white-card__title">What CodeViva collects as evidence</h3>
              </div>
              <span className="notion-pill-tag notion-pill-tag--white">8 Dimensions</span>
            </div>

            <div className="notion-dimension-list">
              {assessmentDimensions.map((item) => (
                <div key={item.dimension} className="notion-kanban-card">
                  <div className="notion-kanban-card__top">
                    <strong className="notion-kanban-card__title">{item.dimension}</strong>
                    <span
                      className="notion-pill-tag"
                      style={{ backgroundColor: item.pillBg, color: item.pillText }}
                    >
                      {item.status}
                    </span>
                  </div>
                  <p className="notion-kanban-card__meta">{item.evidence}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
