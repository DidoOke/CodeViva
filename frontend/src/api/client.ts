import type {
  AnalysisJob,
  AssessmentPlanResponse,
  AssessmentReportResponse,
  AssessmentStatus,
  CodeChunk,
  CodingChallenge,
  CodingChallengeRunResult,
  InterviewSessionState,
  RepositoryFile,
  RepositoryResponse,
  RepositorySummary,
} from '../types/repository'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const raw = await response.text()
    try {
      const parsed = JSON.parse(raw) as { detail?: string }
      if (parsed.detail) {
        throw new Error(parsed.detail)
      }
    } catch (parseErr) {
      if (parseErr instanceof Error && parseErr.message !== raw && !raw.startsWith('{')) {
        // Not JSON
      } else if (parseErr instanceof Error && !parseErr.message.includes('JSON')) {
        throw parseErr
      }
    }
    throw new Error(raw || 'Request failed')
  }
  return response.json() as Promise<T>
}

export async function submitGithubRepository(githubUrl: string): Promise<RepositoryResponse> {
  const response = await fetch(`${API_BASE}/repositories/github`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ github_url: githubUrl }),
  })

  return handleResponse<RepositoryResponse>(response)
}

export async function submitZipRepository(file: File): Promise<RepositoryResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE}/repositories/upload`, {
    method: 'POST',
    body: formData,
  })

  return handleResponse<RepositoryResponse>(response)
}

export async function fetchRepository(repositoryId: number): Promise<RepositorySummary> {
  const response = await fetch(`${API_BASE}/repositories/${repositoryId}`)
  return handleResponse<RepositorySummary>(response)
}

export async function fetchRepositoryStatus(repositoryId: number): Promise<AnalysisJob> {
  const response = await fetch(`${API_BASE}/repositories/${repositoryId}/status`)
  return handleResponse<AnalysisJob>(response)
}

export async function fetchRepositoryFiles(repositoryId: number): Promise<RepositoryFile[]> {
  const response = await fetch(`${API_BASE}/repositories/${repositoryId}/files`)
  return handleResponse<RepositoryFile[]>(response)
}

export async function fetchRepositoryChunks(repositoryId: number): Promise<CodeChunk[]> {
  const response = await fetch(`${API_BASE}/repositories/${repositoryId}/chunks`)
  return handleResponse<CodeChunk[]>(response)
}

/* ==========================================================================
   Assessment & Grading Loop API Calls
   ========================================================================== */

export async function fetchAssessmentStatus(): Promise<AssessmentStatus> {
  const response = await fetch(`${API_BASE}/assessment/status`)
  return handleResponse<AssessmentStatus>(response)
}

export async function buildAssessmentPlan(
  repositoryId: number,
  options: {
    use_llm?: boolean
    round_no?: number
    max_questions?: number
    demo_submission_id?: string | null
  } = {}
): Promise<AssessmentPlanResponse> {
  const response = await fetch(`${API_BASE}/assessment/repositories/${repositoryId}/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      use_llm: options.use_llm ?? true,
      round_no: options.round_no ?? 1,
      max_questions: options.max_questions ?? 5,
      demo_submission_id: options.demo_submission_id ?? null,
    }),
  })
  return handleResponse<AssessmentPlanResponse>(response)
}

export async function startAssessmentInterview(
  repositoryId: number,
  options: {
    use_llm?: boolean
    round_no?: number
    demo_submission_id?: string | null
  } = {}
): Promise<InterviewSessionState> {
  const response = await fetch(`${API_BASE}/assessment/repositories/${repositoryId}/interview/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      use_llm: options.use_llm ?? true,
      round_no: options.round_no ?? 1,
      demo_submission_id: options.demo_submission_id ?? null,
    }),
  })
  return handleResponse<InterviewSessionState>(response)
}

export async function pollAssessmentInterview(
  sessionId: string,
  after: number = 0
): Promise<{
  session_id: string
  submission_id: string
  round_no: number
  messages: Array<{ speaker: 'examiner' | 'student'; text: string }>
  total_messages: number
  done: boolean
  error: string
}> {
  const response = await fetch(`${API_BASE}/assessment/interview/${sessionId}?after=${after}`)
  return handleResponse(response)
}

export async function sendInterviewAnswer(
  sessionId: string,
  text: string
): Promise<{
  ok: boolean
  messages: Array<{ speaker: 'examiner' | 'student'; text: string }>
  done: boolean
  error: string
}> {
  const response = await fetch(`${API_BASE}/assessment/interview/${sessionId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  return handleResponse(response)
}

export async function runAutoDemoInterviewAndGrade(
  repositoryId: number,
  options: {
    use_llm?: boolean
    round_no?: number
    demo_submission_id?: string | null
  } = {}
): Promise<AssessmentReportResponse> {
  const response = await fetch(`${API_BASE}/assessment/repositories/${repositoryId}/auto-grade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      use_llm: options.use_llm ?? true,
      round_no: options.round_no ?? 1,
      demo_submission_id: options.demo_submission_id ?? null,
    }),
  })
  return handleResponse<AssessmentReportResponse>(response)
}

export async function fetchAssessmentReport(
  repositoryId: number,
  roundNo: number = 1,
  demoSubmissionId?: string | null
): Promise<AssessmentReportResponse> {
  const params = new URLSearchParams({ round_no: String(roundNo) })
  if (demoSubmissionId) {
    params.set('demo_submission_id', demoSubmissionId)
  }
  const response = await fetch(`${API_BASE}/assessment/repositories/${repositoryId}/report?${params.toString()}`)
  return handleResponse<AssessmentReportResponse>(response)
}

export async function fetchCodingChallenge(repositoryId: number): Promise<CodingChallenge> {
  const response = await fetch(`${API_BASE}/assessment/repositories/${repositoryId}/coding-challenge`)
  return handleResponse<CodingChallenge>(response)
}

export async function runCodingChallenge(
  repositoryId: number,
  code: string
): Promise<CodingChallengeRunResult> {
  const response = await fetch(`${API_BASE}/assessment/repositories/${repositoryId}/coding-challenge/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  return handleResponse<CodingChallengeRunResult>(response)
}

export async function submitCodingChallengeAndDefence(
  repositoryId: number,
  payload: {
    code: string
    answers: Array<{
      question_id: string
      answer: string
      follow_up_answer?: string
    }>
    use_llm?: boolean
    round_no?: number
  }
): Promise<AssessmentReportResponse> {
  const response = await fetch(
    `${API_BASE}/assessment/repositories/${repositoryId}/coding-challenge/submit-defence`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: payload.code,
        answers: payload.answers,
        use_llm: payload.use_llm ?? true,
        round_no: payload.round_no ?? 1,
      }),
    }
  )
  return handleResponse<AssessmentReportResponse>(response)
}
