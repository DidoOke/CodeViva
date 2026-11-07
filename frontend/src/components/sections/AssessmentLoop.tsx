import { useEffect, useRef, useState } from 'react'
import {
  buildAssessmentPlan,
  fetchAssessmentReport,
  fetchAssessmentStatus,
  pollAssessmentInterview,
  runAutoDemoInterviewAndGrade,
  sendInterviewAnswer,
  startAssessmentInterview,
} from '../../api/client'
import {
  getSpeechCapabilities,
  speak,
  startListening,
  type ListeningSession,
  type SpeechCapabilities,
} from '../../speech/speech'
import type {
  AssessmentPlanResponse,
  AssessmentReportResponse,
  AssessmentStatus,
  InterviewMessage,
  RepositorySummary,
} from '../../types/repository'
import { SectionHeading } from '../primitives/SectionHeading'
import codevivaLogo from '../../assets/codeviva.png'

interface AssessmentLoopProps {
  repository: RepositorySummary
}

const dimensionColors: Record<string, { bg: string; text: string }> = {
  decision_rationale: { bg: '#ffb110', text: '#000000' },
  code_understanding: { bg: '#e6f3fe', text: '#0075de' },
  debugging_failure_handling: { bg: '#f64932', text: '#ffffff' },
  communication_under_follow_up: { bg: '#f6d5b8', text: '#000000' },
  consistency_across_rounds: { bg: '#62aef0', text: '#000000' },
}

export function AssessmentLoop({ repository }: AssessmentLoopProps) {
  const [status, setStatus] = useState<AssessmentStatus | null>(null)
  const [speechCaps, setSpeechCaps] = useState<SpeechCapabilities>({ tts: null, stt: null })

  const [demoSubmissionId, setDemoSubmissionId] = useState<string | null>(
    repository.id === 101 ? '1' : null
  )
  const [roundNo, setRoundNo] = useState<number>(1)
  const [useLlm, setUseLlm] = useState<boolean>(true)

  const [planData, setPlanData] = useState<AssessmentPlanResponse | null>(null)
  const [isBuildingPlan, setIsBuildingPlan] = useState<boolean>(false)

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<InterviewMessage[]>([])
  const [interviewDone, setInterviewDone] = useState<boolean>(false)
  const [answerInput, setAnswerInput] = useState<string>('')
  const [isSendingAnswer, setIsSendingAnswer] = useState<boolean>(false)
  const [isAutoGrading, setIsAutoGrading] = useState<boolean>(false)

  const [autoSpeakTts, setAutoSpeakTts] = useState<boolean>(false)
  const [isSpeaking, setIsSpeaking] = useState<boolean>(false)
  const [isListening, setIsListening] = useState<boolean>(false)
  const [interimTranscript, setInterimTranscript] = useState<string>('')
  const listeningRef = useRef<ListeningSession | null>(null)
  const spokenCountRef = useRef<number>(0)

  const [reportData, setReportData] = useState<AssessmentReportResponse | null>(null)
  const [showMarkdownReport, setShowMarkdownReport] = useState<boolean>(false)
  const [copiedMarkdown, setCopiedMarkdown] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const chatContainerRef = useRef<HTMLDivElement | null>(null)

  // Load LLM & Speech status on mount
  useEffect(() => {
    fetchAssessmentStatus()
      .then(setStatus)
      .catch(() => null)
    getSpeechCapabilities()
      .then(setSpeechCaps)
      .catch(() => null)
  }, [])

  // Auto-build Stage 0–5 Plan when repository, demoSubmissionId, or roundNo changes
  useEffect(() => {
    let cancelled = false
    async function loadInitialPlan() {
      setIsBuildingPlan(true)
      setError(null)
      try {
        const res = await buildAssessmentPlan(repository.id, {
          use_llm: useLlm,
          round_no: roundNo,
          demo_submission_id: demoSubmissionId,
        })
        if (!cancelled) {
          setPlanData(res)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to build assessment plan.')
        }
      } finally {
        if (!cancelled) {
          setIsBuildingPlan(false)
        }
      }
    }
    loadInitialPlan()
    return () => {
      cancelled = true
    }
  }, [repository.id, demoSubmissionId, roundNo])

  // Poll active interview session
  useEffect(() => {
    if (!sessionId || interviewDone) return

    const timer = window.setInterval(async () => {
      try {
        const res = await pollAssessmentInterview(sessionId, 0)
        setMessages(res.messages)
        if (res.done) {
          setInterviewDone(true)
          window.clearInterval(timer)
          // Fetch completed Stage 7 grading report
          try {
            const rep = await fetchAssessmentReport(repository.id, roundNo, demoSubmissionId)
            setReportData(rep)
            setPlanData((prev) => (prev ? { ...prev, stages: rep.stages } : prev))
          } catch {
            // Report might take a moment
          }
        }
      } catch {
        // Ignore transient poll errors
      }
    }, 800)

    return () => window.clearInterval(timer)
  }, [sessionId, interviewDone, repository.id, roundNo, demoSubmissionId])

  // Scroll chat to bottom and optionally speak new examiner turns
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
    if (autoSpeakTts && messages.length > spokenCountRef.current) {
      const latestExaminer = [...messages.slice(spokenCountRef.current)]
        .reverse()
        .find((m) => m.speaker === 'examiner')
      spokenCountRef.current = messages.length
      if (latestExaminer) {
        handleSpeakText(latestExaminer.text)
      }
    } else {
      spokenCountRef.current = messages.length
    }
  }, [messages, autoSpeakTts])

  async function handleRebuildPlan() {
    setIsBuildingPlan(true)
    setError(null)
    try {
      const res = await buildAssessmentPlan(repository.id, {
        use_llm: useLlm,
        round_no: roundNo,
        demo_submission_id: demoSubmissionId,
      })
      setPlanData(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rebuild plan.')
    } finally {
      setIsBuildingPlan(false)
    }
  }

  async function handleStartLiveInterview() {
    setError(null)
    setReportData(null)
    setInterviewDone(false)
    spokenCountRef.current = 0
    try {
      const res = await startAssessmentInterview(repository.id, {
        use_llm: useLlm,
        round_no: roundNo,
        demo_submission_id: demoSubmissionId,
      })
      setSessionId(res.session_id)
      setMessages(res.messages)
      setInterviewDone(res.done)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start live interview.')
    }
  }

  async function handleSendAnswer(textOverride?: string) {
    const textToSend = (textOverride ?? answerInput).trim()
    if (!sessionId || !textToSend || isSendingAnswer || interviewDone) return

    setIsSendingAnswer(true)
    if (!textOverride) {
      setAnswerInput('')
    }
    try {
      const res = await sendInterviewAnswer(sessionId, textToSend)
      setMessages(res.messages)
      if (res.done) {
        setInterviewDone(true)
        const rep = await fetchAssessmentReport(repository.id, roundNo, demoSubmissionId)
        setReportData(rep)
        setPlanData((prev) => (prev ? { ...prev, stages: rep.stages } : prev))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send response.')
    } finally {
      setIsSendingAnswer(false)
    }
  }

  async function handleInstantAutoGrade() {
    setIsAutoGrading(true)
    setError(null)
    try {
      const rep = await runAutoDemoInterviewAndGrade(repository.id, {
        use_llm: useLlm,
        round_no: roundNo,
        demo_submission_id: demoSubmissionId,
      })
      setReportData(rep)
      if (rep.transcript?.turns) {
        setMessages(
          rep.transcript.turns.map((t) => ({
            speaker: t.speaker,
            text: t.text,
          }))
        )
      }
      setInterviewDone(true)
      setPlanData((prev) => (prev ? { ...prev, stages: rep.stages } : prev))
      const reportEl = document.getElementById('stage7-grading-report')
      if (reportEl) {
        setTimeout(() => reportEl.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run instant demo interview & grading.')
    } finally {
      setIsAutoGrading(false)
    }
  }

  async function handleSpeakText(text: string) {
    if (isSpeaking) return
    setIsSpeaking(true)
    try {
      await speak(text)
    } catch {
      // Ignore speech cancellation or unsupported browser errors
    } finally {
      setIsSpeaking(false)
    }
  }

  async function handleToggleMicrophone() {
    if (isListening && listeningRef.current) {
      try {
        const result = await listeningRef.current.stop()
        setIsListening(false)
        setInterimTranscript('')
        listeningRef.current = null
        if (result.text.trim()) {
          setAnswerInput((prev) => (prev ? `${prev} ${result.text.trim()}` : result.text.trim()))
        }
      } catch (err) {
        setIsListening(false)
        setInterimTranscript('')
        listeningRef.current = null
        setError(err instanceof Error ? err.message : 'Voice transcription failed.')
      }
      return
    }

    try {
      setInterimTranscript('')
      const session = await startListening({
        onInterim: (liveText) => setInterimTranscript(liveText),
      })
      listeningRef.current = session
      setIsListening(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Microphone access is unavailable.')
    }
  }

  return (
    <div id="viva-preview" className="notion-assessment-loop">
      {/* ====================================================================
          1. Stage 0–7 Pipeline Control Console & Artifact Table
         ==================================================================== */}
      <section className="notion-section">
        <SectionHeading
          eyebrow="Stages 0–7 · Grounded Viva & Grading Engine"
          title="Transform repository facts into a verified oral defence and draft grade."
          description="CodeViva parses AST & commit history (never executing untrusted code), matches lecturer markdown rules, verifies LLM proposals in code, conducts a one-question-per-turn viva, and double-grades with verbatim student quote verification."
        />

        <div className="notion-mockup-window">
          <div className="notion-mockup-window__topbar">
            <div className="notion-mockup-window__breadcrumbs">
              <img src={codevivaLogo} alt="" className="notion-mockup-window__mini-logo" />
              <span className="notion-breadcrumb-sep">/</span>
              <span className="notion-breadcrumb-item">Assessment Pipeline</span>
              <span className="notion-breadcrumb-sep">/</span>
              <strong className="notion-breadcrumb-active">
                Submission #{planData?.submission_id ?? (demoSubmissionId || repository.id)} · Round {roundNo}
              </strong>
            </div>

            <div className="notion-mockup-window__pills">
              <span
                className={`notion-pill-tag ${
                  status?.llm_configured ? 'notion-pill-tag--sky' : 'notion-pill-tag--peach'
                }`}
              >
                {status?.llm_configured
                  ? `LLM Active: ${status.llm_provider} (${status.llm_model})`
                  : 'Mode: Deterministic Rules + Heuristic Grader'}
              </span>
              <span className="notion-pill-tag notion-pill-tag--warning">
                Voice: {speechCaps.tts === 'server' ? 'ElevenLabs API' : speechCaps.tts === 'browser' ? 'Browser Web Speech' : 'Text Mode'}
              </span>
            </div>
          </div>

          <div className="notion-pipeline-toolbar">
            <div className="notion-pipeline-toolbar__filters">
              <div className="notion-control-cluster">
                <span className="notion-eyebrow">Target Codebase</span>
                <div className="notion-filter-tabs">
                  {repository.id !== 101 && (
                    <button
                      type="button"
                      className={`notion-filter-tab${demoSubmissionId === null ? ' notion-filter-tab--active' : ''}`}
                      onClick={() => setDemoSubmissionId(null)}
                    >
                      Uploaded: {repository.display_name}
                    </button>
                  )}
                  <button
                    type="button"
                    className={`notion-filter-tab${demoSubmissionId === '1' ? ' notion-filter-tab--active' : ''}`}
                    onClick={() => setDemoSubmissionId('1')}
                  >
                    Submission 1 (Full History)
                  </button>
                  <button
                    type="button"
                    className={`notion-filter-tab${demoSubmissionId === '2' ? ' notion-filter-tab--active' : ''}`}
                    onClick={() => {
                      setDemoSubmissionId('2')
                      setRoundNo(1)
                    }}
                  >
                    Submission 2 (Broad Except / Loop Sort)
                  </button>
                </div>
              </div>

              <div className="notion-control-cluster">
                <span className="notion-eyebrow">Assessment Round</span>
                <div className="notion-filter-tabs">
                  <button
                    type="button"
                    className={`notion-filter-tab${roundNo === 1 ? ' notion-filter-tab--active' : ''}`}
                    onClick={() => setRoundNo(1)}
                  >
                    Round 1 · Initial Viva
                  </button>
                  <button
                    type="button"
                    className={`notion-filter-tab${roundNo === 2 ? ' notion-filter-tab--active' : ''}`}
                    onClick={() => {
                      if (demoSubmissionId === '2') setDemoSubmissionId('1')
                      setRoundNo(2)
                    }}
                  >
                    Round 2 · Delta &amp; Stated-Plan Check
                  </button>
                </div>
              </div>

              <div className="notion-control-cluster">
                <span className="notion-eyebrow">Model Layer</span>
                <label className="notion-toggle-label">
                  <input
                    type="checkbox"
                    checked={useLlm}
                    onChange={(e) => setUseLlm(e.target.checked)}
                  />
                  <span>Enable LLM (Stages 3, 6, 7)</span>
                </label>
              </div>
            </div>

            <div className="notion-pipeline-toolbar__actions">
              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                onClick={handleRebuildPlan}
                disabled={isBuildingPlan}
              >
                {isBuildingPlan ? 'Running Stages 0–5…' : '↻ Rebuild Plan (Stages 0–5)'}
              </button>
              <button
                type="button"
                className="notion-btn notion-btn--primary"
                onClick={handleInstantAutoGrade}
                disabled={isAutoGrading}
              >
                {isAutoGrading ? 'Grading interview…' : '⚡ Instant Demo Interview & Grade (Stages 0–7)'}
              </button>
            </div>
          </div>

          {error ? (
            <div className="notion-error-banner" style={{ margin: '0 24px 16px' }} role="alert">
              <strong>Assessment notice:</strong> <span>{error}</span>
            </div>
          ) : null}

          {/* Stage 0–7 Artifact Table */}
          {planData ? (
            <div className="notion-stages-table-wrap">
              <table className="notion-stages-table">
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th>Pipeline Step</th>
                    <th>Artifact Summary</th>
                    <th>Model / Engine</th>
                    <th>In → Out</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {planData.stages.map((st) => (
                    <tr key={st.id}>
                      <td>
                        <code className="notion-code-chip">#{st.id}</code>
                      </td>
                      <td>
                        <strong>{st.name}</strong>
                      </td>
                      <td>{st.summary}</td>
                      <td>
                        {st.model ? (
                          <span className="notion-pill-tag notion-pill-tag--sky">{st.model}</span>
                        ) : (
                          <span className="notion-caption-muted">Deterministic code</span>
                        )}
                      </td>
                      <td>
                        {st.count_in !== null && st.count_out !== null ? (
                          <code>
                            {st.count_in} → {st.count_out}
                          </code>
                        ) : (
                          <span className="notion-caption-muted">—</span>
                        )}
                      </td>
                      <td>
                        <span
                          className={`notion-pill-tag ${
                            st.status === 'completed'
                              ? 'notion-pill-tag--sky'
                              : st.status === 'error'
                                ? 'notion-pill-tag--coral'
                                : 'notion-pill-tag--xs'
                          }`}
                        >
                          {st.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </section>

      {/* ====================================================================
          2. Round 2 Stated-Plan Delta Check (if Round 2 is active)
         ==================================================================== */}
      {planData?.delta?.plan_items && planData.delta.plan_items.length > 0 ? (
        <section className="notion-section">
          <div className="notion-accent-card notion-accent-card--sky-tint">
            <div className="notion-accent-card__header-row">
              <div>
                <span className="notion-pill-tag notion-pill-tag--white">
                  Stage 1d · Round 2 Delta &amp; Stated-Plan Check
                </span>
                <h3 className="notion-white-card__title" style={{ marginTop: '10px' }}>
                  Did the student implement what they planned in Round 1?
                </h3>
                <p className="notion-white-card__body">
                  CodeViva splits the student’s Round 1 closing answer into verbatim claims and searches the Round 2 AST
                  and diff for supporting evidence.
                </p>
              </div>
              <span className="notion-pill-tag notion-pill-tag--warning">
                Mode: {planData.delta.stated_plan?.claim_mode ?? 'deterministic'}
              </span>
            </div>

            <div className="notion-trust-grid">
              {planData.delta.plan_items.map((item, idx) => (
                <article key={idx} className="notion-kanban-card">
                  <div className="notion-kanban-card__top">
                    <strong>Claim #{idx + 1}</strong>
                    <span
                      className={`notion-pill-tag ${
                        item.status === 'found' ? 'notion-pill-tag--sky' : 'notion-pill-tag--coral'
                      }`}
                    >
                      {item.status === 'found' ? 'Evidence found' : 'No code evidence'}
                    </span>
                  </div>
                  <p className="notion-white-card__body" style={{ fontSize: '14px' }}>
                    “{item.claim}”
                  </p>
                  {item.evidence.length > 0 ? (
                    <div className="notion-pill-cluster" style={{ marginTop: '6px' }}>
                      {item.evidence.map((ev, i) => (
                        <code key={i} className="notion-code-chip notion-code-chip--blue">
                          {ev.file}
                          {ev.line ? `:${ev.line}` : ''} {ev.commit_short ?? ''}
                        </code>
                      ))}
                    </div>
                  ) : (
                    <p className="notion-kanban-card__meta">
                      Code could not find this change; Round 2 plan will ask the student where to look.
                    </p>
                  )}
                </article>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {/* ====================================================================
          3. Stage 1 Facts & Stage 5 Grounded Question Plan + Provenance
         ==================================================================== */}
      {planData ? (
        <section className="notion-section">
          <div className="notion-two-col">
            {/* Left Column: Stage 5 Selected Viva Questions + Explainability */}
            <div className="notion-two-col__left">
              <div className="notion-section-header">
                <span className="notion-eyebrow">
                  Stage 5 · Grounded Question Plan ({planData.mode})
                </span>
                <h3 className="notion-section-title" style={{ fontSize: '34px' }}>
                  {planData.questions.length} verified questions selected for viva
                </h3>
                <p className="notion-lyon-subhead">
                  No two questions share the same file/line or commit anchor. Click “Why this question?” on any card to
                  inspect the full Stage 5 → Stage 0 provenance chain.
                </p>
              </div>

              <div className="notion-stage-stack">
                {planData.questions.map((q) => {
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
                          <span className="notion-pill-tag notion-pill-tag--xs">
                            Source: {q.source.type === 'model' ? `Verified LLM (${q.source.proposal_id})` : `Rule (${q.source.rule_id})`}
                          </span>
                        </div>

                        <button
                          type="button"
                          className="notion-btn--outlined-xs"
                          onClick={() => handleSpeakText(q.text)}
                          title="Read question aloud"
                        >
                          🔊 Speak
                        </button>
                      </div>

                      {q.citations.length > 0 ? (
                        <div className="notion-pill-cluster">
                          {q.citations.map((cite) => (
                            <code key={cite} className="notion-code-chip notion-code-chip--blue">
                              {cite}
                            </code>
                          ))}
                        </div>
                      ) : null}

                      <p className="notion-examiner-quote">“{q.text}”</p>

                      {q.follow_up ? (
                        <p className="notion-kanban-card__meta">
                          <strong>Prepared follow-up probe:</strong> {q.follow_up}
                        </p>
                      ) : null}

                      <details className="notion-explain-drawer">
                        <summary className="notion-explain-drawer__summary">
                          Why was this question asked? (Stage 5 → Stage 0 provenance trail)
                        </summary>
                        <pre className="notion-code-pre notion-explain-pre">{q.explain}</pre>
                      </details>
                    </article>
                  )
                })}
              </div>
            </div>

            {/* Right Column: Stage 1 Deterministic AST & Git Facts */}
            <div className="notion-two-col__right">
              <div className="notion-accent-card notion-accent-card--marigold">
                <div className="notion-accent-card__header-row">
                  <div>
                    <span className="notion-pill-tag notion-pill-tag--white">
                      Stage 1 &amp; 2 · AST &amp; Git Facts
                    </span>
                    <h3 className="notion-white-card__title" style={{ marginTop: '10px' }}>
                      {planData.facts_summary.total} deterministic facts extracted
                    </h3>
                  </div>
                  <span className="notion-pill-tag notion-pill-tag--white">
                    {planData.rule_matches_summary.triggered_count} / {planData.rule_matches_summary.total_rules} KB
                    rules triggered
                  </span>
                </div>

                <div className="notion-pill-cluster">
                  {Object.entries(planData.facts_summary.counts_by_kind).map(([kind, count]) => (
                    <span key={kind} className="notion-pill-tag notion-pill-tag--white">
                      {kind}: {count}
                    </span>
                  ))}
                </div>

                <div className="notion-dimension-list" style={{ maxHeight: '460px', overflowY: 'auto' }}>
                  {planData.facts_summary.facts.slice(0, 10).map((f) => (
                    <div key={f.id} className="notion-kanban-card">
                      <div className="notion-kanban-card__top">
                        <code>
                          {f.id} · {f.kind}
                        </code>
                        {f.file ? (
                          <code className="notion-code-chip">
                            {f.file}
                            {f.line ? `:${f.line}` : ''}
                          </code>
                        ) : null}
                      </div>
                      <p className="notion-kanban-card__meta">
                        {f.kind === 'constant_changed' && (
                          <>
                            Constant <code>{f.name}</code> changed from <code>{String(f.old)}</code> →{' '}
                            <code>{String(f.new)}</code>
                          </>
                        )}
                        {f.kind === 'fix_commit' && (
                          <>
                            Fix commit <code>{f.commit_short}</code>: “{f.commit_message}”
                          </>
                        )}
                        {f.kind === 'constant' && (
                          <>
                            Constant <code>{f.name}</code> = <code>{String(f.value)}</code>
                          </>
                        )}
                        {f.kind === 'exception_handler' && (
                          <>
                            In <code>{f.function}()</code>: <code>{f.handler}</code> ({f.broad ? 'broad catch' : 'specific'}, body: {f.body_kind})
                          </>
                        )}
                        {f.kind === 'data_structure' && (
                          <>
                            In <code>{f.function}()</code>: uses <code>{f.structure}</code> ({f.usage})
                          </>
                        )}
                        {f.kind === 'numeric_comparison' && (
                          <>
                            In <code>{f.function}()</code>: <code>{f.expr}</code>
                          </>
                        )}
                        {f.kind === 'loop_nesting' && (
                          <>
                            In <code>{f.function}()</code>: nested loop depth = {f.depth}
                          </>
                        )}
                        {f.kind === 'test_function' && (
                          <>
                            Unit test function <code>{f.name}()</code>
                          </>
                        )}
                        {f.kind === 'import' && (
                          <>
                            Imports <code>{f.names}</code> from <code>{f.module}</code>
                          </>
                        )}
                      </p>
                    </div>
                  ))}
                </div>

                {planData.not_triggered.length > 0 ? (
                  <div className="notion-kanban-card">
                    <strong className="notion-kanban-card__title">
                      Rules not triggered ({planData.not_triggered.length})
                    </strong>
                    <p className="notion-kanban-card__meta">
                      {planData.not_triggered.map((nt) => nt.rule_id).join(', ')} — no matching AST/history facts in
                      this submission.
                    </p>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {/* ====================================================================
          4. Stage 6 Interactive Voice & Text Examiner Interview
         ==================================================================== */}
      <section className="notion-section">
        <div className="notion-mockup-window">
          <div className="notion-mockup-window__topbar">
            <div className="notion-mockup-window__breadcrumbs">
              <img src={codevivaLogo} alt="" className="notion-mockup-window__mini-logo" />
              <span className="notion-breadcrumb-sep">/</span>
              <span className="notion-breadcrumb-item">Stage 6 · Interactive Viva Examiner</span>
              <span className="notion-breadcrumb-sep">/</span>
              <strong className="notion-breadcrumb-active">
                {sessionId ? `Session ${sessionId}` : interviewDone ? 'Transcript Complete' : 'Ready to Start'}
              </strong>
            </div>

            <div className="notion-mockup-window__pills">
              <label className="notion-toggle-label">
                <input
                  type="checkbox"
                  checked={autoSpeakTts}
                  onChange={(e) => setAutoSpeakTts(e.target.checked)}
                />
                <span>🔊 Auto-speak examiner turns</span>
              </label>

              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                onClick={handleStartLiveInterview}
              >
                {sessionId && !interviewDone ? '↻ Restart Live Viva' : '▶ Start Live Viva Interview'}
              </button>

              <button
                type="button"
                className="notion-btn notion-btn--primary"
                onClick={handleInstantAutoGrade}
                disabled={isAutoGrading}
              >
                {isAutoGrading ? 'Running & Grading…' : '⚡ Instant Demo & Grade'}
              </button>
            </div>
          </div>

          <div className="notion-interview-body">
            {messages.length === 0 ? (
              <div className="notion-interview-empty">
                <span className="notion-pill-tag notion-pill-tag--peach">One question per turn · No time limit</span>
                <h3 className="notion-white-card__title" style={{ marginTop: '8px' }}>
                  Ready for the code-grounded oral examination
                </h3>
                <p className="notion-lyon-subhead">
                  Click <strong>“Start Live Viva Interview”</strong> to answer questions one by one via voice or text, or
                  click <strong>“Instant Demo &amp; Grade”</strong> to replay a full student defence and generate the
                  Stage 7 grading report immediately.
                </p>
              </div>
            ) : (
              <div ref={chatContainerRef} className="notion-chat-feed" aria-live="polite">
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`notion-chat-turn notion-chat-turn--${msg.speaker}`}
                  >
                    <div className="notion-chat-turn__meta">
                      <strong>{msg.speaker === 'examiner' ? 'CodeViva Examiner' : 'Student Candidate'}</strong>
                      {msg.speaker === 'examiner' ? (
                        <button
                          type="button"
                          className="notion-btn--outlined-xs"
                          onClick={() => handleSpeakText(msg.text)}
                        >
                          🔊 Listen
                        </button>
                      ) : null}
                    </div>
                    <p className="notion-chat-turn__text">{msg.text}</p>
                  </div>
                ))}
              </div>
            )}

            {interimTranscript ? (
              <div className="notion-interim-voice">
                <span className="notion-pill-tag notion-pill-tag--coral">🎤 Listening live…</span>
                <span>{interimTranscript}</span>
              </div>
            ) : null}

            <form
              className="notion-interview-controls"
              onSubmit={(e) => {
                e.preventDefault()
                handleSendAnswer()
              }}
            >
              <button
                type="button"
                className={`notion-btn ${
                  isListening ? 'notion-btn--coral-active' : 'notion-btn--ghost-cta'
                }`}
                onClick={handleToggleMicrophone}
                disabled={!sessionId || interviewDone}
                title="Answer with your microphone (ElevenLabs STT or Browser Speech Recognition)"
              >
                {isListening ? '⏹ Stop & Transcribe' : '🎤 Speak Answer'}
              </button>

              <input
                type="text"
                className="notion-input notion-input--sm"
                placeholder={
                  !sessionId
                    ? 'Click "Start Live Viva Interview" above to type or speak your answer…'
                    : interviewDone
                      ? 'Interview completed — see Stage 7 Grading Report below.'
                      : 'Explain how your code works (or type "repeat" or "pass")…'
                }
                value={answerInput}
                onChange={(e) => setAnswerInput(e.target.value)}
                disabled={!sessionId || interviewDone || isSendingAnswer}
              />

              <button
                type="submit"
                className="notion-btn notion-btn--primary"
                disabled={!sessionId || interviewDone || isSendingAnswer || !answerInput.trim()}
              >
                {isSendingAnswer ? 'Sending…' : 'Send Answer'}
              </button>

              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                disabled={!sessionId || interviewDone || isSendingAnswer}
                onClick={() => handleSendAnswer('repeat')}
                title="Ask the examiner to repeat the current question verbatim"
              >
                Repeat
              </button>

              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                disabled={!sessionId || interviewDone || isSendingAnswer}
                onClick={() => handleSendAnswer('pass')}
                title="Skip the current question neutrally"
              >
                Pass
              </button>
            </form>
          </div>
        </div>
      </section>

      {/* ====================================================================
          5. Stage 7 Double-Pass Quote-Verified Grading Report
         ==================================================================== */}
      {reportData ? (
        <section id="stage7-grading-report" className="notion-section">
          {/* Midnight Ink (#02093a) Dark Feature Island for Educator Grading Summary */}
          <div className="notion-dark-island">
            <div className="notion-dark-island__header">
              <div>
                <div className="notion-pill-cluster">
                  <span className="notion-pill-tag notion-pill-tag--marigold">
                    Stage 7 · Double-Pass Quote-Verified Report
                  </span>
                  <span
                    className={`notion-pill-tag ${
                      reportData.report.needs_human_review
                        ? 'notion-pill-tag--coral'
                        : 'notion-pill-tag--sky'
                    }`}
                  >
                    {reportData.report.needs_human_review
                      ? 'Flagged for Mandatory Academic Review'
                      : 'Pass 1 & Pass 2 Aligned'}
                  </span>
                </div>

                <h2 className="notion-dark-island__title">
                  Draft Score: {reportData.report.total ?? 0} / {reportData.report.max_total}
                </h2>
                <p className="notion-dark-island__subhead">{reportData.report.disclaimer}</p>
              </div>

              <div className="notion-report-summary-badges">
                <div className="notion-report-stat-box">
                  <span>Pass 1 vs Pass 2</span>
                  <strong>
                    {reportData.report.pass_totals[0]} / {reportData.report.max_total} ·{' '}
                    {reportData.report.pass_totals[1]} / {reportData.report.max_total}
                  </strong>
                </div>
                <div className="notion-report-stat-box">
                  <span>Grader Engine</span>
                  <strong>{reportData.report.grader}</strong>
                </div>
                <div className="notion-report-stat-box">
                  <span>Student Evidence</span>
                  <strong>{reportData.report.student_words} words quoted</strong>
                </div>
              </div>
            </div>

            {reportData.report.review_reasons.length > 0 ? (
              <div className="notion-review-reasons-box">
                <strong>Code-computed human review triggers:</strong>
                <ul>
                  {reportData.report.review_reasons.map((reason, idx) => (
                    <li key={idx}>{reason}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {/* 5 Rubric Dimensions Cards on Warm/White Surface */}
            <div className="notion-dimensions-report-grid">
              {reportData.report.dimensions.map((dim) => {
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
                        <span className="notion-eyebrow">Verbatim Student Quotes (Substring-Verified)</span>
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

            <div className="notion-dark-island__footer">
              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                onClick={() => setShowMarkdownReport((prev) => !prev)}
              >
                {showMarkdownReport ? 'Hide Markdown Report (report.md)' : '📄 View Educator Markdown Report (report.md)'}
              </button>

              {showMarkdownReport ? (
                <button
                  type="button"
                  className="notion-btn notion-btn--primary"
                  onClick={() => {
                    navigator.clipboard?.writeText(reportData.markdown)
                    setCopiedMarkdown(true)
                    setTimeout(() => setCopiedMarkdown(false), 2000)
                  }}
                >
                  {copiedMarkdown ? '✓ Copied report.md' : 'Copy Markdown'}
                </button>
              ) : null}
            </div>

            {showMarkdownReport ? (
              <pre className="notion-code-pre notion-markdown-preview">{reportData.markdown}</pre>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  )
}
