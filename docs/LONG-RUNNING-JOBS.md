# Long-Running Jobs System (Transcription & Video Analysis)

## Overview

A generic jobs system for long-running work that runs **outside the agent** and requires asynchronous completion handling. The first job type is **audio/video transcription** via Amazon Transcribe; the architecture is designed for future job types (research, video analysis, export, etc.).

All jobs are scoped to a **user session** (a specific chat conversation).

## Architecture: Three-Lambda Model

| Lambda | Trigger | Responsibility | Knows job types? | Touches `consumed`? |
|--------|---------|----------------|-----------------|---------------------|
| **Job Resolver** | EventBridge (every 60s) | Scans for `started` jobs, dispatches type-specific handlers | Yes (routing) | No |
| **Type Handler** (e.g., Transcription) | Async invoke from Resolver | Resolves one job — checks service, saves results, updates status | Yes (deeply) | No |
| **Poll Lambda** | Frontend `GET /jobs/poll` | Reads job statuses for a session, tells frontend what to do | No | No (read-only) |

The **agent** is the only actor that reads job results and marks them `consumed`.

## DynamoDB: Jobs Table

```
Table: storyteller-jobs-{stage}
  PK: session_id (S)
  SK: job_id (S)

  Attributes:
    email          (S)    — user email
    job_type       (S)    — "transcription" | future types
    status         (S)    — "started" | "completed" | "failed"
    consumed       (BOOL) — has the agent processed this result? Default: false
    created_at     (S)    — ISO timestamp
    updated_at     (S)    — ISO timestamp
    metadata       (M)    — job-type-specific input (e.g., { transcribe_job_name, s3_key, filename })
    result         (M)    — output on completion (e.g., { s3_key, filename, text_preview, language })
    error          (S)    — error message on failure
    ttl            (N)    — epoch seconds, 365-day expiry

  GSI: status-index
    PK: status (S)
    SK: created_at (S)
    → Enables Job Resolver to efficiently query only "started" jobs
```

## Component Details

### 1. Job Resolver Lambda (`api/job_resolver.py`)

Triggered by EventBridge every 60 seconds. Always runs, regardless of whether there are active jobs.

```
Every 60s:
  1. Query GSI status-index WHERE status="started"
  2. For each job:
       - Async-invoke the type-specific handler Lambda (InvocationType="Event")
       - Pass: { job_id, session_id, email, job_type, metadata }
  3. Exit. Does NOT wait for handlers.
```

Cost at idle: ~$0/month (one DDB GSI query returning 0 items + one Lambda invocation at 128MB/100ms).

### 2. Transcription Handler Lambda (`api/transcription_handler.py`)

Invoked asynchronously by Job Resolver. Handles exactly one transcription job.

```
Input: { job_id, session_id, email, metadata: { transcribe_job_name, s3_key, filename } }

1. GetTranscriptionJob(transcribe_job_name)
2. If IN_PROGRESS → exit (resolver retries next minute)
3. If COMPLETED:
     - Download transcript from result URI
     - Save .txt to S3: uploads/{email}/{session_id}/{file_id}-transcript.txt
     - Record .txt as session file in sessions table (files list)
     - Conditional update jobs table: status="started" → status="completed"
       result = { s3_key, filename, text_preview (500 chars), language }
     - Delete Transcribe job (cleanup)
4. If FAILED:
     - Conditional update: status="started" → status="failed", error = reason
     - Delete Transcribe job
```

The conditional update (`ConditionExpression: status = "started"`) prevents duplicate processing when two resolver ticks overlap.

### 3. Poll Lambda (`api/jobs_poll.py`)

Called by the frontend. Completely dumb — reads DDB only, no service API calls.

```
GET /jobs/poll?session_id=X

1. Query jobs table: PK = session_id
2. Filter for consumed=false
3. Compute:
     has_pending    = any job where status="started" AND consumed=false
     has_unconsumed = any job where status IN ("completed","failed") AND consumed=false
4. Return: { has_pending: bool, has_unconsumed: bool }
```

### 4. Agent Tools

**`start_transcription(s3_key, file_id, session_id, email)`**
- Starts AWS Transcribe job (IdentifyLanguage: he-IL, en-US; no MediaFormat — auto-detect)
- Writes job to DDB: `status="started"`, `consumed=false`
- Estimates time: `file_size_mb / 1.5 / 5 * 60` seconds (rough heuristic)
- Returns `{ job_id, estimated_seconds }`

**`list_pending_jobs(session_id, email)`**
- Queries jobs table: `consumed=false AND status IN ("completed", "failed")`
- Returns full details: `[{ job_id, job_type, status, result, error, metadata }]`

**`mark_job_consumed(job_id, session_id)`**
- Updates job: `consumed=true`
- Returns `{ success: true }`

## Frontend: Singleton Poll Loop

After every agent response, the frontend calls `GET /jobs/poll?session_id=X` once.

### State Machine

```
                    ┌─────────────┐
                    │   IDLE      │ ← initial state
                    └──────┬──────┘
                           │ agent response received
                           ▼
                    ┌─────────────┐
                    │  CHECK      │ → GET /jobs/poll
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ IDLE     │ │ POLLING  │ │ NOTIFY   │
        │(nothing) │ │(pending) │ │(ready)   │
        └──────────┘ └────┬─────┘ └────┬─────┘
                          │ 60s        │
                          ▼            ▼
                     GET /jobs/poll   send msg to agent
                          │            │
                     (re-evaluate)     └→ IDLE or POLLING
```

**Rules:**
- Only ONE poll loop runs at a time (singleton). If a new agent response arrives while polling, the existing loop handles it — no new loop spawns.
- `has_unconsumed=true` → send message to agent: `"יש עבודות שהסתיימו, בדוק בבקשה"`
- `has_pending=true AND has_unconsumed=false` → keep polling every 60s
- `has_pending=false AND has_unconsumed=false` → stop, go idle
- On session load → run initial check (picks up jobs from previous visits)

## End-to-End Flow

```
User          Frontend       Poll Lambda    Job Resolver    Transcription     Jobs DDB    Agent
  │               │              │              │           Handler              │           │
  │─upload file──▶│              │              │              │                 │           │
  │─"transcribe"──────────────────────────────────────────────────────────────────────────▶│
  │               │              │              │              │                 │  start_transcription()
  │               │              │              │              │                 │◀─write────│
  │               │              │              │              │                 │ started   │
  │◀─"Started, ~3 min"─────────────────────────────────────────────────────────────────────│
  │               │              │              │              │                 │           │
  │               │─poll────────▶│              │              │                 │           │
  │               │              │─query───────▶│              │                 │           │
  │               │◀─{pending:T}─│              │              │                 │           │
  │               │ (start 60s loop)            │              │                 │           │
  │               │              │              │              │                 │           │
  │               │              │        [60s tick]           │                 │           │
  │               │              │              │─query GSI───▶│                 │           │
  │               │              │              │─async invoke▶│                 │           │
  │               │              │              │              │─check Transcribe│           │
  │               │              │              │              │ (IN_PROGRESS)   │           │
  │               │              │              │              │ → exit          │           │
  │               │              │              │              │                 │           │
  │               │              │        [next 60s tick]      │                 │           │
  │               │              │              │─async invoke▶│                 │           │
  │               │              │              │              │─check Transcribe│           │
  │               │              │              │              │ (COMPLETED!)    │           │
  │               │              │              │              │─save .txt to S3 │           │
  │               │              │              │              │─update DDB─────▶│           │
  │               │              │              │              │ completed+result│           │
  │               │              │              │              │                 │           │
  │               │─poll────────▶│              │              │                 │           │
  │               │              │─query───────▶│              │                 │           │
  │               │◀─{unconsumed:T, pending:F}──│              │                 │           │
  │               │ (stop poll, notify agent)   │              │                 │           │
  │               │─"יש עבודות שהסתיימו"───────────────────────────────────────────────────▶│
  │               │              │              │              │                 │  list_pending_jobs()
  │               │              │              │              │                 │◀─query────│
  │               │              │              │              │                 │─results──▶│
  │               │              │              │              │                 │           │ process
  │               │              │              │              │                 │◀─consumed─│
  │◀─"Transcription ready! Here's a summary..."────────────────────────────────────────────│
```

## Edge Cases

| Case | Handling |
|------|----------|
| Job completes before first poll | Poll sees `completed + unconsumed` → notify agent immediately |
| Old unconsumed jobs from previous session visits | Poll picks them up on session load |
| Multiple jobs finish simultaneously | `list_pending_jobs` returns all; agent processes each, marks consumed |
| Two resolver ticks invoke handler for same job | Conditional DDB update prevents duplicate; S3 write is idempotent |
| Handler crashes after saving .txt but before updating job | Job stays `started`, handler retried next minute (idempotent) |
| Agent crashes while processing results | Jobs stay `consumed=false`, frontend re-notifies on next poll |
| No active jobs (steady state) | Resolver scans GSI, finds nothing, exits. ~$0 cost. |
| Multiple poll loops (duplicate agent responses) | Frontend enforces singleton — max one loop at a time |

## Upload: Extended File Types

```python
ALLOWED_EXTENSIONS = {
    # Documents
    ".pdf", ".pptx", ".ppt", ".txt", ".md", ".doc", ".docx",
    # Images
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    # Audio
    ".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".wma",
    # Video
    ".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v",
}
MAX_SIZE_MB = 2000
```

S3 lifecycle: 365-day expiration on `uploads/` prefix.

## Cleanup

Remove dead code from the pre-AgentCore dev fallback:
- `api/chat.py` (async Lambda chat with self-invocation + polling)
- CDK routes for `/chat` and `/chat/{job_id}`
- Evaluate whether the old `storyteller-jobs` DDB table (used only by `chat.py`) can be repurposed or removed
