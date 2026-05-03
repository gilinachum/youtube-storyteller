// API client — supports both local (email in query) and Cognito (JWT) auth.
//
// In Cognito mode, the ID token is sent as an Authorization header and the
// API Gateway Cognito authorizer validates it. The email comes from the token.

const API_BASE = '/api'

import { getAuth, getAuthHeader, AUTH_MODE } from './auth'

function email(): string {
  return getAuth()?.email || ''
}

/** Build headers with optional Authorization for Cognito mode. */
async function authHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  const headers: Record<string, string> = { ...extra }
  const token = await getAuthHeader()
  if (token) headers['Authorization'] = token
  return headers
}

/** Build URL with email param for local mode, plain URL for Cognito. */
function withEmail(url: string): string {
  if (AUTH_MODE === 'cognito') return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}email=${encodeURIComponent(email())}`
}

export interface Session {
  email: string
  session_id: string
  name: string
  created_at: string
  updated_at: string
  shared_with?: string[]
  _shared?: boolean
  _shared_by?: string
}

export interface Message {
  session_id: string
  timestamp: string
  role: 'user' | 'assistant'
  content: string
}

export interface UploadResponse {
  upload_url: string
  key: string
  file_id: string
}

export interface FileRecord {
  file_id: string
  filename: string
  s3_key: string
  content_type: string
  uploaded_at: string
}

export async function listSessions(): Promise<Session[]> {
  const headers = await authHeaders()
  const res = await fetch(withEmail(`${API_BASE}/sessions`), { headers })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Failed to load sessions')
  return data.sessions || []
}

export async function deleteSession(sessionId: string): Promise<void> {
  const headers = await authHeaders()
  const res = await fetch(withEmail(`${API_BASE}/sessions/${sessionId}`), {
    method: 'DELETE', headers,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Failed to delete session')
}

export async function getSessionMessages(sessionId: string): Promise<{ messages: Message[]; files: FileRecord[]; shared_with: string[] }> {
  const headers = await authHeaders()
  const res = await fetch(withEmail(`${API_BASE}/sessions/${sessionId}`), { headers })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Failed to load session')
  return {
    messages:    data.messages    || [],
    files:       data.files       || [],
    shared_with: data.shared_with || [],
  }
}

export async function shareSession(sessionId: string, shareWith: string): Promise<void> {
  const headers = await authHeaders({ 'Content-Type': 'application/json' })
  const body: Record<string, string> = { share_with: shareWith }
  if (AUTH_MODE === 'local') body.email = email()
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/share`, {
    method: 'POST', headers, body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Share failed')
}

export async function getFileDownloadUrl(sessionId: string, fileId: string): Promise<string> {
  const headers = await authHeaders()
  const res = await fetch(withEmail(`${API_BASE}/sessions/${sessionId}/files/${fileId}`), { headers })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Download failed')
  return data.download_url
}

export async function requestUploadUrl(
  sessionId: string, filename: string, contentType: string
): Promise<UploadResponse> {
  const headers = await authHeaders({ 'Content-Type': 'application/json' })
  const body: Record<string, string> = { session_id: sessionId, filename, content_type: contentType }
  if (AUTH_MODE === 'local') body.email = email()
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST', headers, body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Upload request failed')
  return data
}

export async function uploadFile(sessionId: string, file: File): Promise<{ key: string; filename: string; file_id: string }> {
  const { upload_url, key, file_id } = await requestUploadUrl(
    sessionId, file.name, file.type || 'application/octet-stream'
  )
  await fetch(upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
    body: file,
  })
  return { key, filename: file.name, file_id }
}

// ── Streaming chat via AgentCore Runtime ────────────────────────────────────

export interface StreamChatOptions {
  email: string
  message: string
  sessionId: string
  fileRefs?: Array<{ filename: string; s3_key: string }>
  onChunk: (text: string) => void
  onDone: (fullText: string) => void
  onError: (error: Error) => void
  signal?: AbortSignal
}

export async function streamChat(opts: StreamChatOptions): Promise<void> {
  const { email, message, sessionId, fileRefs, onChunk, onDone, onError, signal } = opts

  try {
    const headers = await authHeaders({ 'Content-Type': 'application/json' })
    const body: Record<string, unknown> = {
      message,
      session_id: sessionId,
      file_refs: fileRefs || [],
    }
    if (AUTH_MODE === 'local') body.email = email

    const res = await fetch(`${API_BASE}/chat-stream`, {
      method: 'POST', headers,
      body: JSON.stringify(body),
      signal,
    })

    if (!res.ok) {
      const errBody = await res.text()
      throw new Error(`Stream request failed (${res.status}): ${errBody}`)
    }
    if (!res.body) throw new Error('No response body — streaming not supported')

    const reader  = res.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      fullText += chunk
      onChunk(chunk)
    }
    const remaining = decoder.decode()
    if (remaining) { fullText += remaining; onChunk(remaining) }
    onDone(fullText)
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') return
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}

export async function transcribeAudio(audioBlob: Blob, sessionId: string): Promise<{ text: string; language: string }> {
  const buffer = await audioBlob.arrayBuffer()
  const bytes  = new Uint8Array(buffer)
  let binary = ''
  const chunkSize = 8192
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize))
  }
  const base64 = btoa(binary)

  const headers = await authHeaders({ 'Content-Type': 'application/json' })
  const body: Record<string, string> = { session_id: sessionId, audio: base64 }
  if (AUTH_MODE === 'local') body.email = email()

  const startRes = await fetch(`${API_BASE}/transcribe`, {
    method: 'POST', headers, body: JSON.stringify(body),
  })

  if (!startRes.ok) {
    const err = await startRes.json().catch(() => ({ error: 'Transcription failed' }))
    throw new Error(err.error || 'Failed to start transcription')
  }
  const { job_name } = await startRes.json()

  const pollHeaders = await authHeaders()
  const maxAttempts = 60
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000))
    const pollRes = await fetch(`${API_BASE}/transcribe/${encodeURIComponent(job_name)}`, { headers: pollHeaders })
    if (!pollRes.ok) continue
    const result = await pollRes.json()
    if (result.status === 'COMPLETED') return { text: result.text, language: result.language }
    if (result.status === 'FAILED')    throw new Error(result.error || 'Transcription failed')
  }
  throw new Error('Transcription timed out')
}
