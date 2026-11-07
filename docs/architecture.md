# CodeViva Initial Architecture

## Goal

Build the first slice of CodeViva: a clean upload-first product that ingests a repository, analyses it quickly, and stores retrieval-ready context for later assessment generation.

This phase does **not** implement the assessment engine yet. It focuses on:

1. A polished landing page
2. Repository ingestion by ZIP upload or GitHub URL
3. Fast structural analysis
4. Storage of codebase metadata and chunks for later retrieval
5. Reviewable analysis status and outputs

## Product scope for this phase

### Student-facing flow

1. Open the landing page
2. Paste a GitHub link or upload a ZIP archive
3. Start analysis
4. See an analysis progress screen
5. Review a simple summary of what was extracted

### System scope

- Accept GitHub repository URLs
- Accept ZIP file uploads
- Unpack and normalise the repository
- Build a file inventory
- Extract lightweight code structure
- Chunk code and documentation for retrieval
- Store analysis outputs in a database
- Expose the results via API

## Stack

### Frontend
- **React** with **Vite**
- TypeScript
- Minimal, Apple-inspired UI system
- No heavy component library required for v1

### Backend
- **FastAPI**
- Python 3.12
- Async API endpoints
- Background task support for ingestion jobs

### Storage
- **PostgreSQL** with **pgvector**

Why this is the right choice:
- Structured relational data for repositories, files, jobs, and analyses
- Good support for JSON metadata
- Easy path to embeddings and retrieval later through pgvector
- Better long-term fit than SQLite for queued jobs + retrieval + growth

### Containerization
- **Docker Compose** for local development
- Services:
  - frontend
  - backend
  - postgres

## High-level architecture

```text
React frontend
    ↓
FastAPI backend
    ↓
Ingestion service
    ├─ GitHub clone/download
    ├─ ZIP extraction
    ├─ File discovery
    ├─ Lightweight static analysis
    ├─ Chunking
    └─ Persistence
    ↓
PostgreSQL + pgvector
```

## Initial database model

### repositories
Stores one submitted codebase.

Fields:
- id
- source_type (`github` | `upload`)
- github_url
- original_filename
- display_name
- status (`pending` | `processing` | `completed` | `failed`)
- detected_languages
- root_path
- summary_json
- created_at
- updated_at

### repository_files
Stores discovered files.

Fields:
- id
- repository_id
- relative_path
- file_type
- language
- size_bytes
- sha256
- is_text
- line_count
- metadata_json

### code_chunks
Stores retrieval-ready chunks.

Fields:
- id
- repository_id
- repository_file_id
- chunk_index
- chunk_type (`code` | `readme` | `config` | `test`)
- start_line
- end_line
- content
- embedding (`vector`, optional in this phase)
- metadata_json

### analysis_jobs
Tracks ingestion runs.

Fields:
- id
- repository_id
- status
- stage
- error_message
- started_at
- finished_at

## Ingestion pipeline design

### Step 1: intake
If source is GitHub:
- validate the URL
- download repository archive or clone shallowly

If source is upload:
- save ZIP file
- extract safely into a workspace directory

### Step 2: normalization
- identify project root
- ignore irrelevant directories (`.git`, `node_modules`, `dist`, `build`, `venv`, `__pycache__`)
- cap file size for analysis
- classify text vs binary

### Step 3: file inventory
For each text file:
- capture relative path
- detect language by extension
- hash file
- count lines
- label probable role: source, test, config, docs

### Step 4: fast structural analysis
Start with lightweight heuristics only:
- detect dominant languages
- identify entrypoints (`main.py`, `package.json`, `app.py`, etc.)
- extract imports
- extract function and class names where easy
- detect test files
- detect README/docs presence
- detect framework hints

This should be intentionally fast and deterministic.

### Step 5: chunking for retrieval
- chunk source files by line windows with overlap
- chunk docs separately
- preserve path and line metadata
- mark important chunks such as tests, configs, and core modules

### Step 6: repository summary
Build a basic summary object:
- repository name
- dominant language(s)
- number of files
- number of code files
- number of test files
- probable frameworks
- likely entrypoints
- top-level directories

### Step 7: persist and expose
Store:
- repository record
- file records
- chunk records
- summary JSON
- job status

## API surface for v1

### `POST /api/repositories/upload`
Upload a ZIP file and create an analysis job.

### `POST /api/repositories/github`
Submit a GitHub URL and create an analysis job.

### `GET /api/repositories/{repository_id}`
Return repository metadata and summary.

### `GET /api/repositories/{repository_id}/status`
Return current analysis status.

### `GET /api/repositories/{repository_id}/files`
Return discovered files.

### `GET /api/repositories/{repository_id}/chunks`
Return chunk metadata for debugging.

## UI direction

Use a restrained Apple-inspired style:
- bright background
- soft greys
- crisp typography
- subtle borders and shadows
- a single strong accent color
- one primary CTA on screen

### Initial screens

1. **Landing page**
   - headline
   - short value proposition
   - GitHub link field
   - ZIP upload dropzone
   - single “Analyse codebase” action

2. **Analysis progress page**
   - progress stages
   - status pill
   - detected source

3. **Repository summary page**
   - languages
   - file count
   - framework hints
   - top files
   - analysis-ready confirmation

## Notes on voice and video recording

For later sponsored-track coverage:
- store metadata for future media sessions now in a way that won’t block current design
- do not build voice/video capture in this phase
- keep repository and future assessment sessions as separate concepts in the data model

## Development priorities

1. Ship the upload-first UI
2. Ship repository ingestion endpoints
3. Store file and chunk data reliably
4. Show analysis results in the frontend
5. Leave embeddings and assessment generation for the next slice
