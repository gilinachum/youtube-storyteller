---
name: transcription-workflow
description: Process audio/video files into structured content — transcribe, clean up, extract key points, and organize into chapters. Use when a user uploads an audio/video file or asks to work with a transcript.
---

# Transcription Workflow

## Trigger

User uploads an audio or video file (.mp3, .mp4, .webm, .wav, .m4a).

## Steps

1. **Start transcription** — use `start_transcription` tool with the uploaded file's S3 key
2. **Inform user** — tell them transcription is in progress (takes 1-5 min depending on length)
3. **When notified of completion** — use `list_pending_jobs` to get the result
4. **Mark consumed** — use `mark_job_consumed` after processing
5. **Read transcript** — use `read_file` with the transcript S3 key
6. **Process** — based on user intent:
   - Clean up raw transcript (remove filler words, fix formatting)
   - Extract key topics and timestamps
   - Create chapter markers
   - Summarize main points
   - Convert to video script outline

## Transcription Output Format

The raw transcript is plain text (Hebrew or English). AWS Transcribe provides:
- Full text without timestamps (current implementation)
- Language auto-detection

## Post-Processing Options

Ask the user what they want:
- **סיכום** (Summary) — bullet points of key topics
- **תוכנית סרטון** (Video plan) — convert talk into a YouTube video structure
- **ניקוי** (Cleanup) — readable version without stutters/fillers
- **פרקים** (Chapters) — segment into logical sections with titles

## Important Notes

- Transcription is async — don't block the conversation
- Files must be in the session's uploads folder
- After transcription completes, provide the `file://` download link
- Hebrew transcription quality is good but may need manual fixes for technical terms
