import type { AnalysisJob, CodeChunk, RepositoryFile, RepositorySummary } from '../types/repository'
import { AppShell, type FlowStep } from '../components/layout/AppShell'
import { IngestionProgress } from '../components/sections/IngestionProgress'
import { RepositoryInsights } from '../components/sections/RepositoryInsights'

interface RepositoryPageProps {
  repository: RepositorySummary
  job: AnalysisJob
  files: RepositoryFile[]
  chunks?: CodeChunk[]
  hasResults?: boolean
  onReset: () => void
  onStartAssessment: () => void
  onNavigateStep: (step: FlowStep) => void
}

export function RepositoryPage({
  repository,
  job,
  files,
  chunks = [],
  hasResults = false,
  onReset,
  onStartAssessment,
  onNavigateStep,
}: RepositoryPageProps) {
  const isComplete = repository.status === 'completed' || job.status === 'completed'

  return (
    <AppShell
      currentStep="repository"
      repositoryName={repository.display_name}
      hasResults={hasResults}
      onNavigateStep={onNavigateStep}
      onResetRepo={onReset}
      onPrimaryAction={isComplete ? onStartAssessment : undefined}
    >
      {!isComplete ? (
        <IngestionProgress repository={repository} job={job} onReset={onReset} />
      ) : (
        <RepositoryInsights
          repository={repository}
          job={job}
          files={files}
          chunks={chunks}
          onReset={onReset}
          onStartAssessment={onStartAssessment}
        />
      )}
    </AppShell>
  )
}
