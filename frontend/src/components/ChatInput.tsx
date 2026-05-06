import { useState, useRef, useMemo } from 'react'

interface Props {
  onSend: (message: string, files?: UploadedFile[]) => void
  disabled: boolean
  onUpload: (file: File) => Promise<UploadedFile | null>
  onTranscribe?: (audioBlob: Blob) => Promise<string>
}

export interface UploadedFile {
  key: string
  filename: string
  file_id: string
}

export default function ChatInput({ onSend, disabled, onUpload, onTranscribe }: Props) {
  const [text, setText] = useState('')
  const [attachedFiles, setAttachedFiles] = useState<UploadedFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const cancelledRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  // Detect text direction — RTL for Hebrew/Arabic, LTR for Latin/numbers
  const textDir = useMemo(() => {
    const trimmed = text.trimStart()
    if (!trimmed) return 'rtl' // default RTL
    // Check first meaningful character
    const firstChar = trimmed.codePointAt(0) || 0
    // Hebrew: 0x0590-0x05FF, Arabic: 0x0600-0x06FF
    if ((firstChar >= 0x0590 && firstChar <= 0x05FF) || (firstChar >= 0x0600 && firstChar <= 0x06FF)) return 'rtl'
    // Latin, digits, common punctuation → LTR
    if (firstChar >= 0x0020 && firstChar <= 0x007F) return 'ltr'
    return 'rtl'
  }, [text])

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault()
    const trimmed = text.trim()
    if ((!trimmed && attachedFiles.length === 0) || disabled) return
    onSend(trimmed, attachedFiles.length > 0 ? attachedFiles : undefined)
    setText('')
    setAttachedFiles([])
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Enter sends the message; Shift+Enter creates a new line
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const uploaded = await onUpload(file)
      if (uploaded) {
        setAttachedFiles(prev => [...prev, uploaded])
      }
    } catch (err) {
      console.error('Upload failed:', err)
    } finally {
      setUploading(false)
      // Reset input so same file can be selected again
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const removeFile = (fileId: string) => {
    setAttachedFiles(prev => prev.filter(f => f.file_id !== fileId))
  }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'
      const recorder = new MediaRecorder(stream, { mimeType })
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        // Stop all tracks
        stream.getTracks().forEach(t => t.stop())

        // If cancelled, discard the recording
        if (cancelledRef.current) {
          cancelledRef.current = false
          return
        }

        const blob = new Blob(chunksRef.current, { type: mimeType })
        if (blob.size > 0 && onTranscribe) {
          setTranscribing(true)
          try {
            const transcribedText = await onTranscribe(blob)
            if (transcribedText.trim()) {
              // Auto-send the transcribed text immediately
              onSend(transcribedText.trim())
            }
          } finally {
            setTranscribing(false)
          }
        }
      }

      recorder.start()
      mediaRecorderRef.current = recorder
      setRecording(true)
    } catch (err) {
      console.error('Microphone access denied:', err)
    }
  }

  const stopRecording = (cancel = false) => {
    if (cancel) cancelledRef.current = true
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    mediaRecorderRef.current = null
    setRecording(false)
  }

  return (
    <div className="border-t border-gray-800 bg-gray-950 px-4 py-4">
      {/* Attached files chips */}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachedFiles.map(f => (
            <div key={f.file_id} className="flex items-center gap-1.5 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-gray-300">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5 text-brand-400 flex-shrink-0">
                <path fillRule="evenodd" d="M18.97 3.659a2.25 2.25 0 00-3.182 0l-10.94 10.94a3.75 3.75 0 105.304 5.303l7.693-7.693a.75.75 0 011.06 1.06l-7.693 7.693a5.25 5.25 0 01-7.424-7.424l10.939-10.94a3.75 3.75 0 115.303 5.304L9.097 18.835l-.008.008-.007.007-.002.002-.003.002A2.25 2.25 0 015.91 15.66l7.81-7.81a.75.75 0 011.061 1.06l-7.81 7.81a.75.75 0 001.054 1.068L18.97 6.84a2.25 2.25 0 000-3.182z" clipRule="evenodd" />
              </svg>
              <span className="truncate max-w-[120px]">{f.filename}</span>
              <button
                onClick={() => removeFile(f.file_id)}
                className="text-gray-500 hover:text-gray-300 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5">
                  <path fillRule="evenodd" d="M5.47 5.47a.75.75 0 011.06 0L12 10.94l5.47-5.47a.75.75 0 111.06 1.06L13.06 12l5.47 5.47a.75.75 0 11-1.06 1.06L12 13.06l-5.47 5.47a.75.75 0 01-1.06-1.06L10.94 12 5.47 6.53a.75.75 0 010-1.06z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2 items-end">
        {/* File upload button — hide during recording */}
        {!recording && !transcribing && (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || uploading}
            className="p-3 rounded-xl hover:bg-gray-800 text-gray-400 hover:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
            title="העלאת קובץ"
          >
            {uploading ? (
              <svg className="w-5 h-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
              </svg>
            )}
          </button>
        )}
        {/* No accept filter — backend validates allowed types */}
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handleFileSelect}
        />

        {/* Voice record — when recording show cancel + send, hiding textbox */}
        {recording ? (
          <div className="flex items-center gap-2 flex-1 justify-center">
            <button
              type="button"
              onClick={() => stopRecording(true)}
              className="p-3 rounded-xl bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
              title="בטל הקלטה"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                <path fillRule="evenodd" d="M5.47 5.47a.75.75 0 011.06 0L12 10.94l5.47-5.47a.75.75 0 111.06 1.06L13.06 12l5.47 5.47a.75.75 0 11-1.06 1.06L12 13.06l-5.47 5.47a.75.75 0 01-1.06-1.06L10.94 12 5.47 6.53a.75.75 0 010-1.06z" clipRule="evenodd" />
              </svg>
            </button>
            <div className="flex items-center gap-2 px-4 text-red-400 text-sm">
              <div className="w-2.5 h-2.5 bg-red-500 rounded-full animate-pulse" />
              <span>מקליט...</span>
            </div>
            <button
              type="button"
              onClick={() => stopRecording(false)}
              className="p-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white transition-colors"
              title="שלח הקלטה"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
              </svg>
            </button>
          </div>
        ) : transcribing ? (
          /* Transcribing state — replaces textbox with centered spinner */
          <div className="flex items-center gap-3 flex-1 justify-center py-3">
            <svg className="w-5 h-5 animate-spin text-brand-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-brand-400 text-sm">מתמלל ושולח...</span>
          </div>
        ) : (
          /* Normal state — mic + textbox + send */
          <>
            <button
              type="button"
              onClick={startRecording}
              disabled={disabled || uploading}
              className="p-3 rounded-xl hover:bg-gray-800 text-gray-400 hover:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
              title="הקלט הודעה קולית"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
              </svg>
            </button>

            <div className="relative flex-1">
              <textarea
                ref={textareaRef}
                dir={textDir}
                value={text}
                onChange={e => setText(e.target.value)}
                onKeyDown={handleKeyDown}
                onInput={handleInput}
                placeholder="כתוב לי כאן..."
                disabled={uploading || recording || transcribing}
                rows={1}
                className="w-full resize-none px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition text-sm leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>
            <button
              type="submit"
              disabled={disabled || (!text.trim() && attachedFiles.length === 0)}
              className="p-3 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 disabled:cursor-not-allowed transition-colors flex-shrink-0"
              title="שלח"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 text-white rotate-180">
                <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
              </svg>
            </button>
          </>
        )}
      </form>
    </div>
  )
}
