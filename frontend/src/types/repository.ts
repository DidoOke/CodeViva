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
  sha256: string
  is_text: boolean
  line_count: number
  metadata_json: Record<string, unknown>
}

export interface RepositoryResponse {
  repository: RepositorySummary
  job: AnalysisJob
}
