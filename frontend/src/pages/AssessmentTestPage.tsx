import { useEffect, useRef, useState } from 'react'
import {
  fetchAssessmentStatus,
  fetchCodingChallenge,
  runCodingChallenge,
  submitCodingChallengeAndDefence,
} from '../api/client'
import {
  getSpeechCapabilities,
  speak,
  startListening,
  type ListeningSession,
  type SpeechCapabilities,
} from '../speech/speech'
import type {
  AssessmentPlanResponse,
  AssessmentReportResponse,
  AssessmentStatus,
  CodingChallenge,
  CodingChallengeRunResult,
  RepositorySummary,
  TargetedDefenceQuestion,
} from '../types/repository'
import { AppShell, type FlowStep } from '../components/layout/AppShell'
import { SectionHeading } from '../components/primitives/SectionHeading'
import codevivaLogo from '../assets/codeviva.png'

interface AssessmentTestPageProps {
  repository: RepositorySummary
  roundNo?: number
  onCompleteAssessment: (report: AssessmentReportResponse, plan: AssessmentPlanResponse | null) => void
  onNavigateStep: (step: FlowStep) => void
  onReset: () => void
}

const dimensionBadgeStyle: Record<string, { bg: string; text: string }> = {
  code_understanding: { bg: '#e6f3fe', text: '#0075de' },
  decision_rationale: { bg: '#ffb110', text: '#000000' },
  debugging_failure_handling: { bg: '#f64932', text: '#ffffff' },
  consistency_across_rounds: { bg: '#62aef0', text: '#000000' },
  communication_under_follow_up: { bg: '#f6d5b8', text: '#000000' },
}

function countWords(text: string): number {
  return text
    .trim()
    .split(/\s+/)
    .filter(Boolean).length
}

export function AssessmentTestPage({
  repository,
  roundNo = 1,
  onCompleteAssessment,
  onNavigateStep,
  onReset,
}: AssessmentTestPageProps) {
  const [status, setStatus] = useState<AssessmentStatus | null>(null)
  const [speechCaps, setSpeechCaps] = useState<SpeechCapabilities>({ tts: null, stt: null })

  const [challenge, setChallenge] = useState<CodingChallenge | null>(null)
  const [code, setCode] = useState<string>('')
  const [runResult, setRunResult] = useState<CodingChallengeRunResult | null>(null)
  const [selectedTestCaseIdx, setSelectedTestCaseIdx] = useState<number>(0)

  const [questions, setQuestions] = useState<TargetedDefenceQuestion[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const [isLoadingChallenge, setIsLoadingChallenge] = useState<boolean>(true)
  const [isRunningCode, setIsRunningCode] = useState<boolean>(false)
  const [isSubmittingDefence, setIsSubmittingDefence] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  // Voice TTS & STT per question
  const [speakingQuestionId, setSpeakingQuestionId] = useState<string | null>(null)
  const [listeningQuestionId, setListeningQuestionId] = useState<string | null>(null)
  const [interimTranscript, setInterimTranscript] = useState<string>('')
  const listeningRef = useRef<ListeningSession | null>(null)
  const questionsSectionRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadWorkspace() {
      setIsLoadingChallenge(true)
      setError(null)
      try {
        const [st, caps, loadedChallenge] = await Promise.all([
          fetchAssessmentStatus().catch(() => null),
          getSpeechCapabilities().catch(() => ({ tts: null, stt: null })),
          fetchCodingChallenge(repository.id),
        ])
        if (cancelled) return
        if (st) setStatus(st)
        setSpeechCaps(caps)
        setChallenge(loadedChallenge)
        setCode(loadedChallenge.starter_code)
        setQuestions(loadedChallenge.targeted_questions)

        const initialAnswers: Record<string, string> = {}
        for (const q of loadedChallenge.targeted_questions) {
          initialAnswers[q.id] = ''
        }
        setAnswers(initialAnswers)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load coding challenge for repository.')
        }
      } finally {
        if (!cancelled) {
          setIsLoadingChallenge(false)
        }
      }
    }

    loadWorkspace()
    return () => {
      cancelled = true
    }
  }, [repository.id])

  async function handleRunCode() {
    if (!challenge || isRunningCode) return
    setIsRunningCode(true)
    setError(null)
    try {
      const res = await runCodingChallenge(repository.id, code)
      setRunResult(res)
      if (res.targeted_questions && res.targeted_questions.length > 0) {
        setQuestions(res.targeted_questions)
      }
      // Automatically focus the first failed test case if any failed
      const firstFailedIdx = res.test_results.findIndex((t) => !t.passed)
      if (firstFailedIdx >= 0) {
        setSelectedTestCaseIdx(firstFailedIdx)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute code against test cases.')
    } finally {
      setIsRunningCode(false)
    }
  }

  function scrollToTargetedQuestions() {
    questionsSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  async function handleRunAndProceedToQuestions() {
    await handleRunCode()
    setTimeout(() => {
      scrollToTargetedQuestions()
    }, 150)
  }

  function handleCodeKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Tab') {
      event.preventDefault()
      const target = event.currentTarget
      const start = target.selectionStart
      const end = target.selectionEnd
      const nextValue = code.substring(0, start) + '    ' + code.substring(end)
      setCode(nextValue)
      requestAnimationFrame(() => {
        target.selectionStart = target.selectionEnd = start + 4
      })
    }
  }

  async function handleSpeakQuestion(q: TargetedDefenceQuestion) {
    if (speakingQuestionId) return
    setSpeakingQuestionId(q.id)
    try {
      await speak(`${q.text} Follow up: ${q.follow_up}`)
    } catch {
      // Ignore speech cancellation
    } finally {
      setSpeakingQuestionId(null)
    }
  }

  async function handleToggleDictation(questionId: string) {
    if (listeningQuestionId === questionId && listeningRef.current) {
      try {
        const res = await listeningRef.current.stop()
        setListeningQuestionId(null)
        setInterimTranscript('')
        listeningRef.current = null
        if (res.text.trim()) {
          setAnswers((prev) => ({
            ...prev,
            [questionId]: prev[questionId] ? `${prev[questionId]} ${res.text.trim()}` : res.text.trim(),
          }))
        }
      } catch (err) {
        setListeningQuestionId(null)
        setInterimTranscript('')
        listeningRef.current = null
        setError(err instanceof Error ? err.message : 'Voice transcription failed.')
      }
      return
    }

    try {
      setError(null)
      setInterimTranscript('')
      const session = await startListening({
        onInterim: (interim) => setInterimTranscript(interim),
      })
      listeningRef.current = session
      setListeningQuestionId(questionId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Microphone access unavailable.')
    }
  }

  async function handleSubmitAssessment() {
    if (!challenge || isSubmittingDefence) return
    setIsSubmittingDefence(true)
    setError(null)
    try {
      const formattedAnswers = questions.map((q) => ({
        question_id: q.id,
        answer: (answers[q.id] ?? '').trim(),
      }))
      const reportResponse = await submitCodingChallengeAndDefence(repository.id, {
        code,
        answers: formattedAnswers,
        use_llm: true,
        round_no: roundNo,
      })
      onCompleteAssessment(reportResponse, null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to grade coding exercise and targeted responses.')
    } finally {
      setIsSubmittingDefence(false)
    }
  }

  const answeredCount = questions.filter((q) => countWords(answers[q.id] ?? '') >= 5).length
  const activeTestCase = challenge?.test_cases[selectedTestCaseIdx]
  const activeTestResult = runResult?.test_results[selectedTestCaseIdx]

  return (
    <AppShell
      currentStep="assessment"
      repositoryName={repository.display_name}
      onNavigateStep={onNavigateStep}
      onResetRepo={onReset}
    >
      <div className="notion-results-container">
        {/* Top Assessment Workspace Bar */}
        <section className="notion-mockup-window">
          <div className="notion-mockup-window__topbar">
            <div className="notion-mockup-window__breadcrumbs">
              <img src={codevivaLogo} alt="" className="notion-mockup-window__mini-logo" />
              <span className="notion-breadcrumb-sep">/</span>
              <span className="notion-breadcrumb-item">{repository.display_name}</span>
              <span className="notion-breadcrumb-sep">/</span>
              <strong className="notion-breadcrumb-active">
                Step 03 · HackerRank Codebase Exercise &amp; Targeted Defence
              </strong>
            </div>

            <div className="notion-mockup-window__pills">
              <span
                className={`notion-pill-tag ${
                  status?.llm_configured ? 'notion-pill-tag--sky' : 'notion-pill-tag--peach'
                }`}
              >
                {status?.llm_configured
                  ? `Grader: ${status.llm_provider} (${status.llm_model})`
                  : 'Deterministic Codebase Verifier Ready'}
              </span>
              {runResult ? (
                <span
                  className={`notion-pill-tag ${
                    runResult.all_passed ? 'notion-pill-tag--sky' : 'notion-pill-tag--marigold'
                  }`}
                >
                  Test Suite: {runResult.passed_count} / {runResult.total_count} Passed ({runResult.runtime_ms} ms)
                </span>
              ) : (
                <span className="notion-pill-tag">Test Suite: Ready to Run</span>
              )}
              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                onClick={() => onNavigateStep('repository')}
              >
                ← Back to Repository Context
              </button>
            </div>
          </div>

          <div className="notion-pipeline-toolbar">
            <div className="notion-pipeline-toolbar__filters">
              <div>
                <span className="notion-eyebrow">Part 1 · Live Coding Challenge</span>
                <p className="notion-caption-muted">
                  Complete and run the Python exercise grounded in <code>{challenge?.target_lines ?? 'your repository'}</code>.
                </p>
              </div>
              <div>
                <span className="notion-eyebrow">Part 2 · Targeted Technical Questions ({answeredCount}/{questions.length})</span>
                <p className="notion-caption-muted">
                  Defend your implementation, edge-case handling, and architectural trade-offs across 5 rubric dimensions.
                </p>
              </div>
            </div>

            <div className="notion-pipeline-toolbar__actions">
              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                onClick={scrollToTargetedQuestions}
              >
                Jump to Targeted Questions ({questions.length}) ↓
              </button>
              <button
                type="button"
                className="notion-btn notion-btn--primary"
                disabled={isSubmittingDefence || isLoadingChallenge}
                onClick={handleSubmitAssessment}
              >
                {isSubmittingDefence
                  ? 'Running Grader & Verifying Quotes…'
                  : 'Submit Exercise & Answers for Grading →'}
              </button>
            </div>
          </div>
        </section>

        {error ? (
          <div className="notion-error-banner" role="alert">
            <span>{error}</span>
          </div>
        ) : null}

        {isLoadingChallenge || !challenge ? (
          <div className="notion-white-card">
            <span className="notion-eyebrow">Synthesizing Codebase Challenge</span>
            <h3 className="notion-white-card__title">
              Extracting functions, line anchors, and test cases from {repository.display_name}…
            </h3>
          </div>
        ) : (
          <>
            {/* ================================================================
                PART 1: HACKERRANK-STYLE CODING EXERCISE WORKSPACE
                ================================================================ */}
            <div className="notion-hackerrank-grid">
              {/* Left Pane: Problem Description & Uploaded Codebase Reference */}
              <section className="notion-white-card notion-hackerrank-problem">
                <div className="notion-white-card__top">
                  <span className="notion-pill-tag notion-pill-tag--marigold">{challenge.difficulty}</span>
                  <code className="notion-code-chip notion-code-chip--blue">{challenge.target_lines}</code>
                </div>

                <h2 className="notion-upload-console__title" style={{ fontSize: '24px' }}>
                  {challenge.title}
                </h2>

                <div className="notion-problem-markdown">
                  {challenge.problem_statement.split('\n\n').map((para, idx) => (
                    <p key={idx} className="notion-white-card__body" style={{ whiteSpace: 'pre-line' }}>
                      {para}
                    </p>
                  ))}
                </div>

                <div className="notion-constraints-box">
                  <span className="notion-eyebrow">Invariants &amp; Constraints</span>
                  <ul className="notion-constraints-list">
                    {challenge.constraints.map((c, idx) => (
                      <li key={idx}>{c}</li>
                    ))}
                  </ul>
                </div>

                <div className="notion-chunk-block">
                  <div className="notion-chunk-block__bar">
                    <span>Reference from Your Uploaded Codebase</span>
                    <code>
                      {challenge.target_file} ({challenge.target_symbol})
                    </code>
                  </div>
                  <pre className="notion-code-pre" style={{ maxHeight: '240px' }}>
                    <code>{challenge.reference_code}</code>
                  </pre>
                </div>

                <details className="notion-explain-drawer">
                  <summary className="notion-explain-drawer__summary">
                    Need a nudge? View implementation hint
                  </summary>
                  <p className="notion-caption-muted" style={{ marginTop: '8px', lineHeight: 1.5 }}>
                    {challenge.solution_hint}
                  </p>
                  {challenge.reference_solution ? (
                    <div style={{ marginTop: '10px' }}>
                      <button
                        type="button"
                        className="notion-btn notion-btn--outlined-xs"
                        onClick={() => setCode(challenge.reference_solution ?? challenge.starter_code)}
                      >
                        Load Reference Implementation into Editor
                      </button>
                    </div>
                  ) : null}
                </details>
              </section>

              {/* Right Pane: Code Editor & Live Test Case Runner */}
              <div className="notion-hackerrank-Ide">
                <section className="notion-mockup-window">
                  <div className="notion-mockup-window__topbar">
                    <div className="notion-mockup-window__breadcrumbs">
                      <span className="notion-pill-tag notion-pill-tag--midnight">Python 3.12 Sandbox</span>
                      <code>
                        def {challenge.function_name}(…)
                      </code>
                    </div>

                    <div className="notion-mockup-window__pills">
                      <button
                        type="button"
                        className="notion-btn notion-btn--outlined-xs"
                        onClick={() => setCode(challenge.starter_code)}
                      >
                        Reset Starter Code
                      </button>
                      <button
                        type="button"
                        className="notion-btn notion-btn--ghost-cta"
                        disabled={isRunningCode}
                        onClick={handleRunCode}
                      >
                        {isRunningCode ? 'Running Tests…' : '▶ Run Code'}
                      </button>
                      <button
                        type="button"
                        className="notion-btn notion-btn--primary"
                        disabled={isRunningCode}
                        onClick={handleRunAndProceedToQuestions}
                      >
                        Run &amp; Continue to Questions →
                      </button>
                    </div>
                  </div>

                  <div className="notion-code-editor-wrap">
                    <textarea
                      className="notion-code-editor-textarea"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      onKeyDown={handleCodeKeyDown}
                      spellCheck={false}
                      aria-label="Python Coding Exercise Editor"
                    />
                  </div>
                </section>

                {/* Test Cases & Execution Output Panel */}
                <section className="notion-white-card">
                  <div className="notion-white-card__top">
                    <div>
                      <span className="notion-eyebrow">Automated Verification Suite</span>
                      <h3 className="notion-white-card__title" style={{ marginTop: '2px' }}>
                        Test Cases ({challenge.test_cases.length})
                      </h3>
                    </div>

                    {runResult ? (
                      <div className="notion-pill-cluster">
                        <span
                          className={`notion-pill-tag ${
                            runResult.all_passed ? 'notion-pill-tag--sky' : 'notion-pill-tag--coral'
                          }`}
                        >
                          {runResult.passed_count} / {runResult.total_count} Passed
                        </span>
                        <span className="notion-pill-tag">{runResult.runtime_ms} ms</span>
                      </div>
                    ) : (
                      <span className="notion-caption-muted">
                        Click <strong>▶ Run Code</strong> to execute all {challenge.test_cases.length} test cases
                      </span>
                    )}
                  </div>

                  {runResult?.compile_error ? (
                    <div className="notion-error-banner" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                      <strong>Compilation / Execution Error</strong>
                      <pre className="notion-code-pre" style={{ width: '100%', padding: '8px 0 0' }}>
                        <code>{runResult.compile_error}</code>
                      </pre>
                    </div>
                  ) : null}

                  {/* Test Case Selector Tabs */}
                  <div className="notion-filter-tabs">
                    {challenge.test_cases.map((tc, idx) => {
                      const res = runResult?.test_results[idx]
                      let badge = ''
                      if (res) {
                        badge = res.passed ? '✓ ' : '✕ '
                      }
                      return (
                        <button
                          key={tc.id}
                          type="button"
                          className={`notion-filter-tab${
                            selectedTestCaseIdx === idx ? ' notion-filter-tab--active' : ''
                          }`}
                          onClick={() => setSelectedTestCaseIdx(idx)}
                        >
                          {badge}
                          {tc.id}: {tc.name}
                        </button>
                      )
                    })}
                  </div>

                  {/* Active Test Case Details */}
                  {activeTestCase ? (
                    <div className="notion-testcase-detail">
                      <div className="notion-white-card__top">
                        <span className="notion-pill-tag">{activeTestCase.category}</span>
                        {activeTestResult ? (
                          <span
                            className={`notion-pill-tag ${
                              activeTestResult.passed ? 'notion-pill-tag--sky' : 'notion-pill-tag--coral'
                            }`}
                          >
                            {activeTestResult.passed
                              ? `✓ Passed (${activeTestResult.runtime_ms} ms)`
                              : '✕ Failed'}
                          </span>
                        ) : (
                          <span className="notion-caption-muted">Not run yet</span>
                        )}
                      </div>

                      <div className="notion-testcase-io-grid">
                        <div className="notion-chunk-block">
                          <div className="notion-chunk-block__bar">
                            <span>Input Arguments</span>
                          </div>
                          <pre className="notion-code-pre">
                            <code>{activeTestCase.input_display}</code>
                          </pre>
                        </div>

                        <div className="notion-chunk-block">
                          <div className="notion-chunk-block__bar">
                            <span>Expected Output</span>
                          </div>
                          <pre className="notion-code-pre">
                            <code>{activeTestCase.expected_display}</code>
                          </pre>
                        </div>
                      </div>

                      {activeTestResult ? (
                        <div className="notion-chunk-block">
                          <div className="notion-chunk-block__bar">
                            <span>Your Output</span>
                            <code>{activeTestResult.passed ? 'Exact Match' : 'Mismatch / Error'}</code>
                          </div>
                          <pre className="notion-code-pre">
                            <code>
                              {activeTestResult.error
                                ? activeTestResult.error
                                : activeTestResult.actual_display}
                            </code>
                          </pre>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </section>
              </div>
            </div>

            {/* ================================================================
                PART 2: TARGETED CODEBASE & SOLUTION DEFENCE QUESTIONS
                ================================================================ */}
            <section
              ref={questionsSectionRef}
              id="targeted-defence-questions"
              className="notion-section"
            >
              <SectionHeading
                eyebrow="Part 2 · Targeted Codebase & Exercise Defence"
                title="Defend your implementation and architectural trade-offs."
                description="Answer each targeted question below using specific details from your coding exercise and your uploaded repository. Stage 07 verifies verbatim quotes from your answers across all 5 rubric dimensions."
              />

              <div className="notion-targeted-questions-stack">
                {questions.map((q, idx) => {
                  const badgeColor = dimensionBadgeStyle[q.dimension] ?? {
                    bg: '#e6f3fe',
                    text: '#0075de',
                  }
                  const currentAns = answers[q.id] ?? ''
                  const words = countWords(currentAns)
                  const isListeningThis = listeningQuestionId === q.id

                  return (
                    <article key={q.id} className="notion-white-card notion-targeted-q-card">
                      <div className="notion-white-card__top">
                        <div className="notion-pill-cluster">
                          <span className="notion-stage-code">Question 0{idx + 1}</span>
                          <span
                            className="notion-pill-tag"
                            style={{ backgroundColor: badgeColor.bg, color: badgeColor.text }}
                          >
                            {q.dimension_label}
                          </span>
                          <code className="notion-code-chip notion-code-chip--blue">{q.anchor}</code>
                        </div>

                        <div className="notion-pill-cluster">
                          {speechCaps.tts ? (
                            <button
                              type="button"
                              className="notion-btn notion-btn--outlined-xs"
                              onClick={() => handleSpeakQuestion(q)}
                            >
                              {speakingQuestionId === q.id ? 'Speaking…' : '🔊 Read Question'}
                            </button>
                          ) : null}
                          <span
                            className={`notion-pill-tag ${
                              words >= 15 ? 'notion-pill-tag--sky' : 'notion-pill-tag--peach'
                            }`}
                          >
                            {words} words {words >= 15 ? '✓ Evidence ready' : '(aim for 15+ words)'}
                          </span>
                        </div>
                      </div>

                      <p className="notion-examiner-quote">{q.text}</p>

                      <div className="notion-followup-callout">
                        <span className="notion-eyebrow">Targeted Follow-Up Probe to Address:</span>
                        <p className="notion-white-card__body" style={{ fontSize: '14px', marginTop: '4px' }}>
                          {q.follow_up}
                        </p>
                      </div>

                      {isListeningThis && interimTranscript ? (
                        <div className="notion-interim-voice">
                          <span className="notion-pill-tag notion-pill-tag--coral">Listening</span>
                          <span>{interimTranscript}</span>
                        </div>
                      ) : null}

                      <div className="notion-field-group">
                        <div className="notion-field-group__label-row">
                          <label className="notion-field-label" htmlFor={`answer-${q.id}`}>
                            Your Technical Defence Response ({q.id})
                          </label>
                          <div className="notion-pill-cluster">
                            {speechCaps.stt ? (
                              <button
                                type="button"
                                className={`notion-btn ${
                                  isListeningThis
                                    ? 'notion-btn--coral-active'
                                    : 'notion-btn--outlined-xs'
                                }`}
                                onClick={() => handleToggleDictation(q.id)}
                              >
                                {isListeningThis ? '⏹ Stop Mic' : '🎙 Dictate with Voice'}
                              </button>
                            ) : null}
                          </div>
                        </div>

                        <textarea
                          id={`answer-${q.id}`}
                          className="notion-defence-textarea"
                          rows={4}
                          placeholder={q.suggested_outline}
                          value={currentAns}
                          onChange={(e) =>
                            setAnswers((prev) => ({
                              ...prev,
                              [q.id]: e.target.value,
                            }))
                          }
                        />
                      </div>

                      <div className="notion-pill-cluster">
                        <span className="notion-caption-muted">Key concepts probed:</span>
                        {q.good_answer_mentions.map((mention, mIdx) => (
                          <span key={mIdx} className="notion-pill-tag notion-pill-tag--xs">
                            {mention}
                          </span>
                        ))}
                      </div>
                    </article>
                  )
                })}
              </div>

              {/* Bottom Submit Strip */}
              <div className="notion-accent-card notion-accent-card--sky-tint">
                <div className="notion-accent-card__header-row">
                  <div>
                    <span className="notion-pill-tag notion-pill-tag--white">
                      Ready for Stage 07 Double-Pass Grading
                    </span>
                    <h3 className="notion-accent-card__heading notion-accent-card__heading--sm" style={{ marginTop: '8px' }}>
                      Finish Live Assessment &amp; Generate Verified Grading Report
                    </h3>
                    <p className="notion-accent-card__body" style={{ marginTop: '4px' }}>
                      Your Python coding exercise will be verified against all {challenge.test_cases.length} test cases
                      and your {questions.length} targeted defence answers will be scored across two independent passes
                      with verbatim quote verification.
                    </p>
                  </div>

                  <div className="notion-upload-actions">
                    <button
                      type="button"
                      className="notion-btn notion-btn--primary notion-btn--lg"
                      disabled={isSubmittingDefence}
                      onClick={handleSubmitAssessment}
                    >
                      {isSubmittingDefence
                        ? 'Running Test Suite & Double-Pass Grader…'
                        : 'Submit Assessment & View Results →'}
                    </button>
                  </div>
                </div>
              </div>
            </section>
          </>
        )}
      </div>
    </AppShell>
  )
}
