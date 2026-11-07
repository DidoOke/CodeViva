/**
 * Text-to-speech and speech-to-text for the voice examiner.
 *
 * Uses the backend (/api/speech, ElevenLabs) when it has a key configured, and falls back to
 * the browser's built-in Web Speech API otherwise — or when a server call fails at runtime.
 *
 *   await speak('Walk me through your insert function.')
 *   const session = await startListening({ onInterim: (t) => setLive(t) })
 *   const { text } = await session.stop()
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

export type SpeechEngine = 'server' | 'browser'

export interface SpeechCapabilities {
  tts: SpeechEngine | null
  stt: SpeechEngine | null
}

export interface TranscriptWord {
  text: string
  start: number | null
  end: number | null
  type: string
  speaker_id: string | null
}

export interface TranscriptResult {
  text: string
  engine: SpeechEngine
  language_code?: string | null
  words?: TranscriptWord[] // word timings: server engine only
}

export interface SpeakOptions {
  voiceId?: string // server engine
  lang?: string // browser engine, e.g. 'en-GB'
  rate?: number // browser engine, 0.1–10
  signal?: AbortSignal // abort to stop speaking
}

export interface ListenOptions {
  lang?: string // e.g. 'en-GB'
  onInterim?: (text: string) => void // live transcript (browser engine only)
}

export interface ListeningSession {
  engine: SpeechEngine
  stop(): Promise<TranscriptResult>
  cancel(): void
}

// ---------------------------------------------------------------------------
// Capability detection

let serverStatus: Promise<{ tts: boolean; stt: boolean }> | null = null

function fetchServerStatus() {
  serverStatus ??= fetch(`${API_BASE}/speech/status`)
    .then((r) => (r.ok ? r.json() : { tts: false, stt: false }))
    .catch(() => ({ tts: false, stt: false }))
  return serverStatus
}

/** Forget the cached server status, e.g. after the backend gets a key. */
export function resetSpeechStatus() {
  serverStatus = null
}

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

const browserTts = () => typeof window !== 'undefined' && 'speechSynthesis' in window
const browserStt = () => typeof window !== 'undefined' && getRecognitionCtor() !== null
const canRecord = () => typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

export async function getSpeechCapabilities(): Promise<SpeechCapabilities> {
  const server = await fetchServerStatus()
  return {
    tts: server.tts ? 'server' : browserTts() ? 'browser' : null,
    stt: server.stt && canRecord() ? 'server' : browserStt() ? 'browser' : null,
  }
}

// ---------------------------------------------------------------------------
// Text-to-speech

export async function speak(text: string, options: SpeakOptions = {}): Promise<SpeechEngine> {
  const { tts } = await getSpeechCapabilities()
  if (tts === 'server') {
    try {
      await speakWithServer(text, options)
      return 'server'
    } catch (error) {
      if (options.signal?.aborted) throw error
      if (!browserTts()) throw error
      console.warn('Server TTS failed, falling back to browser speech', error)
    }
  }
  if (!browserTts()) throw new Error('Text-to-speech is not available in this browser.')
  await speakWithBrowser(text, options)
  return 'browser'
}

async function speakWithServer(text: string, { voiceId, signal }: SpeakOptions) {
  const response = await fetch(`${API_BASE}/speech/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice_id: voiceId }),
    signal,
  })
  if (!response.ok) throw new Error((await response.text()) || `TTS failed (${response.status})`)

  const url = URL.createObjectURL(await response.blob())
  const audio = new Audio(url)
  try {
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        audio.pause()
        reject(new DOMException('Aborted', 'AbortError'))
      }
      signal?.addEventListener('abort', onAbort, { once: true })
      audio.onended = () => resolve()
      audio.onerror = () => reject(new Error('Audio playback failed'))
      audio.play().catch(reject)
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}

function speakWithBrowser(text: string, { lang = 'en-GB', rate = 0.95, signal }: SpeakOptions) {
  return new Promise<void>((resolve, reject) => {
    const synth = window.speechSynthesis
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = lang
    utterance.rate = rate // slightly slow: calmer for an exam setting
    const voice = pickVoice(synth.getVoices(), lang)
    if (voice) utterance.voice = voice

    signal?.addEventListener(
      'abort',
      () => {
        synth.cancel()
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
    utterance.onend = () => resolve()
    utterance.onerror = (e) => (e.error === 'interrupted' || e.error === 'canceled' ? resolve() : reject(new Error(e.error)))
    synth.cancel() // one question at a time: never stack utterances
    synth.speak(utterance)
  })
}

function pickVoice(voices: SpeechSynthesisVoice[], lang: string) {
  const base = lang.split('-')[0]
  const matching = voices.filter((v) => v.lang === lang || v.lang.startsWith(base))
  // Prefer higher-quality system voices where the browser exposes them.
  return (
    matching.find((v) => /natural|neural|enhanced|premium|google/i.test(v.name)) ??
    matching.find((v) => v.localService) ??
    matching[0] ??
    null
  )
}

// ---------------------------------------------------------------------------
// Speech-to-text

export async function startListening(options: ListenOptions = {}): Promise<ListeningSession> {
  const { stt } = await getSpeechCapabilities()
  if (stt === 'server') return startServerListening(options)
  if (stt === 'browser') return startBrowserListening(options)
  throw new Error('Speech recognition is not available in this browser. Try Chrome or Edge, or type your answer.')
}

async function startServerListening(options: ListenOptions): Promise<ListeningSession> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const recorder = new MediaRecorder(stream)
  const chunks: Blob[] = []
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  recorder.start()

  const release = () => stream.getTracks().forEach((t) => t.stop())

  return {
    engine: 'server',
    cancel() {
      if (recorder.state !== 'inactive') recorder.stop()
      release()
    },
    async stop() {
      await new Promise<void>((resolve) => {
        recorder.onstop = () => resolve()
        if (recorder.state !== 'inactive') recorder.stop()
        else resolve()
      })
      release()

      const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
      const ext = blob.type.includes('mp4') ? 'mp4' : blob.type.includes('ogg') ? 'ogg' : 'webm'
      const form = new FormData()
      form.append('file', blob, `answer.${ext}`)
      if (options.lang) form.append('language_code', options.lang.split('-')[0])

      const response = await fetch(`${API_BASE}/speech/stt`, { method: 'POST', body: form })
      if (!response.ok) throw new Error((await response.text()) || `Transcription failed (${response.status})`)
      const body = await response.json()
      return { ...body, engine: 'server' }
    },
  }
}

function startBrowserListening({ lang = 'en-GB', onInterim }: ListenOptions): ListeningSession {
  const Ctor = getRecognitionCtor()!
  const recognition = new Ctor()
  recognition.lang = lang
  recognition.continuous = true
  recognition.interimResults = true

  let finalText = ''
  let interimText = ''
  let stopping = false
  let fatalError: string | null = null
  let finish: (() => void) | null = null

  recognition.onresult = (event) => {
    interimText = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i]
      if (result.isFinal) finalText += result[0].transcript + ' '
      else interimText += result[0].transcript
    }
    onInterim?.((finalText + interimText).trim())
  }
  recognition.onerror = (event) => {
    // 'no-speech' just means a silent stretch; students need long silence tolerance.
    if (event.error !== 'no-speech' && event.error !== 'aborted') fatalError = event.error
  }
  recognition.onend = () => {
    // Browsers end recognition on their own after silence; keep listening until stop().
    if (!stopping && !fatalError) {
      try {
        recognition.start()
        return
      } catch {
        /* fall through and finish */
      }
    }
    finish?.()
  }
  recognition.start()

  return {
    engine: 'browser',
    cancel() {
      stopping = true
      recognition.abort()
    },
    stop() {
      stopping = true
      return new Promise<TranscriptResult>((resolve, reject) => {
        finish = () => {
          if (fatalError && !finalText.trim()) reject(new Error(`Speech recognition failed: ${fatalError}`))
          else resolve({ text: (finalText + interimText).trim(), engine: 'browser' })
        }
        recognition.stop()
      })
    },
  }
}

// ---------------------------------------------------------------------------
// Minimal Web Speech API typings (not in TypeScript's DOM lib).

interface SpeechRecognitionAlternativeLike {
  transcript: string
}
interface SpeechRecognitionResultLike {
  isFinal: boolean
  [index: number]: SpeechRecognitionAlternativeLike
}
interface SpeechRecognitionEventLike {
  resultIndex: number
  results: { length: number; [index: number]: SpeechRecognitionResultLike }
}
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike
