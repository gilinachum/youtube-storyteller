import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getFileDownloadUrl } from '../api'

const FILE_ICON_MAP: Record<string, string> = {
  pdf: '📕',
  pptx: '📊',
  ppt: '📊',
  doc: '📄',
  docx: '📄',
  txt: '📄',
  md: '📄',
}

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif'])

function isImageFile(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return IMAGE_EXTENSIONS.has(ext)
}

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return FILE_ICON_MAP[ext] || '📁'
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
      const parts = f.key.replace(/^s3:\/\/[^/]+\//, '').split('/')
      const sessionId = parts.length >= 3 ? parts[2] : ''
      const fileIdMatch = parts[parts.length - 1]?.match(/^([a-f0-9]+)-/)
      const fileId = fileIdMatch ? fileIdMatch[1] : ''
      if (sessionId && fileId) {
        const url = await getFileDownloadUrl(sessionId, fileId, email || '')
        window.open(url, '_blank')
      }
    } catch {
      // Fallback: can't download
    }
  }

  // Separate images from documents
  const imageFiles = files.filter(f => isImageFile(f.filename))
  const docFiles = files.filter(f => !isImageFile(f.filename))

  return (
    <div>
      {cleanText && <p>{cleanText}</p>}
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
        // Parse S3 key: uploads/{email}/{session_id}/{file_id}-{filename}
        const rawKey = file.key.replace(/^s3:\/\/[^/]+\//, '')
        const parts = rawKey.split('/')
        // Expected: ['uploads', email, session_id, 'file_id-filename']
        if (parts.length >= 4 && parts[0] === 'uploads') {
          const sessionId = parts[2]
          const fileIdMatch = parts[3]?.match(/^([a-f0-9]+)-/)
          const fileId = fileIdMatch ? fileIdMatch[1] : ''
          if (sessionId && fileId) {
            const downloadUrl = await getFileDownloadUrl(sessionId, fileId, email)
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

/** Custom markdown renderers — turns S3 presigned download links into file cards */
const markdownComponents: Components = {
  a({ href, children }) {
    // Detect S3 presigned download links
    if (href && (href.includes('.s3.') || href.includes('s3.amazonaws.com')) && href.includes('X-Amz-Signature')) {
      // Extract filename from URL path
      const urlPath = new URL(href).pathname
      const filename = decodeURIComponent(urlPath.split('/').pop() || 'document')
        .replace(/^[a-f0-9]{8}-/, '') // strip file_id prefix
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
  email?: string
}

export default function ChatMessages({ messages, loading, loadingText, progressLabel, streamingContent, email }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const isStickRef = useRef(true)

  // Track if user is near the bottom (within 150px)
  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const threshold = 150
    isStickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  }, [])

  // Auto-scroll only if user hasn't scrolled up
  useEffect(() => {
    if (isStickRef.current) {
      // Use instant scroll during streaming to avoid smooth animation conflicts
      const el = containerRef.current
      if (el) {
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
      {messages.map(msg => (
        <div
          key={msg.id}
        >
          <div className={`${msg.role === 'user' ? 'message-bubble message-user' : 'message-assistant px-1 py-2 max-w-[90%]'}`}>
            {msg.role === 'user' ? (
              <UserMessage content={msg.content} email={email} />
            ) : (
              <div className="prose-rtl">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{msg.content}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      ))}

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

      {/* Progress indicator during streaming — animated bouncing dots */}
      {progressLabel && !loading && (
        <div>
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl px-4 py-2 text-gray-400 text-sm flex items-center gap-2">
            <div className="flex gap-0.5">
              <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span>{progressLabel}</span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
