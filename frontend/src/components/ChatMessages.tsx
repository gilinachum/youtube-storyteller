import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getFileDownloadUrl } from '../api'
import MediaImage from './MediaImage'
import { InteractiveForm, parseInteractiveBlocks } from './interactive'

const FILE_ICON_MAP: Record<string, string> = {
  pdf: '📕',
  pptx: '📊',
  ppt: '📊',
  doc: '📄',
  docx: '📄',
  txt: '📄',
  md: '📄',
  png: '🖼️',
  jpg: '🖼️',
  jpeg: '🖼️',
  webp: '🖼️',
  gif: '🖼️',
}

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif'])

function isImageFile(filename: string): boolean {
  const lower = filename.toLowerCase()
  const ext = lower.split('.').pop() || ''
  // Also check if filename starts with an image extension (e.g. "jpg.153508_20260319")
  const firstPart = lower.split('.')[0] || ''
  return IMAGE_EXTENSIONS.has(ext) || IMAGE_EXTENSIONS.has(firstPart)
}

function getFileIcon(filename: string): string {
  const lower = filename.toLowerCase()
  const ext = lower.split('.').pop() || ''
  const firstPart = lower.split('.')[0] || ''
  return FILE_ICON_MAP[ext] || FILE_ICON_MAP[firstPart] || '📁'
}

/** Parse user message content — render file attachment refs as styled cards, images as previews */
function UserMessage({ content, email }: { content: string; email?: string }) {
  // Match [קובץ מצורף: filename (s3_key)] or 📎 filename patterns
  const fileRefRegex = /\[קובץ מצורף: (.+?) \((?:s3:\/\/)?(.+?)\)\]/g
  const clipRegex = /\n?📎 .+/g

  // Extract file refs
  const files: { filename: string; key: string }[] = []
  let match
  while ((match = fileRefRegex.exec(content)) !== null) {
    files.push({ filename: match[1], key: match[2] })
  }

  // Get the clean text (remove file ref lines and 📎 lines)
  let cleanText = content
    .replace(fileRefRegex, '')
    .replace(clipRegex, '')
    .trim()

  // Helper to get a download URL and open/display the file
  const handleFileClick = async (f: { filename: string; key: string }) => {
    try {
      // Key format: uploads/{email}/{session_id}/{file_id}-{filename}
      // In message: s3://uploads/{email}/{session_id}/{file_id}-{filename}
      // Strip only the s3:// protocol prefix (no bucket — 'uploads' IS the first folder)
      const rawKey = f.key.replace(/^s3:\/\//, '')
      const parts = rawKey.split('/')
      // Expected: ['uploads', email, session_id, '{file_id}-{filename}']
      const uploadsIdx = parts.indexOf('uploads')
      if (uploadsIdx >= 0 && parts.length >= uploadsIdx + 4) {
        const sessionId = parts[uploadsIdx + 2]
        const fileIdMatch = parts[uploadsIdx + 3]?.match(/^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-/)
        const fileId = fileIdMatch ? fileIdMatch[1] : ''
        if (sessionId && fileId) {
          const url = await getFileDownloadUrl(sessionId, fileId)
          window.open(url, '_blank')
          return
        }
      }
      console.warn('Could not parse file key for download:', f.key)
    } catch (err) {
      console.error('File download failed:', err)
    }
  }

  // Separate images from documents
  const imageFiles = files.filter(f => isImageFile(f.filename))
  const docFiles = files.filter(f => !isImageFile(f.filename))

  return (
    <div>
      {cleanText && <p className="whitespace-pre-wrap">{cleanText}</p>}
      {/* Image previews */}
      {imageFiles.length > 0 && (
        <div className={`flex flex-wrap gap-2 ${cleanText ? 'mt-2' : ''}`}>
          {imageFiles.map((f, i) => (
            <ImagePreview key={i} file={f} email={email || ''} onClick={() => handleFileClick(f)} />
          ))}
        </div>
      )}
      {/* Document file cards */}
      {docFiles.length > 0 && (
        <div className={`flex flex-col gap-1.5 ${cleanText || imageFiles.length > 0 ? 'mt-2' : ''}`}>
          {docFiles.map((f, i) => (
            <a
              key={i}
              href="#"
              onClick={async (e) => {
                e.preventDefault()
                await handleFileClick(f)
              }}
              className="flex items-center gap-2 bg-white/10 hover:bg-white/15 transition-colors rounded-lg px-3 py-2 text-sm cursor-pointer"
            >
              <span className="text-base">{getFileIcon(f.filename)}</span>
              <span className="truncate max-w-[200px] text-white/90">{f.filename}</span>
              <span className="text-white/50 mr-auto text-xs">⬇</span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

/** Lazy-loading image preview — uses download API for uploaded files */
function ImagePreview({ file, email, onClick }: { file: { filename: string; key: string }; email: string; onClick: () => void }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const attempted = useRef(false)

  useEffect(() => {
    if (attempted.current) return
    attempted.current = true
    ;(async () => {
      try {
        // Key format: uploads/{email}/{session_id}/{file_id}-{filename}
        // In message: s3://uploads/... — strip only s3:// protocol
        const rawKey = file.key.replace(/^s3:\/\//, '')
        const parts = rawKey.split('/')
        const uploadsIdx = parts.indexOf('uploads')
        if (uploadsIdx >= 0 && parts.length >= uploadsIdx + 4) {
          const sessionId = parts[uploadsIdx + 2]
          const fileIdMatch = parts[uploadsIdx + 3]?.match(/^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-/)
          const fileId = fileIdMatch ? fileIdMatch[1] : ''
          if (sessionId && fileId) {
            const downloadUrl = await getFileDownloadUrl(sessionId, fileId)
            setUrl(downloadUrl)
            return
          }
        }
        setError(true)
      } catch {
        setError(true)
      }
    })()
  }, [file, email])

  if (error) {
    return (
      <div
        onClick={onClick}
        className="flex items-center gap-2 bg-white/10 rounded-lg px-3 py-2 text-sm cursor-pointer"
      >
        <span className="text-base">🖼️</span>
        <span className="truncate max-w-[200px] text-white/90">{file.filename}</span>
      </div>
    )
  }

  if (!url) {
    return (
      <div className="w-32 h-24 rounded-lg bg-gray-700 animate-pulse" />
    )
  }

  return (
    <img
      src={url}
      alt={file.filename}
      onClick={onClick}
      className="rounded-lg max-w-[200px] max-h-[150px] object-cover border border-white/20 cursor-pointer hover:border-brand-400 transition-colors"
      loading="lazy"
    />
  )
}

/** Custom markdown renderers — file:// links become on-demand download cards */
function makeMarkdownComponents(sessionId?: string): Components {
  return {
  a({ href, children }) {
    // Detect file:// download references (on-demand presigned URL)
    if (href && href.startsWith('file://')) {
      const fileId = href.replace('file://', '')
      const text = typeof children === 'string' ? children : (Array.isArray(children) ? children.join('') : '')
      // Extract filename — strip leading emoji if present
      const filename = text.replace(/^[\u{1F4C4}\u{1F4C1}\u{1F4CE}\u{1F4D1}]\s*/u, '') || 'document'
      const ext = filename.split('.').pop()?.toLowerCase() || ''
      const icon = FILE_ICON_MAP[ext] || '\ud83d\udcc1'

      const handleClick = async (e: React.MouseEvent) => {
        e.preventDefault()
        if (!sessionId || !fileId) return
        try {
          const url = await getFileDownloadUrl(sessionId, fileId)
          window.open(url, '_blank')
        } catch (err) {
          console.error('File download failed:', err)
        }
      }

      return (
        <a
          href="#"
          onClick={handleClick}
          className="flex items-center gap-2 bg-white/10 hover:bg-white/15 transition-colors rounded-lg px-3 py-2 text-sm no-underline my-2 max-w-[280px] cursor-pointer"
        >
          <span className="text-xl flex-shrink-0">{icon}</span>
          <span className="truncate text-white/90">{filename}</span>
          <span className="text-white/50 mr-auto text-xs">\u2b07</span>
        </a>
      )
    }

    // Legacy: detect S3 presigned download links (for old messages)
    if (href && (href.includes('.s3.') || href.includes('s3.amazonaws.com')) && href.includes('X-Amz-Signature')) {
      const urlPath = new URL(href).pathname
      const filename = decodeURIComponent(urlPath.split('/').pop() || 'document')
        .replace(/^[a-f0-9]{8}-/, '')
      const ext = filename.split('.').pop()?.toLowerCase() || ''
      const icon = FILE_ICON_MAP[ext] || '\ud83d\udcc1'

      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 bg-white/10 hover:bg-white/15 transition-colors rounded-lg px-3 py-2 text-sm no-underline my-2 max-w-[280px]"
        >
          <span className="text-xl flex-shrink-0">{icon}</span>
          <span className="truncate text-white/90">{filename}</span>
          <span className="text-white/50 mr-auto text-xs">\u2b07</span>
        </a>
      )
    }

    // Regular links
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-400 underline">
        {children}
      </a>
    )
  },
  // Render tables with horizontal scroll and styling
  table({ children }) {
    return (
      <div className="overflow-x-auto my-3 rounded-lg border border-gray-700">
        <table className="min-w-full text-sm border-collapse">{children}</table>
      </div>
    )
  },
  th({ children }) {
    return <th className="bg-gray-800 px-3 py-2 text-right font-medium text-gray-300 border-b border-gray-700">{children}</th>
  },
  td({ children }) {
    return <td className="px-3 py-2 text-right border-b border-gray-800">{children}</td>
  },
  // Render thumbnail/inline images with proper styling
  img({ src, alt }) {
    // Detect media:// protocol — resolve via presigned URL
    if (src && src.startsWith('media://')) {
      const fileId = src.replace('media://', '')
      console.log(`[ChatMessages:img] Rendering MediaImage for fileId=${fileId}, sessionId=${sessionId}`)
      return <MediaImage fileId={fileId} alt={alt || 'image'} sessionId={sessionId || ''} />
    }
    console.log(`[ChatMessages:img] Rendering regular img, src=${src?.substring(0, 50)}`)
    return (
      <div className="my-3">
        <img
          src={src}
          alt={alt || 'thumbnail'}
          className="rounded-lg max-w-full border border-gray-700 shadow-lg"
          style={{ maxHeight: '400px', objectFit: 'contain' }}
          loading="lazy"
        />
        {alt && alt !== 'thumbnail' && (
          <p className="text-xs text-gray-400 mt-1">{alt}</p>
        )}
      </div>
    )
  },
  }
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

interface Props {
  messages: Message[]
  loading: boolean
  loadingText?: string
  progressLabel?: string
  streamingContent?: string
  isStreaming?: boolean
  email?: string
  sessionId?: string
  onSendMessage?: (message: string) => void
  onPendingFormChange?: (pending: string | null) => void
}

export default function ChatMessages({ messages, loading, loadingText, progressLabel, streamingContent, isStreaming, email, sessionId, onSendMessage, onPendingFormChange }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const isStickRef = useRef(true)
  // Tracks the previous scrollTop so we can detect user-initiated upward scrolls
  const prevScrollTopRef = useRef(0)
  // Track which interactive blocks have been responded to
  const [respondedBlocks, setRespondedBlocks] = useState<Set<string>>(new Set())

  // Memoize parsed interactive blocks — keyed by message content to avoid re-parsing on every render
  const parsedMessages = useMemo(() => {
    const map = new Map<string, ReturnType<typeof parseInteractiveBlocks>>()
    for (const msg of messages) {
      if (msg.role === 'assistant') {
        map.set(msg.id, parseInteractiveBlocks(msg.content))
      }
    }
    return map
  }, [messages])

  const markdownComponents = useMemo(() => makeMarkdownComponents(sessionId), [sessionId])

  // Disable auto-scroll the moment the user scrolls up (any amount).
  // Re-enable only when they scroll back within 150 px of the bottom.
  // This prevents fast streaming from snapping the user back before they
  // can scroll more than the old 150 px threshold.
  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const threshold = 150
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    const scrolledUp = el.scrollTop < prevScrollTopRef.current
    prevScrollTopRef.current = el.scrollTop
    if (scrolledUp) {
      isStickRef.current = false
    } else if (atBottom) {
      isStickRef.current = true
    }
  }, [])

  // Auto-scroll only if user hasn't scrolled up
  useEffect(() => {
    if (isStickRef.current) {
      const el = containerRef.current
      if (el) {
        // Pre-update prevScrollTopRef so the resulting scroll event isn't
        // mistaken for a user-initiated upward scroll.
        prevScrollTopRef.current = el.scrollHeight
        el.scrollTop = el.scrollHeight
      }
    }
  }, [messages, loading, streamingContent])

  // Always scroll to bottom when user sends a new message
  useEffect(() => {
    const lastMsg = messages[messages.length - 1]
    if (lastMsg?.role === 'user') {
      isStickRef.current = true
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length])

  return (
    <div ref={containerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6 space-y-4">
      {messages.map((msg, msgIndex) => {
        // Use memoized parsed interactive blocks
        const isAssistant = msg.role === 'assistant'
        const parsed = isAssistant ? parsedMessages.get(msg.id) || null : null
        const textToRender = parsed ? parsed.textContent : msg.content
        // A block is "responded" if there's a user message after this assistant message
        const hasUserReplyAfter = isAssistant && msgIndex < messages.length - 1 &&
          messages[msgIndex + 1]?.role === 'user'

        return (
        <div
          key={msg.id}
        >
          <div className={`${msg.role === 'user' ? 'message-bubble message-user' : 'message-assistant px-1 py-2 max-w-[90%]'}`}>
            {msg.role === 'user' ? (
              <UserMessage content={msg.content} email={email} />
            ) : (
              <div className="prose-rtl">
                <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={(url) => url} components={markdownComponents}>{textToRender}</ReactMarkdown>
                {/* Render interactive blocks */}
                {parsed && parsed.blocks.length > 0 && (
                  <InteractiveForm
                    blocks={parsed.blocks}
                    disabled={hasUserReplyAfter || loading}
                    respondedBlocks={respondedBlocks}
                    onSubmit={(answers) => {
                      if (onSendMessage && !loading) {
                        const blockIds = parsed.blocks.map(b => b.id)
                        setRespondedBlocks(prev => new Set([...prev, ...blockIds]))
                        onSendMessage(answers)
                      }
                    }}
                    onPendingChange={onPendingFormChange}
                  />
                )}
              </div>
            )}
          </div>
        </div>
        )
      })}

      {/* Loading indicator — before any streaming content arrives */}
      {loading && (
        <div>
          <div className="message-assistant px-1 py-2">
            <div className="flex items-center gap-2 text-gray-400">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm">{loadingText || 'חוקר ומנתח...'}</span>
            </div>
          </div>
        </div>
      )}

      {/* Persistent activity indicator during streaming — always shows animated dots */}
      {/* Appears below the streaming message so user knows it's still working */}
      {isStreaming && !loading && (
        <div>
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl px-4 py-2 text-gray-400 text-sm flex items-center gap-2">
            <div className="flex gap-0.5">
              <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="animate-pulse">{progressLabel || 'עובד על זה...'}</span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
