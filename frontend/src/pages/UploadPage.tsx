import { useRef } from 'react'
import type { AnalysisJob, RepositorySummary } from '../types/repository'
import { AppShell } from '../components/layout/AppShell'
import { LandingHero } from '../components/sections/LandingHero'
import { SubmissionPanel } from '../components/sections/SubmissionPanel'
import { IngestionFlow } from '../components/sections/IngestionFlow'
import { FuturePlatformStrip } from '../components/sections/FuturePlatformStrip'

interface UploadPageProps {
  onRepositoryCreated: (repository: RepositorySummary, job: AnalysisJob) => void
}

export function UploadPage({ onRepositoryCreated }: UploadPageProps) {
  const githubInputRef = useRef<HTMLInputElement | null>(null)

  function focusUploadWorkspace() {
    const el = document.getElementById('workspace-upload')
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    setTimeout(() => {
      githubInputRef.current?.focus()
    }, 250)
  }

  return (
    <AppShell
      currentStep="upload"
      onPrimaryAction={focusUploadWorkspace}
    >
      <LandingHero onFocusUpload={focusUploadWorkspace} />
      <SubmissionPanel
        onRepositoryCreated={onRepositoryCreated}
        inputRef={githubInputRef}
      />
      <IngestionFlow />
      <FuturePlatformStrip onFocusUpload={focusUploadWorkspace} />
    </AppShell>
  )
}
