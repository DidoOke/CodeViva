import type { AnalysisJob, RepositoryFile, RepositoryResponse, RepositorySummary } from '../types/repository'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || 'Request failed')
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
