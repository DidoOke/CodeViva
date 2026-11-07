export type RepositoryStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type AnalysisJobStatus = 'pending' | 'processing' | 'completed' | 'failed'

export interface RepositorySummary {
  id: number
  source_type: 'github' | 'upload'
  display_name: string
  status: RepositoryStatus
  github_url?: string | null
  original_filename?: string | null
  detected_languages: string[]
  summary_json: {
    file_count?: number
    code_file_count?: number
    test_file_count?: number
    top_level_directories?: string[]
    entrypoints?: string[]
    dominant_languages?: string[]
  }
  created_at: string
  updated_at: string
}

export interface AnalysisJob {
  id: number
  repository_id: number
  status: AnalysisJobStatus
  stage: string
  error_message?: string | null
  started_at: string
  finished_at?: string | null
}

export interface RepositoryFile {
  id: number
  relative_path: string
  file_type: string
  language?: string | null
  size_bytes: number
  sha256: number | string
  is_text: boolean
  line_count: number
  metadata_json: Record<string, unknown>
}

export interface CodeChunk {
  id: number
  repository_file_id: number
  chunk_index: number
  chunk_type: string
  start_line: number
  end_line: number
  content: string
  metadata_json: {
    path?: string
    language?: string | null
    [key: string]: unknown
  }
}

export interface RepositoryResponse {
  repository: RepositorySummary
  job: AnalysisJob
}

/* ==========================================================================
   Stage 0–7 Oral Assessment & Grading Loop Types
   ========================================================================== */

export interface AssessmentStatus {
  llm_configured: boolean
  llm_provider: string
  llm_model: string
  llm_reason: string
  speech_server_configured: boolean
  demo_submissions: Array<{
    id: string
    assignment: string
    label: string
  }>
}

export interface PipelineStageRow {
  id: string
  name: string
  summary: string
  model: string | null
  count_in: number | null
  count_out: number | null
  status: 'completed' | 'pending' | 'error'
}

export interface ExtractedFact {
  id: string
  kind: string
  file?: string | null
  line?: number | null
  name?: string
  value?: unknown
  old?: unknown
  new?: unknown
  function?: string
  structure?: string
  usage?: string
  exc_types?: string
  handler?: string
  broad?: boolean
  body_kind?: string
  commit?: string
  commit_short?: string
  commit_message?: string
}

export interface PlannedQuestion {
  id: string
  dimension: string
  dimension_label: string
  text: string
  follow_up: string
  good_answer_mentions: string[]
  why_selected: string
  source: {
    type: 'rule' | 'model'
    rule_id?: string
    proposal_id?: string
    fact_id?: string | null
  }
  citations: string[]
  explain: string
}

export interface DeltaPlanItem {
  claim: string
  quote: string
  status: 'found' | 'no_evidence'
  keywords: string[]
  evidence: Array<{
    file?: string
    line?: number
    commit_short?: string
    detail?: string
  }>
}

export interface AssessmentPlanResponse {
  submission_id: string
  round_no: number
  mode: string
  stages: PipelineStageRow[]
  facts_summary: {
    total: number
    python_files: number
    counts_by_kind: Record<string, number>
    facts: ExtractedFact[]
  }
  rule_matches_summary: {
    triggered_count: number
    total_rules: number
  }
  verified_proposals_summary: {
    status: string | null
    accepted: number
    rejected: number
  }
  questions: PlannedQuestion[]
  not_triggered: Array<{ rule_id: string; reason: string }>
  not_selected: Array<{ id: string; reason: string }>
  delta?: {
    stated_plan?: {
      status: string
      claim_mode: string
      answer?: string
    }
    plan_items?: DeltaPlanItem[]
  } | null
}

export interface InterviewMessage {
  speaker: 'examiner' | 'student'
  text: string
}

export interface InterviewSessionState {
  session_id: string
  submission_id: string
  round_no: number
  messages: InterviewMessage[]
  done: boolean
  error: string
}

export interface GradedDimension {
  dimension: string
  label: string
  score: number | null
  pass_scores: Array<number | null>
  quotes: string[]
  justifications: string[]
  needs_human_review: boolean
  review_reasons: string[]
}

export interface CodingChallengeTestCase {
  id: string
  name: string
  category: string
  input_display: string
  expected_display: string
  is_hidden: boolean
}

export interface CodingChallengeTestResult {
  id: string
  name: string
  category: string
  input_display: string
  expected_display: string
  actual_display: string
  passed: boolean
  runtime_ms: number
  error: string | null
}

export interface TargetedDefenceQuestion {
  id: string
  kind?: 'code_question' | 'live_modification'
  dimension: string
  dimension_label: string
  anchor: string
  target_file?: string
  target_symbol?: string
  target_lines?: string
  code_snippet?: string
  raw_snippet?: string
  starter_snippet?: string
  modification_prompt?: string
  ask_follow_up?: boolean
  timer_seconds?: number
  citations: string[]
  text: string
  follow_up: string
  good_answer_mentions: string[]
  why_selected: string
  suggested_outline: string
}

export interface TailoredFollowUpResponse {
  should_ask_follow_up: boolean
  examiner_context_note: string
  follow_up_question: string
  code_diff: string
  timer_seconds: number
}

export interface LiveModificationReportItem {
  question_id: string
  target_file: string
  target_lines: string
  prompt: string
  starter_code: string
  modified_code: string
  was_modified: boolean
  explanation: string
}

export interface CodingChallenge {
  challenge_id: string
  archetype: string
  title: string
  difficulty: string
  language: string
  function_name: string
  target_file: string
  target_symbol: string
  target_lines: string
  secondary_file: string
  secondary_symbol: string
  secondary_lines: string
  reference_code: string
  problem_statement: string
  constraints: string[]
  starter_code: string
  reference_solution?: string
  solution_hint: string
  test_cases: CodingChallengeTestCase[]
  targeted_questions: TargetedDefenceQuestion[]
}

export interface CodingChallengeRunResult {
  passed_count: number
  total_count: number
  all_passed: boolean
  runtime_ms: number
  compile_error: string | null
  stdout: string
  stderr: string
  test_results: CodingChallengeTestResult[]
  targeted_questions: TargetedDefenceQuestion[]
}

export interface CodingChallengeReportSummary {
  challenge_id: string
  title: string
  function_name: string
  target_file: string
  target_lines: string
  submitted_code: string
  passed_count: number
  total_count: number
  all_passed: boolean
  runtime_ms: number
  test_results: CodingChallengeTestResult[]
}

export interface AssessmentReport {
  status: string
  reviewer: string | null
  disclaimer: string
  conversation_id: string
  round: number
  grader: string
  grader_note: string
  dimensions: GradedDimension[]
  total: number | null
  max_total: number
  pass_totals: [number, number]
  needs_human_review: boolean
  review_reasons: string[]
  student_words: number
  stacked_question_turns: number
  coding_challenge?: CodingChallengeReportSummary
  live_modifications?: LiveModificationReportItem[]
}

export interface AssessmentReportResponse {
  submission_id: string
  round_no: number
  report: AssessmentReport
  transcript: {
    conversation_id?: string
    turns?: Array<{
      speaker: 'examiner' | 'student'
      text: string
      kind?: string
      question_id?: string | null
    }>
    stats?: {
      examiner_turns: number
      multi_question_rejections: number
      follow_up_fallbacks: number
      model_follow_ups: number
      repeats: number
      passes: number
      feedback_requests: number
      ended_early: boolean
    }
  }
  stages: PipelineStageRow[]
  markdown: string
}
