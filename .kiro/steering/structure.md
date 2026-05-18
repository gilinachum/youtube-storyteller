# StoryTeller — Project Structure

## Root Layout

```
youtube-storyteller/
├── agent/              # Strands agent deployed to AgentCore Runtime
├── api/                # Lambda handler functions
├── frontend/           # React + Vite SPA
├── infra/              # AWS CDK infrastructure stacks
├── infra-private/      # Private infra (not in main repo)
├── private/            # Private config/notes (gitignored)
├── docs/               # Product, requirements, and technical documentation
├── tests/              # All tests (unit + E2E)
├── scripts/            # Deploy, test, and utility scripts
├── .kiro/              # Kiro steering and specs
├── .venv/              # Python virtual environment (uv-managed)
├── .env                # Local environment variables (gitignored)
├── .env.example        # Environment variable template
├── pyproject.toml      # Python project + dependencies
├── pytest.ini          # pytest config
├── cdk-outputs-dev.json
└── cdk-outputs-prod.json
```

## `agent/` — AI Agent (AgentCore)

```
agent/
├── runtime_app.py      # AgentCore entrypoint: streaming, keepalive, DynamoDB history
├── main.py             # Agent factory (create_agent)
├── system_prompt.py    # System prompt builder (loads methodology + virality)
├── research_agent.py   # Research sub-agent (preserve_context=False)
├── thumbnail_agent.py  # Thumbnail sub-agent (preserve_context=True)
├── prompts/
│   ├── methodology.md  # YouTube 7-part structure + hook formulas
│   └── virality.md     # Virality coaching rules
├── tools/              # Agent tools (one file per tool)
│   ├── content_fetch.py
│   ├── web_research.py
│   ├── trend_analysis.py
│   ├── pdf_extract.py
│   ├── pptx_extract.py
│   ├── export_document.py
│   ├── session_manager.py
│   ├── generate_thumbnail.py
│   ├── save_user_photo.py
│   ├── list_user_photos.py
│   ├── list_style_templates.py
│   ├── start_transcription.py
│   ├── list_pending_jobs.py
│   ├── mark_job_consumed.py
│   └── read_file.py
└── knowledge/          # SKILL.md files for agent knowledge domains
    ├── youtube-planning/
    ├── thumbnail-design/
    ├── transcription-workflow/
    ├── video-review/
    └── ...
```

## `api/` — Lambda Handlers

```
api/
├── _auth_context.py        # Shared auth/JWT context extraction
├── sessions.py             # GET/POST /sessions, session sharing
├── upload.py               # Presigned S3 upload URLs, file management
├── transcribe.py           # Start/poll Amazon Transcribe jobs
├── transcription_handler.py
├── jobs_poll.py            # Long-running jobs polling
├── job_resolver.py         # Job result resolution
└── thumbnail_proxy.py      # Thumbnail serving proxy
```

## `frontend/src/` — React SPA

```
frontend/src/
├── App.tsx                 # Root component, routing, auth gate
├── main.tsx                # Entry point
├── api.ts                  # All API calls (typed, async)
├── auth.ts                 # Auth abstraction layer
├── auth-cognito.ts         # Cognito-specific auth implementation
├── components/
│   ├── Chat.tsx            # Main chat container
│   ├── ChatInput.tsx       # Input bar (text, voice, file upload)
│   ├── ChatMessages.tsx    # Message list + streaming rendering
│   ├── Sidebar.tsx         # Session list sidebar
│   ├── FileList.tsx        # Uploaded files panel
│   └── ShareModal.tsx      # Session sharing modal
└── hooks/                  # Custom React hooks
```

## `infra/` — CDK Stacks

```
infra/
├── app.py                  # CDK app entry point
├── stacks/
│   ├── data_stack.py       # DynamoDB tables (sessions, messages, jobs)
│   ├── api_stack.py        # API Gateway, Lambda functions, AgentCore integration
│   ├── frontend_stack.py   # S3 + CloudFront + CF Functions
│   └── backup_stack.py     # Backup configuration
├── cf-functions/           # CloudFront Functions (media auth, SPA rewrite)
├── layers/                 # Lambda layers
└── cdk.json
```

## `tests/` — Test Suite

```
tests/
├── conftest.py             # Shared fixtures (moto mocks, env setup)
├── test_api.py             # Lambda handler tests (sessions, upload, jobs)
├── test_tools.py           # Agent tool unit tests
├── test_runtime_app.py     # AgentCore runtime tests
├── test_system_prompt.py   # System prompt builder tests
├── test_thumbnail.py       # Thumbnail agent unit tests
├── test_jobs.py            # Jobs system tests
├── test_session_sharing.py # Session sharing tests
├── test_session_pinning.py # Session pinning tests
├── test_save_user_photo.py # User photo upload tests
├── test_e2e.py             # E2E tests (Playwright browser)
├── test_e2e_live.py        # E2E live AWS tests
└── test_e2e_thumbnail.py   # E2E thumbnail tests
```

## `docs/` — Documentation

```
docs/
├── PRODUCT.md              # What StoryTeller does, user flow, design principles
├── REQUIREMENTS.md         # All functional requirements with status
├── TECHNICAL-DESIGN.md     # Architecture, data model, streaming, sub-agents
├── CODING-GUIDELINES.md    # Conventions, security rules, common mistakes
└── LONG-RUNNING-JOBS.md    # Async jobs system design
```

## Key Conventions

- **One tool per file** in `agent/tools/` — keep tools small and focused
- **One Lambda handler per concern** in `api/` — auth, sessions, upload, transcribe are separate
- **One CDK stack per layer** — stateful (data) separate from stateless (api, frontend)
- **All tests in `tests/`** — no test files scattered in source directories
- **Temporary test/debug scripts** go in `.testscripts/` (gitignored)
- **Secrets never in code** — always Secrets Manager; config via env vars

## S3 Layout (Upload Bucket)

```
uploads/{email}/{session_id}/{file_id}-{filename}   # Session files
voice/{email}/{session_id}/{file_id}.webm            # Voice recordings (temp)
exports/{email}/{session_id}/{filename}              # Exported documents
media/photos/{email}/{uuid}.{ext}                    # User profile photos
media/photos/{email}/photos.json                     # Photo metadata
media/thumbnails/{email}/{session_id}/thumb-{uuid}.png
templates/thumbnails/{template_id}.png               # Style templates
templates/thumbnails/templates.json                  # Template metadata
```

## DynamoDB Tables

| Table | PK | SK | Purpose |
|-------|----|----|---------|
| `storyteller-sessions` | `email` | `session_id` | Session metadata + file list |
| `storyteller-messages` | `session_id` | `timestamp` | Chat message history |
| `storyteller-jobs` | `job_id` | — | Async job tracking |
