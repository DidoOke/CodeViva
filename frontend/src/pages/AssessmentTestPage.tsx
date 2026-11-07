import { useEffect, useRef, useState } from 'react'
import {
  fetchAssessmentStatus,
  fetchCodingChallenge,
  generateQuestionFollowUp,
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
  RepositorySummary,
  TargetedDefenceQuestion,
} from '../types/repository'
import { AppShell, type FlowStep } from '../components/layout/AppShell'
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

const DEFAULT_TIMER_SECONDS = 30

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
  const [questions, setQuestions] = useState<TargetedDefenceQuestion[]>([])

  // One-at-a-time question state
  const [activeIdx, setActiveIdx] = useState<number>(0)
  const [turnPhase, setTurnPhase] = useState<'primary' | 'followup'>('primary')

  // Per-question student responses
  const [primaryAnswers, setPrimaryAnswers] = useState<Record<string, string>>({})
  const [followUpQuestions, setFollowUpQuestions] = useState<Record<string, string>>({})
  const [followUpNotes, setFollowUpNotes] = useState<Record<string, string>>({})
  const [followUpAnswers, setFollowUpAnswers] = useState<Record<string, string>>({})
  const [modifiedSnippets, setModifiedSnippets] = useState<Record<string, string>>({})
  const [syntaxStatus, setSyntaxStatus] = useState<Record<string, { ok: boolean; msg: string }>>({})

  // 30-second countdown timer state
  const [timeLeft, setTimeLeft] = useState<number>(DEFAULT_TIMER_SECONDS)
  const [timerPaused, setTimerPaused] = useState<boolean>(false)

  // Loading & submission flags
  const [isLoadingAssessment, setIsLoadingAssessment] = useState<boolean>(true)
  const [isGeneratingFollowUp, setIsGeneratingFollowUp] = useState<boolean>(false)
  const [isSubmittingFinal, setIsSubmittingFinal] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  // Voice TTS & STT
  const [isSpeaking, setIsSpeaking] = useState<boolean>(false)
  const [isListening, setIsListening] = useState<boolean>(false)
  const [interimTranscript, setInterimTranscript] = useState<string>('')
  const listeningRef = useRef<ListeningSession | null>(null)

  const currentQuestion: TargetedDefenceQuestion | undefined = questions[activeIdx]

  useEffect(() => {
    let cancelled = false

    async function loadAssessment() {
      setIsLoadingAssessment(true)
      setError(null)
      try {
        const [st, caps, loaded] = await Promise.all([
          fetchAssessmentStatus().catch(() => null),
          getSpeechCapabilities().catch(() => ({ tts: null, stt: null })),
          fetchCodingChallenge(repository.id),
        ])
        if (cancelled) return
        if (st) setStatus(st)
        setSpeechCaps(caps)
        setChallenge(loaded)
        setQuestions(loaded.targeted_questions)

        const initPrimary: Record<string, string> = {}
        const initFollowQ: Record<string, string> = {}
        const initFollowAns: Record<string, string> = {}
        const initMods: Record<string, string> = {}

        for (const q of loaded.targeted_questions) {
          initPrimary[q.id] = ''
          initFollowQ[q.id] = q.follow_up || ''
          initFollowAns[q.id] = ''
          if (q.kind === 'live_modification') {
            initMods[q.id] = q.starter_snippet || q.raw_snippet || ''
          }
        }

        setPrimaryAnswers(initPrimary)
        setFollowUpQuestions(initFollowQ)
        setFollowUpAnswers(initFollowAns)
        setModifiedSnippets(initMods)
        setActiveIdx(0)
        setTurnPhase('primary')
        setTimeLeft(loaded.targeted_questions[0]?.timer_seconds ?? DEFAULT_TIMER_SECONDS)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to prepare tailored codebase questions.')
        }
      } finally {
        if (!cancelled) {
          setIsLoadingAssessment(false)
        }
      }
    }

    loadAssessment()
    return () => {
      cancelled = true
    }
  }, [repository.id])

  // 30-second countdown timer per turn
  useEffect(() => {
    if (
      isLoadingAssessment ||
      isGeneratingFollowUp ||
      isSubmittingFinal ||
      timerPaused ||
      !currentQuestion
    ) {
      return
    }

    if (timeLeft <= 0) {
      // Auto-advance when the 30-second timer expires
      if (turnPhase === 'primary') {
        void handleConfirmPrimaryTurn()
      } else {
        void handleConfirmFollowUpTurn()
      }
      return
    }

    const interval = window.setInterval(() => {
      setTimeLeft((prev) => Math.max(0, prev - 1))
    }, 1000)

    return () => window.clearInterval(interval)
  }, [
    timeLeft,
    timerPaused,
    turnPhase,
    activeIdx,
    isLoadingAssessment,
    isGeneratingFollowUp,
    isSubmittingFinal,
    currentQuestion,
  ])

  async function stopActiveMicrophone() {
    if (isListening && listeningRef.current) {
      try {
        const res = await listeningRef.current.stop()
        setIsListening(false)
        setInterimTranscript('')
        listeningRef.current = null
        return res.text.trim()
      } catch {
        setIsListening(false)
        setInterimTranscript('')
        listeningRef.current = null
      }
    }
    return ''
  }

  async function handleConfirmPrimaryTurn() {
    if (!currentQuestion || isGeneratingFollowUp || isSubmittingFinal) return

    const extraVoice = await stopActiveMicrophone()
    const qid = currentQuestion.id
    const currentAns = [primaryAnswers[qid] ?? '', extraVoice].filter(Boolean).join(' ').trim()
    if (extraVoice) {
      setPrimaryAnswers((prev) => ({ ...prev, [qid]: currentAns }))
    }

    const modCode = modifiedSnippets[qid] ?? ''

    // Check if this question triggers an occasional tailored follow-up
    const shouldFollowUp = Boolean(currentQuestion.ask_follow_up)

    if (shouldFollowUp) {
      setIsGeneratingFollowUp(true)
      setError(null)
      try {
        const followRes = await generateQuestionFollowUp(repository.id, {
          question_id: qid,
          answer: currentAns,
          modified_code: modCode,
        })
        setFollowUpQuestions((prev) => ({
          ...prev,
          [qid]: followRes.follow_up_question || currentQuestion.follow_up,
        }))
        setFollowUpNotes((prev) => ({
          ...prev,
          [qid]: followRes.examiner_context_note || 'Noted.',
        }))
        setTurnPhase('followup')
        setTimeLeft(followRes.timer_seconds ?? DEFAULT_TIMER_SECONDS)
      } catch {
        setTurnPhase('followup')
        setTimeLeft(DEFAULT_TIMER_SECONDS)
      } finally {
        setIsGeneratingFollowUp(false)
      }
    } else {
      await advanceToNextQuestionOrFinish()
    }
  }

  async function handleConfirmFollowUpTurn() {
    if (!currentQuestion || isSubmittingFinal) return

    const extraVoice = await stopActiveMicrophone()
    const qid = currentQuestion.id
    if (extraVoice) {
      setFollowUpAnswers((prev) => ({
        ...prev,
        [qid]: [prev[qid] ?? '', extraVoice].filter(Boolean).join(' ').trim(),
      }))
    }

    await advanceToNextQuestionOrFinish()
  }

  async function advanceToNextQuestionOrFinish() {
    if (activeIdx + 1 < questions.length) {
      const nextIdx = activeIdx + 1
      setActiveIdx(nextIdx)
      setTurnPhase('primary')
      setTimeLeft(questions[nextIdx]?.timer_seconds ?? DEFAULT_TIMER_SECONDS)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } else {
      await handleFinishAndGrade()
    }
  }

  function handleSelectQuestionStep(idx: number) {
    if (isGeneratingFollowUp || isSubmittingFinal) return
    setActiveIdx(idx)
    setTurnPhase('primary')
    setTimeLeft(questions[idx]?.timer_seconds ?? DEFAULT_TIMER_SECONDS)
  }

  async function handleVerifySnippetSyntax(qid: string) {
    const codeToVerify = modifiedSnippets[qid] ?? ''
    try {
      const res = await runCodingChallenge(repository.id, codeToVerify)
      if (res.compile_error) {
        setSyntaxStatus((prev) => ({ ...prev, [qid]: { ok: false, msg: res.compile_error! } }))
      } else {
        setSyntaxStatus((prev) => ({
          ...prev,
          [qid]: { ok: true, msg: '✓ Syntax & AST structure verified cleanly' },
        }))
      }
    } catch {
      setSyntaxStatus((prev) => ({ ...prev, [qid]: { ok: true, msg: '✓ Snippet recorded' } }))
    }
  }

  function handleCodeKeyDown(qid: string, event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Tab') {
      event.preventDefault()
      const target = event.currentTarget
      const start = target.selectionStart
      const end = target.selectionEnd
      const currentCode = modifiedSnippets[qid] ?? ''
      const nextValue = currentCode.substring(0, start) + '    ' + currentCode.substring(end)
      setModifiedSnippets((prev) => ({ ...prev, [qid]: nextValue }))
      requestAnimationFrame(() => {
        target.selectionStart = target.selectionEnd = start + 4
      })
    }
  }

  async function handleSpeakText(text: string) {
    if (isSpeaking) return
    setIsSpeaking(true)
    try {
      await speak(text)
    } catch {
      // Ignore cancellation
    } finally {
      setIsSpeaking(false)
    }
  }

  async function handleToggleMicrophone() {
    if (!currentQuestion) return
    const qid = currentQuestion.id

    if (isListening && listeningRef.current) {
      const text = await stopActiveMicrophone()
      if (text) {
        if (turnPhase === 'primary') {
          setPrimaryAnswers((prev) => ({
            ...prev,
            [qid]: prev[qid] ? `${prev[qid]} ${text}` : text,
          }))
        } else {
          setFollowUpAnswers((prev) => ({
            ...prev,
            [qid]: prev[qid] ? `${prev[qid]} ${text}` : text,
          }))
        }
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
      setIsListening(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Microphone access unavailable.')
    }
  }

  async function handleFinishAndGrade() {
    if (isSubmittingFinal) return
    setIsSubmittingFinal(true)
    setError(null)
    try {
      const formattedAnswers = questions.map((q) => ({
        question_id: q.id,
        answer: (primaryAnswers[q.id] ?? '').trim(),
        follow_up_question: (followUpQuestions[q.id] ?? q.follow_up ?? '').trim(),
        follow_up_answer: (followUpAnswers[q.id] ?? '').trim(),
        modified_code: (modifiedSnippets[q.id] ?? '').trim(),
      }))

      const reportResponse = await submitCodingChallengeAndDefence(repository.id, {
        answers: formattedAnswers,
        use_llm: true,
        round_no: roundNo,
      })
      onCompleteAssessment(reportResponse, null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to grade assessment responses.')
      setIsSubmittingFinal(false)
    }
  }

  const isLiveModification = currentQuestion?.kind === 'live_modification'
  const currentQid = currentQuestion?.id ?? 'Q1'
  const currentPrimaryText = primaryAnswers[currentQid] ?? ''
  const currentFollowUpText = followUpAnswers[currentQid] ?? ''
  const activeAnswerWords = countWords(turnPhase === 'primary' ? currentPrimaryText : currentFollowUpText)
  const timerPercent = Math.min(100, Math.max(0, (timeLeft / DEFAULT_TIMER_SECONDS) * 100))

  return (
    <AppShell
      currentStep="assessment"
      repositoryName={repository.display_name}
      onNavigateStep={onNavigateStep}
      onResetRepo={onReset}
    >
      <div className="notion-results-container">
        {/* Top Assessment Bar & 5-Question Stepper */}
        <section className="notion-mockup-window">
          <div className="notion-mockup-window__topbar">
            <div className="notion-mockup-window__breadcrumbs">
              <img src={codevivaLogo} alt="" className="notion-mockup-window__mini-logo" />
              <span className="notion-breadcrumb-sep">/</span>
              <span className="notion-breadcrumb-item">{repository.display_name}</span>
              <span className="notion-breadcrumb-sep">/</span>
              <strong className="notion-breadcrumb-active">
                Step 03 · Tailored Codebase Questions &amp; Live Code Modification
              </strong>
            </div>

            <div className="notion-mockup-window__pills">
              <span
                className={`notion-pill-tag ${
                  status?.llm_configured ? 'notion-pill-tag--sky' : 'notion-pill-tag--peach'
                }`}
              >
                {status?.llm_configured
                  ? `Agent: ${status.llm_provider} (${status.llm_model})`
                  : 'Deterministic Codebase Examiner'}
              </span>
              <button
                type="button"
                className="notion-btn notion-btn--ghost-cta"
                onClick={() => onNavigateStep('repository')}
              >
                ← Back to Repository Context
              </button>
              <button
                type="button"
                className="notion-btn notion-btn--primary"
                disabled={isSubmittingFinal || isLoadingAssessment}
                onClick={handleFinishAndGrade}
              >
                {isSubmittingFinal ? 'Grading All 5 Questions…' : 'Finish & Grade Now →'}
              </button>
            </div>
          </div>

          {/* 5-Question Progress Stepper Strip */}
          {questions.length > 0 ? (
            <div className="notion-pipeline-toolbar">
              <div className="notion-filter-tabs">
                {questions.map((q, idx) => {
                  const hasAnswered =
                    countWords(primaryAnswers[q.id] ?? '') > 0 ||
                    (q.kind === 'live_modification' &&
                      (modifiedSnippets[q.id] ?? '').trim() !== (q.starter_snippet ?? '').trim())
                  const isCurrent = idx === activeIdx
                  return (
                    <button
                      key={q.id}
                      type="button"
                      className={`notion-filter-tab${isCurrent ? ' notion-filter-tab--active' : ''}`}
                      onClick={() => handleSelectQuestionStep(idx)}
                    >
                      {hasAnswered && !isCurrent ? '✓ ' : ''}
                      {q.id} ·{' '}
                      {q.kind === 'live_modification' ? 'Live Code Edit' : q.dimension_label}
                    </button>
                  )
                })}
              </div>

              {/* 30-Second Timer Controls */}
              <div className="notion-pipeline-toolbar__actions">
                <span
                  className={`notion-pill-tag ${
                    timeLeft <= 5
                      ? 'notion-pill-tag--coral'
                      : timeLeft <= 10
                        ? 'notion-pill-tag--marigold'
                        : 'notion-pill-tag--sky'
                  }`}
                >
                  ⏱ {timeLeft}s remaining ({turnPhase === 'primary' ? 'Main Question' : 'Follow-Up Probe'})
                </span>
                <button
                  type="button"
                  className="notion-btn notion-btn--outlined-xs"
                  onClick={() => setTimerPaused((p) => !p)}
                >
                  {timerPaused ? '▶ Resume Timer' : '⏸ Pause 30s Timer'}
                </button>
                <button
                  type="button"
                  className="notion-btn notion-btn--outlined-xs"
                  onClick={() => setTimeLeft((t) => t + 15)}
                >
                  +15s
                </button>
              </div>
            </div>
          ) : null}

          {/* Visual 30-Second Countdown Progress Bar */}
          {!isLoadingAssessment && currentQuestion ? (
            <div className="notion-timer-bar-track">
              <div
                className={`notion-timer-bar-fill${
                  timeLeft <= 5
                    ? ' notion-timer-bar-fill--coral'
                    : timeLeft <= 10
                      ? ' notion-timer-bar-fill--marigold'
                      : ''
                }`}
                style={{ width: `${timerPercent}%` }}
              />
            </div>
          ) : null}
        </section>

        {error ? (
          <div className="notion-error-banner" role="alert">
            <span>{error}</span>
          </div>
        ) : null}

        {isLoadingAssessment || !currentQuestion ? (
          <div className="notion-white-card">
            <span className="notion-eyebrow">Analyzing Uploaded Codebase</span>
            <h3 className="notion-white-card__title">
              Tailoring 5 code defence and live modification questions to {repository.display_name}…
            </h3>
          </div>
        ) : (
          /* ================================================================
             ACTIVE QUESTION WORKSPACE (ONE AT A TIME · 30s TIMER)
             ================================================================ */
          <div className="notion-hackerrank-grid">
            {/* LEFT PANE: Grounded Code Snippet OR Live Code Modification Editor */}
            <div className="notion-hackerrank-problem">
              {isLiveModification ? (
                <section className="notion-mockup-window">
                  <div className="notion-mockup-window__topbar">
                    <div className="notion-mockup-window__breadcrumbs">
                      <span className="notion-pill-tag notion-pill-tag--marigold">
                        Live Code Modification
                      </span>
                      <code className="notion-code-chip notion-code-chip--blue">
                        {currentQuestion.target_lines || challenge?.target_lines}
                      </code>
                    </div>

                    <div className="notion-mockup-window__pills">
                      <button
                        type="button"
                        className="notion-btn notion-btn--outlined-xs"
                        onClick={() =>
                          setModifiedSnippets((prev) => ({
                            ...prev,
                            [currentQid]:
                              currentQuestion.starter_snippet || currentQuestion.raw_snippet || '',
                          }))
                        }
                      >
                        Reset to Original Code
                      </button>
                      <button
                        type="button"
                        className="notion-btn notion-btn--ghost-cta"
                        onClick={() => handleVerifySnippetSyntax(currentQid)}
                      >
                        ✓ Verify Code Syntax
                      </button>
                    </div>
                  </div>

                  <div className="notion-code-editor-wrap">
                    <textarea
                      className="notion-code-editor-textarea"
                      value={modifiedSnippets[currentQid] ?? ''}
                      onChange={(e) =>
                        setModifiedSnippets((prev) => ({
                          ...prev,
                          [currentQid]: e.target.value,
                        }))
                      }
                      onKeyDown={(e) => handleCodeKeyDown(currentQid, e)}
                      spellCheck={false}
                      aria-label={`Live Code Modification Editor for ${currentQuestion.target_file}`}
                    />
                  </div>

                  {syntaxStatus[currentQid] ? (
                    <div
                      style={{
                        padding: '10px 16px',
                        borderTop: '1px solid rgba(0,0,0,0.08)',
                        backgroundColor: syntaxStatus[currentQid].ok ? '#e6f3fe' : '#fff5f3',
                        color: syntaxStatus[currentQid].ok ? '#0075de' : '#f64932',
                        fontSize: '13px',
                        fontWeight: 500,
                      }}
                    >
                      {syntaxStatus[currentQid].msg}
                    </div>
                  ) : null}
                </section>
              ) : (
                <section className="notion-white-card">
                  <div className="notion-white-card__top">
                    <span className="notion-eyebrow">Your Uploaded Code Context</span>
                    <code className="notion-code-chip notion-code-chip--blue">
                      {currentQuestion.target_lines || currentQuestion.anchor}
                    </code>
                  </div>

                  <h3 className="notion-white-card__title">
                    {currentQuestion.target_file} · <code>{currentQuestion.target_symbol}</code>
                  </h3>

                  <div className="notion-chunk-block">
                    <div className="notion-chunk-block__bar">
                      <span>Verbatim Excerpt from {repository.display_name}</span>
                      <code>{currentQuestion.target_lines}</code>
                    </div>
                    <pre className="notion-code-pre" style={{ maxHeight: '420px' }}>
                      <code>{currentQuestion.code_snippet || challenge?.reference_code}</code>
                    </pre>
                  </div>
                </section>
              )}

              {/* Key Concepts Probed Card */}
              <section className="notion-white-card">
                <div className="notion-white-card__top">
                  <span className="notion-eyebrow">What the Examiner Is Verifying</span>
                  <span className="notion-pill-tag">
                    Question {activeIdx + 1} of {questions.length}
                  </span>
                </div>
                <div className="notion-pill-cluster">
                  {currentQuestion.good_answer_mentions.map((mention, idx) => (
                    <span key={idx} className="notion-pill-tag notion-pill-tag--xs">
                      {mention}
                    </span>
                  ))}
                </div>
              </section>
            </div>

            {/* RIGHT PANE: Active Question / Tailored Follow-Up & Student Response */}
            <div className="notion-hackerrank-Ide">
              <article className="notion-white-card notion-targeted-q-card">
                <div className="notion-white-card__top">
                  <div className="notion-pill-cluster">
                    <span className="notion-stage-code">
                      Question 0{activeIdx + 1} of 0{questions.length}
                    </span>
                    <span
                      className="notion-pill-tag"
                      style={{
                        backgroundColor:
                          dimensionBadgeStyle[currentQuestion.dimension]?.bg ?? '#e6f3fe',
                        color: dimensionBadgeStyle[currentQuestion.dimension]?.text ?? '#0075de',
                      }}
                    >
                      {currentQuestion.dimension_label}
                    </span>
                    <span
                      className={`notion-pill-tag ${
                        isLiveModification ? 'notion-pill-tag--marigold' : 'notion-pill-tag--sky'
                      }`}
                    >
                      {isLiveModification ? 'Live Code Modification' : 'Code Defence Question'}
                    </span>
                  </div>

                  <div className="notion-pill-cluster">
                    {speechCaps.tts ? (
                      <button
                        type="button"
                        className="notion-btn notion-btn--outlined-xs"
                        onClick={() =>
                          handleSpeakText(
                            turnPhase === 'primary'
                              ? currentQuestion.text
                              : followUpQuestions[currentQid] || currentQuestion.follow_up
                          )
                        }
                      >
                        {isSpeaking ? 'Speaking…' : '🔊 Read Aloud'}
                      </button>
                    ) : null}
                  </div>
                </div>

                {/* Primary Question Prompt */}
                <div className="notion-primary-question-box">
                  <span className="notion-eyebrow">Examiner Prompt ({currentQuestion.id})</span>
                  <p className="notion-examiner-quote" style={{ marginTop: '6px' }}>
                    {currentQuestion.text}
                  </p>
                  {isLiveModification && currentQuestion.modification_prompt ? (
                    <p className="notion-caption-muted" style={{ marginTop: '8px' }}>
                      <strong>Task:</strong> {currentQuestion.modification_prompt}
                    </p>
                  ) : null}
                </div>

                {/* If in Primary Turn Phase */}
                {turnPhase === 'primary' ? (
                  <>
                    {isListening && interimTranscript ? (
                      <div className="notion-interim-voice">
                        <span className="notion-pill-tag notion-pill-tag--coral">Listening</span>
                        <span>{interimTranscript}</span>
                      </div>
                    ) : null}

                    <div className="notion-field-group">
                      <div className="notion-field-group__label-row">
                        <label className="notion-field-label" htmlFor="active-primary-answer">
                          {isLiveModification
                            ? 'Explain Your Live Code Modification & Edge-Case Fix'
                            : 'Your Technical Response'}
                        </label>
                        <div className="notion-pill-cluster">
                          <span
                            className={`notion-pill-tag ${
                              activeAnswerWords >= 15
                                ? 'notion-pill-tag--sky'
                                : 'notion-pill-tag--peach'
                            }`}
                          >
                            {activeAnswerWords} words
                          </span>
                          {speechCaps.stt ? (
                            <button
                              type="button"
                              className={`notion-btn ${
                                isListening
                                  ? 'notion-btn--coral-active'
                                  : 'notion-btn--outlined-xs'
                              }`}
                              onClick={handleToggleMicrophone}
                            >
                              {isListening ? '⏹ Stop Mic' : '🎙 Speak Answer'}
                            </button>
                          ) : null}
                        </div>
                      </div>

                      <textarea
                        id="active-primary-answer"
                        className="notion-defence-textarea"
                        rows={5}
                        placeholder={currentQuestion.suggested_outline}
                        value={currentPrimaryText}
                        onChange={(e) =>
                          setPrimaryAnswers((prev) => ({
                            ...prev,
                            [currentQid]: e.target.value,
                          }))
                        }
                      />
                    </div>

                    <div className="notion-upload-actions" style={{ justifyContent: 'space-between' }}>
                      <span className="notion-caption-muted">
                        {currentQuestion.ask_follow_up
                          ? 'Submitting this turn will trigger a tailored follow-up probe on your answer (30s timer).'
                          : 'Submitting this turn will advance to the next codebase question.'}
                      </span>

                      <button
                        type="button"
                        className="notion-btn notion-btn--primary notion-btn--lg"
                        disabled={isGeneratingFollowUp}
                        onClick={handleConfirmPrimaryTurn}
                      >
                        {isGeneratingFollowUp
                          ? 'Examiner Tailoring Follow-Up…'
                          : currentQuestion.ask_follow_up
                            ? 'Submit & Hear Tailored Follow-Up →'
                            : activeIdx + 1 < questions.length
                              ? 'Submit & Next Question →'
                              : 'Submit & Grade Assessment →'}
                      </button>
                    </div>
                  </>
                ) : (
                  /* Follow-Up Turn Phase (30-Second Timer Reset) */
                  <>
                    <div className="notion-student-quote">
                      <strong>Your initial answer:</strong>{' '}
                      {currentPrimaryText || '(Submitted live code modification)'}
                    </div>

                    <div className="notion-followup-callout">
                      <div className="notion-white-card__top">
                        <span className="notion-pill-tag notion-pill-tag--marigold">
                          Tailored Examiner Follow-Up (30s Timer)
                        </span>
                        <span className="notion-caption-muted">
                          {followUpNotes[currentQid] || 'Probing your response'}
                        </span>
                      </div>
                      <p className="notion-examiner-quote" style={{ marginTop: '8px' }}>
                        {followUpQuestions[currentQid] || currentQuestion.follow_up}
                      </p>
                    </div>

                    {isListening && interimTranscript ? (
                      <div className="notion-interim-voice">
                        <span className="notion-pill-tag notion-pill-tag--coral">Listening</span>
                        <span>{interimTranscript}</span>
                      </div>
                    ) : null}

                    <div className="notion-field-group">
                      <div className="notion-field-group__label-row">
                        <label className="notion-field-label" htmlFor="active-followup-answer">
                          Your Follow-Up Response ({currentQuestion.id})
                        </label>
                        <div className="notion-pill-cluster">
                          <span className="notion-pill-tag">{activeAnswerWords} words</span>
                          {speechCaps.stt ? (
                            <button
                              type="button"
                              className={`notion-btn ${
                                isListening
                                  ? 'notion-btn--coral-active'
                                  : 'notion-btn--outlined-xs'
                              }`}
                              onClick={handleToggleMicrophone}
                            >
                              {isListening ? '⏹ Stop Mic' : '🎙 Speak Follow-Up'}
                            </button>
                          ) : null}
                        </div>
                      </div>

                      <textarea
                        id="active-followup-answer"
                        className="notion-defence-textarea"
                        rows={4}
                        placeholder="Address the examiner's follow-up with a concrete detail from your code…"
                        value={currentFollowUpText}
                        onChange={(e) =>
                          setFollowUpAnswers((prev) => ({
                            ...prev,
                            [currentQid]: e.target.value,
                          }))
                        }
                      />
                    </div>

                    <div className="notion-upload-actions" style={{ justifyContent: 'space-between' }}>
                      <button
                        type="button"
                        className="notion-btn notion-btn--ghost-cta"
                        onClick={() => setTurnPhase('primary')}
                      >
                        ← Edit Initial Response
                      </button>

                      <button
                        type="button"
                        className="notion-btn notion-btn--primary notion-btn--lg"
                        disabled={isSubmittingFinal}
                        onClick={handleConfirmFollowUpTurn}
                      >
                        {activeIdx + 1 < questions.length
                          ? `Submit Follow-Up & Go to Question 0${activeIdx + 2} →`
                          : isSubmittingFinal
                            ? 'Running Stage 07 Double-Pass Grader…'
                            : 'Submit Final Answer & View Results →'}
                      </button>
                    </div>
                  </>
                )}
              </article>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}
