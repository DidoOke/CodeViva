import { useEffect, useState } from 'react'

import { fetchRepository, fetchRepositoryFiles, fetchRepositoryStatus } from './api/client'
import { RepositoryPage } from './pages/RepositoryPage'
import { UploadPage } from './pages/UploadPage'
import type { AnalysisJob, RepositoryFile, RepositorySummary } from './types/repository'
import './App.css'

function App() {
  const [repository, setRepository] = useState<RepositorySummary | null>(null)
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const [files, setFiles] = useState<RepositoryFile[]>([])

  useEffect(() => {
    async function hydrateRepository() {
      if (!repository || !job) return
      const [latestRepository, latestJob, latestFiles] = await Promise.all([
        fetchRepository(repository.id),
        fetchRepositoryStatus(repository.id),
        fetchRepositoryFiles(repository.id),
      ])
      setRepository(latestRepository)
      setJob(latestJob)
      setFiles(latestFiles)
    }

    if (repository && job) {
      hydrateRepository().catch((error) => {
        console.error('Failed to hydrate repository results', error)
      })
    }
  }, [repository?.id])

  if (repository && job) {
    return (
      <RepositoryPage
        repository={repository}
        job={job}
        files={files}
        onReset={() => {
          setRepository(null)
          setJob(null)
          setFiles([])
        }}
      />
    )
  }

  return (
    <UploadPage
      onRepositoryCreated={(createdRepository, createdJob) => {
        setRepository(createdRepository)
        setJob(createdJob)
      }}
    />
  )
}

export default App
