import type { AnalysisJob, CodeChunk, RepositoryFile, RepositorySummary } from '../types/repository'

export const trustPrinciples = [
  {
    eyebrow: 'Principle 01',
    title: 'Evidence over accusation',
    description:
      'CodeViva never produces an "AI-written probability" or automatic misconduct charge. It verifies whether the student can explain, trace, and modify their own code.',
    pill: 'No AI detector score',
    pillBg: '#f6d5b8',
  },
  {
    eyebrow: 'Principle 02',
    title: 'Grounded repository context',
    description:
      'Every viva question, trace challenge, and debugging prompt is anchored to actual files, line ranges, and symbols extracted during repository ingestion.',
    pill: 'Verified file references',
    pillBg: '#e6f3fe',
  },
  {
    eyebrow: 'Principle 03',
    title: 'Educator-in-the-loop control',
    description:
      'Lecturers define learning outcomes and inspect traceable evidence reports—confirming, amending, or escalating every suggested assessment judgement.',
    pill: 'Human review required',
    pillBg: '#ffb110',
  },
]

export const ingestionStages = [
  {
    id: 'intake',
    code: '01',
    stageKey: 'cloning',
    label: 'Repository intake & isolation',
    statusPill: 'Intake',
    pillColor: '#e6f3fe',
    pillText: '#0075de',
    description:
      'Accepts a public GitHub URL or local ZIP snapshot, normalizes the project root, and strips transient build/virtualenv artifacts.',
  },
  {
    id: 'mapping',
    code: '02',
    stageKey: 'indexing',
    label: 'Structural & symbol mapping',
    statusPill: 'Mapping',
    pillColor: '#ffb110',
    pillText: '#000000',
    description:
      'Identifies dominant languages, top-level modules, candidate entrypoints, source vs. test coverage, and SHA-256 file fingerprints.',
  },
  {
    id: 'context',
    code: '03',
    stageKey: 'completed',
    label: 'Retrieval-ready code chunking',
    statusPill: 'Grounded',
    pillColor: '#f6d5b8',
    pillText: '#000000',
    description:
      'Slices source, test, and config files into overlapping line-indexed chunks stored in PostgreSQL for grounded viva question generation.',
  },
]

export const assessmentDimensions = [
  {
    dimension: 'Code navigation',
    evidence: 'Locates and explains relevant modules, entrypoints, and architectural boundaries',
    status: 'Complete',
    pillBg: '#e6f3fe',
    pillText: '#0075de',
  },
  {
    dimension: 'Control & data flow',
    evidence: 'Traces execution paths and predicts state transitions on concrete inputs',
    status: 'In progress',
    pillBg: '#ffb110',
    pillText: '#000000',
  },
  {
    dimension: 'Design reasoning',
    evidence: 'Justifies data structure choices, complexity trade-offs, and abstractions',
    status: 'Grounded',
    pillBg: '#f6d5b8',
    pillText: '#000000',
  },
  {
    dimension: 'Live modification',
    evidence: 'Safely extends or debugs the submitted implementation under constraints',
    status: 'To do',
    pillBg: '#f64932',
    pillText: '#ffffff',
  },
]

export const partnerMarks = [
  'Reply AI on Campus',
  'FastAPI Ingestion Engine',
  'PostgreSQL + pgvector',
  'Python AST & Chunking',
  'Adaptive Viva Defence',
  'Educator Evidence Reports',
]

export const sampleRepositoryData: {
  repository: RepositorySummary
  job: AnalysisJob
  files: RepositoryFile[]
  chunks: CodeChunk[]
} = {
  repository: {
    id: 101,
    source_type: 'github',
    display_name: 'chess-endgame-trainer',
    status: 'completed',
    github_url: 'https://github.com/student-showcase/chess-endgame-trainer',
    original_filename: null,
    detected_languages: ['python', 'markdown', 'yaml'],
    summary_json: {
      file_count: 8,
      code_file_count: 5,
      test_file_count: 2,
      top_level_directories: ['src', 'tests', 'docs', 'configs'],
      entrypoints: ['src/main.py', 'src/app.py'],
      dominant_languages: ['python', 'markdown'],
    },
    created_at: '2026-11-07T15:30:00Z',
    updated_at: '2026-11-07T15:30:12Z',
  },
  job: {
    id: 201,
    repository_id: 101,
    status: 'completed',
    stage: 'completed',
    error_message: null,
    started_at: '2026-11-07T15:30:01Z',
    finished_at: '2026-11-07T15:30:12Z',
  },
  files: [
    {
      id: 1,
      relative_path: 'src/main.py',
      file_type: 'source',
      language: 'python',
      size_bytes: 2840,
      sha256: '9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e',
      is_text: true,
      line_count: 84,
      metadata_json: { suffix: '.py', name: 'main.py' },
    },
    {
      id: 2,
      relative_path: 'src/engine/minimax.py',
      file_type: 'source',
      language: 'python',
      size_bytes: 4620,
      sha256: '3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b',
      is_text: true,
      line_count: 142,
      metadata_json: { suffix: '.py', name: 'minimax.py' },
    },
    {
      id: 3,
      relative_path: 'src/engine/board_state.py',
      file_type: 'source',
      language: 'python',
      size_bytes: 3910,
      sha256: '7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d',
      is_text: true,
      line_count: 118,
      metadata_json: { suffix: '.py', name: 'board_state.py' },
    },
    {
      id: 4,
      relative_path: 'src/engine/heuristics.py',
      file_type: 'source',
      language: 'python',
      size_bytes: 2150,
      sha256: '1f2e3d4c5b6a79808172635445362718293a4b5c6d7e8f90a1b2c3d4e5f6a7b8',
      is_text: true,
      line_count: 68,
      metadata_json: { suffix: '.py', name: 'heuristics.py' },
    },
    {
      id: 5,
      relative_path: 'src/app.py',
      file_type: 'source',
      language: 'python',
      size_bytes: 1980,
      sha256: '5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e',
      is_text: true,
      line_count: 62,
      metadata_json: { suffix: '.py', name: 'app.py' },
    },
    {
      id: 6,
      relative_path: 'tests/test_minimax.py',
      file_type: 'test',
      language: 'python',
      size_bytes: 2490,
      sha256: '8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c',
      is_text: true,
      line_count: 76,
      metadata_json: { suffix: '.py', name: 'test_minimax.py' },
    },
    {
      id: 7,
      relative_path: 'tests/test_board_state.py',
      file_type: 'test',
      language: 'python',
      size_bytes: 1820,
      sha256: '2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d',
      is_text: true,
      line_count: 54,
      metadata_json: { suffix: '.py', name: 'test_board_state.py' },
    },
    {
      id: 8,
      relative_path: 'README.md',
      file_type: 'docs',
      language: 'markdown',
      size_bytes: 1640,
      sha256: '4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f',
      is_text: true,
      line_count: 48,
      metadata_json: { suffix: '.md', name: 'README.md' },
    },
  ],
  chunks: [
    {
      id: 501,
      repository_file_id: 2,
      chunk_index: 0,
      chunk_type: 'code',
      start_line: 1,
      end_line: 45,
      content: `from typing import Optional, Tuple
from src.engine.board_state import BoardState
from src.engine.heuristics import evaluate_position

def alphabeta_search(
    state: BoardState,
    depth: int,
    alpha: float = float("-inf"),
    beta: float = float("inf"),
    maximizing_player: bool = True,
) -> Tuple[float, Optional[str]]:
    """
    Depth-limited minimax search with alpha-beta pruning
    and transposition table lookup.
    """
    if depth == 0 or state.is_terminal():
        return evaluate_position(state), None

    best_move: Optional[str] = None
    legal_moves = state.get_ordered_moves()

    if maximizing_player:
        value = float("-inf")
        for move in legal_moves:
            child_state = state.apply_move(move)
            score, _ = alphabeta_search(child_state, depth - 1, alpha, beta, False)
            if score > value:
                value, best_move = score, move
            alpha = max(alpha, value)
            if alpha >= beta:
                break  # Beta cutoff
        return value, best_move`,
      metadata_json: {
        path: 'src/engine/minimax.py',
        language: 'python',
      },
    },
    {
      id: 502,
      repository_file_id: 3,
      chunk_index: 0,
      chunk_type: 'code',
      start_line: 1,
      end_line: 38,
      content: `from dataclasses import dataclass, field
from typing import Dict, List

@dataclass(frozen=True)
class BoardState:
    pieces: Dict[str, str]
    side_to_move: str = "W"
    move_history: Tuple[str, ...] = field(default_factory=tuple)

    def get_ordered_moves(self) -> List[str]:
        """
        Orders candidate moves using MVV-LVA (Most Valuable Victim -
        Least Valuable Attacker) so alpha-beta cutoffs happen earlier.
        """
        captures = [m for m in self.generate_legal_moves() if "x" in m]
        quiet = [m for m in self.generate_legal_moves() if "x" not in m]
        return captures + quiet`,
      metadata_json: {
        path: 'src/engine/board_state.py',
        language: 'python',
      },
    },
    {
      id: 503,
      repository_file_id: 6,
      chunk_index: 0,
      chunk_type: 'test',
      start_line: 1,
      end_line: 34,
      content: `import pytest
from src.engine.board_state import BoardState
from src.engine.minimax import alphabeta_search

def test_mate_in_two_krk_endgame():
    """Verify engine finds forced rook-and-king mate in 2 plies."""
    state = BoardState(
        pieces={"e1": "WK", "a7": "WR", "e8": "BK"},
        side_to_move="W",
    )
    score, best_move = alphabeta_search(state, depth=4, maximizing_player=True)
    assert best_move == "Ra8#"
    assert score > 9000`,
      metadata_json: {
        path: 'tests/test_minimax.py',
        language: 'python',
      },
    },
    {
      id: 504,
      repository_file_id: 1,
      chunk_index: 0,
      chunk_type: 'code',
      start_line: 1,
      end_line: 32,
      content: `import argparse
from src.engine.board_state import BoardState
from src.engine.minimax import alphabeta_search

def run_cli_session(fen: str, depth: int = 4) -> None:
    board = BoardState.from_fen(fen)
    score, move = alphabeta_search(board, depth=depth)
    print(f"[CodeViva Target] Recommended continuation: {move} (eval={score:.2f})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chess Endgame Trainer")
    parser.add_argument("--fen", required=True)
    parser.add_argument("--depth", type=int, default=4)
    args = parser.parse_args()
    run_cli_session(args.fen, args.depth)`,
      metadata_json: {
        path: 'src/main.py',
        language: 'python',
      },
    },
  ],
}
