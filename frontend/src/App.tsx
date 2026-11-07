import { useEffect, useState } from 'react'

import {
  fetchRepository,
  fetchRepositoryChunks,
  fetchRepositoryFiles,
  fetchRepositoryStatus,
} from './api/client'
import type { FlowStep } from './components/layout/AppShell'
import { AssessmentResultsPage } from './pages/AssessmentResultsPage'
import { AssessmentTestPage } from './pages/AssessmentTestPage'
import { RepositoryPage } from './pages/RepositoryPage'
import { UploadPage } from './pages/UploadPage'
import type {
  AnalysisJob,
  AssessmentPlanResponse,
  AssessmentReportResponse,
  CodeChunk,
  RepositoryFile,
  RepositorySummary,
} from './types/repository'
import './App.css'

function App() {
  const [currentStep, setCurrentStep] = useState<FlowStep>('upload')
  const [repository, setRepository] = useState<RepositorySummary | null>(null)
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const [files, setFiles] = useState<RepositoryFile[]>([])
  const [chunks, setChunks] = useState<CodeChunk[]>([])
  const [assessmentPlan, setAssessmentPlan] = useState<AssessmentPlanResponse | null>(null)
  const [assessmentReport, setAssessmentReport] = useState<AssessmentReportResponse | null>(null)

  useEffect(() => {
    if (!repository || !job) return

    let isCancelled = false

    async function hydrateRepository(repoId: number) {
      try {
        const [latestRepository, latestJob, latestFiles, latestChunks] = await Promise.all([
          fetchRepository(repoId),
          fetchRepositoryStatus(repoId),
          fetchRepositoryFiles(repoId),
          fetchRepositoryChunks(repoId).catch(() => [] as CodeChunk[]),
        ])
        if (!isCancelled) {
          setRepository(latestRepository)
          setJob(latestJob)
          setFiles(latestFiles)
          setChunks(latestChunks)
        }
      } catch (loadError) {
        console.error('Failed to hydrate repository results', loadError)
      }
    }

    hydrateRepository(repository.id)

    const isDone = repository.status === 'completed' || job.status === 'completed' || job.status === 'failed'
    if (!isDone) {
      const interval = window.setInterval(() => {
        hydrateRepository(repository.id)
      }, 1800)
      return () => {
        isCancelled = true
        window.clearInterval(interval)
      }
    }

    return () => {
      isCancelled = true
    }
  }, [repository?.id, repository?.status, job?.status])

  function handleRepositoryCreated(newRepo: RepositorySummary, newJob: AnalysisJob) {
    setRepository(newRepo)
    setJob(newJob)
    setFiles([])
    setChunks([])
    setAssessmentPlan(null)
    setAssessmentReport(null)
    setCurrentStep('repository')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function handleStartAssessment() {
    setCurrentStep('assessment')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function handleCompleteAssessment(
    report: AssessmentReportResponse,
    plan: AssessmentPlanResponse | null,
  ) {
    setAssessmentReport(report)
    if (plan) {
      setAssessmentPlan(plan)
    }
    setCurrentStep('results')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function handleNavigateStep(step: FlowStep) {
    if (step === 'upload') {
      handleReset()
      return
    }
    if (step === 'results' && !assessmentReport) {
      return
    }
    setCurrentStep(step)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function handleReset() {
    setRepository(null)
    setJob(null)
    setFiles([])
    setChunks([])
    setAssessmentPlan(null)
    setAssessmentReport(null)
    setCurrentStep('upload')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (repository && job) {
    if (currentStep === 'results' && assessmentReport) {
      return (
        <AssessmentResultsPage
          repository={repository}
          reportData={assessmentReport}
          planData={assessmentPlan}
          onNavigateStep={handleNavigateStep}
          onRetakeAssessment={() => {
            setCurrentStep('assessment')
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
          onReset={handleReset}
        />
      )
    }

    if (currentStep === 'assessment') {
      return (
        <AssessmentTestPage
          repository={repository}
          onCompleteAssessment={handleCompleteAssessment}
          onNavigateStep={handleNavigateStep}
          onReset={handleReset}
        />
      )
    }

    return (
      <RepositoryPage
        repository={repository}
        job={job}
        files={files}
        chunks={chunks}
        hasResults={Boolean(assessmentReport)}
        onReset={handleReset}
        onStartAssessment={handleStartAssessment}
        onNavigateStep={handleNavigateStep}
      />
    )
  }

  return <UploadPage onRepositoryCreated={handleRepositoryCreated} />
}

export default App
