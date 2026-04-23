// API configuration — set via environment variable at build time
const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

import { getValidIdToken } from './cognito'

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

// List sessions for a user
export async function listSessions(email: string): Promise<Session[]> {
  const res = await fetch(`${API_BASE}/sessions?email=${encodeURIComponent(email)}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Failed to load sessions')
  return data.sessions || []
}

// Get messages + files for a session
export async function getSessionMessages(sessionId: string, email?: string): Promise<{ messages: Message[]; files: FileRecord[]; shared_with: string[] }> {
  const params = email ? `?email=${encodeURIComponent(email)}` : ''
  const res = await fetch(`${API_BASE}/sessions/${sessionId}${params}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Failed to load session')
  return {
    messages: data.messages || [],
    files: data.files || [],
    shared_with: data.shared_with || [],
  }
}

// Share a session with another user
export async function shareSession(email: string, sessionId: string, shareWith: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, share_with: shareWith }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Share failed')
}

// Get a download URL for a file
export async function getFileDownloadUrl(sessionId: string, fileId: string, email: string): Promise<string> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/files/${fileId}?email=${encodeURIComponent(email)}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Download failed')
  return data.download_url
}

// Request a presigned upload URL
export async function requestUploadUrl(
  email: string,
  sessionId: string,
  filename: string,
  contentType: string
): Promise<UploadResponse> {
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, session_id: sessionId, filename, content_type: contentType }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Upload request failed')
  return data
}

// Upload a file to S3 via presigned URL, then record in DB
export async function uploadFile(
  email: string,
  sessionId: string,
  file: File
): Promise<{ key: string; filename: string; file_id: string }> {
  // 1. Get presigned URL
  const { upload_url, key, file_id } = await requestUploadUrl(
    email, sessionId, file.name, file.type || 'application/octet-stream'
  )
  // 2. Upload to S3
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

/**
 * Stream a chat response from AgentCore Runtime via API Gateway.
 * Uses ReadableStream to display chunks as they arrive.
 * Falls back to the polling pattern if streaming fails.
 */
export async function streamChat(opts: StreamChatOptions): Promise<void> {
  const { email, message, sessionId, fileRefs, onChunk, onDone, onError, signal } = opts

  try {
    const idToken = await getValidIdToken()

    const res = await fetch(`${API_BASE}/chat-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`,
      },
      body: JSON.stringify({
        email,
        message,
        session_id: sessionId,
        file_refs: fileRefs || [],
      }),
      signal,
    })

    if (!res.ok) {
      const errBody = await res.text()
      throw new Error(`Stream request failed (${res.status}): ${errBody}`)
    }

    if (!res.body) {
      throw new Error('No response body — streaming not supported')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      fullText += chunk
      onChunk(chunk)
    }

    // Flush any remaining partial UTF-8
    const remaining = decoder.decode()
    if (remaining) {
      fullText += remaining
      onChunk(remaining)
    }

    onDone(fullText)
  } catch (err: any) {
    if (err.name === 'AbortError') return
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}

/**
 * Send audio blob to server for transcription via Amazon Transcribe.
 * Returns the transcribed text.
 */
export async function transcribeAudio(audioBlob: Blob, email: string, sessionId: string): Promise<{ text: string; language: string }> {
  // Convert blob to base64
  const buffer = await audioBlob.arrayBuffer()
  const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)))

  const res = await fetch(`${API_BASE}/transcribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      session_id: sessionId,
      audio: base64,
    }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Transcription failed' }))
    throw new Error(err.error || 'Transcription failed')
  }

  return res.json()
}
