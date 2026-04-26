import { useState, useCallback, useEffect, useRef } from 'react'
import { streamChat, listSessions, getSessionMessages, uploadFile, shareSession, getFileDownloadUrl, transcribeAudio } from '../api'
import type { Session, FileRecord } from '../api'
import ChatMessages from './ChatMessages'
import ChatInput from './ChatInput'
import type { UploadedFile } from './ChatInput'
import Sidebar from './Sidebar'
import ShareModal from './ShareModal'
import FileList from './FileList'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

interface Props {
  email: string
  onLogout: () => void
}

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  role: 'assistant',
  content: `אני StoryTeller — העוזר שלך לתכנון סרטוני YouTube בעברית.

**מה אני יכול לעשות בשבילך?**

🔗 **לנתח חומר גלם** — תן לי URL, PDF, או PPTX ואני אהפוך אותו לתכנית סרטון

📈 **לחקור טרנדים** — אגלה מה עובד ביוטיוב עכשיו בנושא שלך

✍️ **לכתוב אאוטליין או סקריפט מלא** — בעברית, מותאם לשימור צופים מקסימלי

🎨 **לעצב תמונת טאמבנייל** — תמונות מעוצבות לסרטון עם עיצוב איטרטיבי

🎯 **לייעץ על כותרות ו-SEO** — כדי שהסרטון יגיע לכמה שיותר אנשים

על מה הסרטון הבא שלך? 🚀`,
  timestamp: Date.now(),
}

export default function Chat({ email, onLogout }: Props) {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE])
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => {
    // Restore last active session or create new
    const saved = localStorage.getItem(`storyteller-last-session-${email}`)
    return saved || crypto.randomUUID()
  })
  const [loading, setLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [progressLabel, setProgressLabel] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sessionFiles, setSessionFiles] = useState<FileRecord[]>([])
  const [showShareModal, setShowShareModal] = useState(false)
  const [showFiles, setShowFiles] = useState(false)
  const [sharedWith, setSharedWith] = useState<string[]>([])
  const [isSharedSession, setIsSharedSession] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Persist current session ID
  useEffect(() => {
    localStorage.setItem(`storyteller-last-session-${email}`, currentSessionId)
  }, [email, currentSessionId])

  // Load sessions on mount + restore last session
  useEffect(() => {
    listSessions(email).then(sessions => {
      setSessions(sessions)
      // If we have a saved session ID, load its messages
      const savedId = localStorage.getItem(`storyteller-last-session-${email}`)
      if (savedId && sessions.some(s => s.session_id === savedId)) {
        getSessionMessages(savedId, email)
          .then(data => {
            if (data.messages && data.messages.length > 0) {
              const loaded: Message[] = data.messages.map((m: any, i: number) => ({
                id: `restored-${i}`,
                role: m.role as 'user' | 'assistant',
                content: m.content,
                timestamp: new Date(m.timestamp).getTime(),
              }))
              setMessages([{ ...WELCOME_MESSAGE, id: 'welcome', timestamp: 0 }, ...loaded])
              setCurrentSessionId(savedId)
              if (data.files) setSessionFiles(data.files)
              if (data.shared_with) setSharedWith(data.shared_with)
            }
          })
          .catch(console.error)
      }
    }).catch(console.error)
  }, [email])

  // Auto-recover on tab focus — reload session messages if stream was interrupted
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && !loading) {
        // Reload current session messages to get the full response
        getSessionMessages(currentSessionId, email)
          .then(data => {
            if (data.messages && data.messages.length > 0) {
              const loaded: Message[] = data.messages.map((m: any, i: number) => ({
                id: `loaded-${i}`,
                role: m.role as 'user' | 'assistant',
                content: m.content,
                timestamp: new Date(m.timestamp).getTime(),
              }))
              // Only update if server has more messages than we have (excluding welcome)
              const currentNonWelcome = messages.filter(m => m.id !== 'welcome')
              if (loaded.length > currentNonWelcome.length) {
                setMessages([{ ...WELCOME_MESSAGE, id: 'welcome', timestamp: 0 }, ...loaded])
              }
            }
          })
          .catch(() => { /* silent — best effort */ })
        // Also refresh session list
        listSessions(email).then(setSessions).catch(console.error)
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [email, currentSessionId, loading, messages])

  const handleSend = useCallback(async (text: string, files?: UploadedFile[]) => {
    // Build file refs for the agent
    const fileRefs = files?.map(f => ({ filename: f.filename, s3_key: f.key })) || []

    let fullMessage = text
    if (files && files.length > 0) {
      const fileList = files.map(f => `[קובץ מצורף: ${f.filename} (s3://${f.key})]`).join('\n')
      fullMessage = fullMessage ? `${fullMessage}\n\n${fileList}` : fileList
    }

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: fullMessage,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    setStreamingContent('')

    // Create abort controller for this request
    const controller = new AbortController()
    abortControllerRef.current = controller

    const streamingMsgId = crypto.randomUUID()

    await streamChat({
      email,
      message: fullMessage,
      sessionId: currentSessionId,
      fileRefs,
      signal: controller.signal,
      onChunk: (chunk) => {
        // Strip keepalive markers before processing
        const cleaned = chunk.replace(/__KEEPALIVE__/g, '')
        if (!cleaned) return  // Pure keepalive chunk — skip

        // Raw chunk from ReadableStream — accumulate for SSE parsing
        setStreamingContent(prev => prev + cleaned)

        // Scan for progress events in the new chunk
        // Progress events now come as: __PROGRESS__{"type":"progress",...}
        const prefixMatch = cleaned.match(/__PROGRESS__.*?"label":\s*"([^"]+)"/)
        if (prefixMatch) {
          setProgressLabel(prefixMatch[1])
        } else {
          // Fallback: legacy format without prefix
          const progressMatch = cleaned.match(/"type":\s*"progress".*?"label":\s*"([^"]+)"/)
          if (progressMatch) {
            setProgressLabel(progressMatch[1])
          }
        }
      },
      onDone: (fullText) => {
        // Parse the SSE data format — extract text from "data: ..." lines
        const parsedText = parseStreamData(fullText)

        const assistantMsg: Message = {
          id: streamingMsgId,
          role: 'assistant',
          content: parsedText,
          timestamp: Date.now(),
        }
        setMessages(prev => [...prev, assistantMsg])
        setLoading(false)
        setStreamingContent('')
        setProgressLabel('')
        abortControllerRef.current = null
        // Refresh sessions (immediate + delayed to catch name_session updates)
        listSessions(email).then(setSessions).catch(console.error)
        setTimeout(() => listSessions(email).then(setSessions).catch(console.error), 2000)
      },
      onError: (err) => {
        // If we have partial streaming content, save it instead of showing error
        if (streamingContent) {
          const parsedText = parseStreamData(streamingContent)
          if (parsedText.trim()) {
            const partialMsg: Message = {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: parsedText,
              timestamp: Date.now(),
            }
            setMessages(prev => [...prev, partialMsg])
            setLoading(false)
            setStreamingContent('')
            setProgressLabel('')
            abortControllerRef.current = null
            // Reload full response from server when tab regains focus
            return
          }
        }

        const errMsg: Message = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `⚠️ שגיאה: ${err.message}`,
          timestamp: Date.now(),
        }
        setMessages(prev => [...prev, errMsg])
        setLoading(false)
        setStreamingContent('')
        setProgressLabel('')
        abortControllerRef.current = null
      },
    })
  }, [email, currentSessionId])

  const handleNewChat = useCallback(() => {
    // Abort any in-flight stream
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setLoading(false)
    setStreamingContent('')
    setProgressLabel('')
    setMessages([{ ...WELCOME_MESSAGE, id: crypto.randomUUID(), timestamp: Date.now() }])
    setCurrentSessionId(crypto.randomUUID())
    setSessionFiles([])
    setSharedWith([])
    setIsSharedSession(false)
    setShowFiles(false)
  }, [])

  const handleSelectSession = useCallback(async (sessionId: string) => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setLoading(false)
    setStreamingContent('')
    setProgressLabel('')
    setCurrentSessionId(sessionId)
    setShowFiles(false)
    try {
      const { messages: msgs, files, shared_with } = await getSessionMessages(sessionId, email)
      setMessages(msgs.map(m => ({
        id: `${m.timestamp}-${m.role}`,
        role: m.role,
        content: m.content,
        timestamp: new Date(m.timestamp).getTime(),
      })))
      setSessionFiles(files)
      setSharedWith(shared_with)
      const session = sessions.find(s => s.session_id === sessionId)
      setIsSharedSession(session?._shared || false)
    } catch (err) {
      console.error('Failed to load session:', err)
    }
  }, [email, sessions])

  const handleUpload = useCallback(async (file: File): Promise<UploadedFile | null> => {
    try {
      const result = await uploadFile(email, currentSessionId, file)
      setSessionFiles(prev => [...prev, {
        file_id: result.file_id,
        filename: result.filename,
        s3_key: result.key,
        content_type: file.type,
        uploaded_at: new Date().toISOString(),
      }])
      return { key: result.key, filename: result.filename, file_id: result.file_id }
    } catch (err) {
      console.error('Upload failed:', err)
      return null
    }
  }, [email, currentSessionId])

  const handleTranscribe = useCallback(async (audioBlob: Blob): Promise<string> => {
    try {
      const result = await transcribeAudio(audioBlob, email, currentSessionId)
      return result.text || ''
    } catch (err: any) {
      console.error('Transcription failed:', err)
      const errorMsg = err?.message?.includes('timed out')
        ? 'התמלול נכשל — נסה הודעה קצרה יותר'
        : `שגיאה בתמלול: ${err?.message || 'unknown'}`
      alert(errorMsg)
      return ''
    }
  }, [email, currentSessionId])

  const handleShare = useCallback(async (shareWithEmail: string) => {
    try {
      await shareSession(email, currentSessionId, shareWithEmail)
      setSharedWith(prev => [...prev, shareWithEmail])
      setShowShareModal(false)
    } catch (err) {
      console.error('Share failed:', err)
      throw err
    }
  }, [email, currentSessionId])

  const handleFileDownload = useCallback(async (fileId: string) => {
    try {
      const url = await getFileDownloadUrl(currentSessionId, fileId, email)
      window.open(url, '_blank')
    } catch (err) {
      console.error('Download failed:', err)
    }
  }, [currentSessionId, email])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort()
    }
  }, [])

  // Compute display messages — include streaming content as a live message
  const displayMessages = streamingContent
    ? [...messages, {
        id: 'streaming',
        role: 'assistant' as const,
        content: parseStreamData(streamingContent),
        timestamp: Date.now(),
      }]
    : messages

  return (
    <div className="flex h-screen bg-gray-950" dir="rtl">
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelect={handleSelectSession}
        onNewChat={handleNewChat}
        email={email}
        onLogout={onLogout}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="border-b border-gray-800 px-4 lg:px-6 py-4 flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 transition-colors"
            title="תפריט"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          </button>
          <span className="text-2xl">🎬</span>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h1 className="font-semibold text-white">StoryTeller</h1>
              {(isSharedSession || sharedWith.length > 0) && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-brand-900/50 text-brand-300 text-xs">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3">
                    <path d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                  </svg>
                  משותפת
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500">עוזר תכנון סרטוני YouTube</p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1">
            {sessionFiles.length > 0 && (
              <button
                onClick={() => setShowFiles(!showFiles)}
                className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors relative"
                title="קבצים"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                <span className="absolute -top-1 -left-1 w-4 h-4 bg-brand-600 rounded-full text-[10px] flex items-center justify-center text-white">
                  {sessionFiles.length}
                </span>
              </button>
            )}

            <button
              onClick={() => setShowShareModal(true)}
              className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
              title="שתף שיחה"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
              </svg>
            </button>
          </div>
        </div>

        {/* Files panel */}
        {showFiles && sessionFiles.length > 0 && (
          <FileList files={sessionFiles} onDownload={handleFileDownload} />
        )}

        <ChatMessages
          messages={displayMessages}
          loading={loading && !streamingContent}
          loadingText={progressLabel || 'מתחבר לסוכן...'}
          progressLabel={streamingContent ? progressLabel : ''}
          streamingContent={streamingContent}
          email={email}
        />
        <ChatInput onSend={handleSend} disabled={loading} onUpload={handleUpload} onTranscribe={handleTranscribe} />
      </div>

      {showShareModal && (
        <ShareModal
          onShare={handleShare}
          onClose={() => setShowShareModal(false)}
          sharedWith={sharedWith}
        />
      )}
    </div>
  )
}

/**
 * Parse SSE-style "data: ..." lines from the stream into plain text.
 * Each chunk comes as: data: "quoted text"\n\n
 * The values are JSON-encoded strings.
 */
function parseStreamData(raw: string): string {
  if (!raw.includes('data: ')) return raw

  const lines = raw.split('\n')
  const textParts: string[] = []

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue
    const value = line.slice(6).trim()
    if (!value) continue

    try {
      const parsed = JSON.parse(value)
      if (typeof parsed === 'string') {
        // Check if it's a progress event (prefixed or raw JSON)
        if (parsed.startsWith('__PROGRESS__')) continue
        if (parsed === '__KEEPALIVE__') continue
        // Also catch legacy un-prefixed progress JSON that got string-wrapped
        if (parsed.includes('"type"') && parsed.includes('"progress"')) {
          try {
            const inner = JSON.parse(parsed)
            if (inner && inner.type === 'progress') continue
          } catch { /* not JSON, keep as text */ }
        }
        textParts.push(parsed)
      }
      // JSON objects (progress events, etc.) — skip silently
    } catch {
      // Not valid JSON — use raw as fallback
      textParts.push(value)
    }
  }

  return textParts.join('')
}
