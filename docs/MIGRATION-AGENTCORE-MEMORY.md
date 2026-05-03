# Migration Plan: DynamoDB → AgentCore Memory

## Current State

### DynamoDB Tables
| Table | PK | SK | Purpose |
|-------|----|----|---------|
| `storyteller-sessions` | `email` (S) | `session_id` (S) | Session metadata: name, status, created_at, updated_at, language, shared_with, files |
| `storyteller-messages` | `session_id` (S) | `timestamp` (S) | Message history: role, content (text only — tool_use/tool_result lost) |
| `storyteller-jobs` | `job_id` (S) | — | Async job tracking: status, progress, response, error |

### Data Volume
- **46 sessions**, **174 messages**, **5 unique emails/actors**
- All session IDs are UUIDs → match AgentCore `sessionId` pattern ✅
- Emails contain `@` → **do NOT match** `actorId` pattern `[a-zA-Z0-9][a-zA-Z0-9-_/]*` ❌

### Current Code Touchpoints
| File | DDB Usage | What Changes |
|------|-----------|--------------|
| `api/chat.py` | Reads messages for history, writes user+assistant messages, manages jobs | **Major rewrite** — replace message R/W with AgentCore Memory session_manager |
| `api/sessions.py` | Lists sessions, gets messages, deletes sessions, shares, file downloads | **Partial rewrite** — message reads move to AgentCore, session metadata stays (or moves) |
| `agent/main.py` | `create_agent()` — no session_manager today | **Add session_manager** |
| `infra/stacks/data_stack.py` | Defines all 3 DDB tables | Keep jobs table, evaluate keeping sessions table |

### Key Problem Being Solved
`chat.py` only saves `role` + `content` (text). All `tool_use` and `tool_result` blocks are lost. This makes conversation resume incomplete — the agent can't see its own tool calls, breaking edit/regenerate and multi-turn reasoning.

---

## Target Architecture

### What Moves to AgentCore Memory
- **Message history** (full Converse API messages including tool_use/tool_result) → AgentCore Memory STM events
- **Session continuity** → `AgentCoreMemorySessionManager` handles all of it

### What Stays in DynamoDB
- **`storyteller-jobs`** — async job tracking (not conversation data, no reason to migrate)
- **`storyteller-sessions`** — session metadata (name, shared_with, files, language, status) — AgentCore Memory has no metadata model for this. Keep as-is.

### What Gets Removed (eventually)
- **`storyteller-messages`** — replaced entirely by AgentCore Memory STM events. Keep read-only during migration window, then deprecate.

---

## ID Mapping

### actorId
Email → actorId transform (AgentCore pattern: `[a-zA-Z0-9][a-zA-Z0-9-_/]*`):

```python
def email_to_actor_id(email: str) -> str:
    """Convert email to valid AgentCore actorId.
    
    'gili@amazon.com' → 'gili-at-amazon-com'
    'gili+oc3@amazon.com' → 'gili-oc3-at-amazon-com'
    """
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")
```

### sessionId
UUIDs already match the pattern. Pass through as-is.

### memoryId
One memory resource for the entire StoryTeller app. Created once via CLI.

---

## Implementation Plan

### Phase 0: Create Memory Resource via CDK (~30 min)

Memory creation is managed in CDK alongside other infrastructure — not a manual CLI step.

**`infra/stacks/data_stack.py` changes:**

```python
from aws_cdk import custom_resources as cr

# AgentCore Memory resource (STM only for now)
self.agentcore_memory = cr.AwsCustomResource(
    self, "AgentCoreMemory",
    on_create=cr.AwsSdkCall(
        service="BedrockAgentCoreControl",
        action="createMemory",
        parameters={
            "name": "storyteller-memory",
            "description": "StoryTeller conversation memory",
            "clientToken": "storyteller-memory-create",  # idempotent
        },
        physical_resource_id=cr.PhysicalResourceId.from_response("memory.memoryId"),
    ),
    on_delete=cr.AwsSdkCall(
        service="BedrockAgentCoreControl",
        action="deleteMemory",
        parameters={"memoryId": cr.PhysicalResourceIdReference()},
    ),
    policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
        resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
    ),
)

self.memory_id = self.agentcore_memory.get_response_field("memory.memoryId")

# Store in SSM for Lambda to read
ssm.StringParameter(
    self, "MemoryIdParam",
    parameter_name="/storyteller/agentcore-memory-id",
    string_value=self.memory_id,
)
```

The Lambda reads the memory ID from SSM at startup (cached in env var via CDK `Environment`).

### Phase 1: Wire AgentCoreMemorySessionManager into the Agent (~2 hours)

**`agent/main.py` changes:**

```python
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

def email_to_actor_id(email: str) -> str:
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")

# ↑ Unit tested — see tests/test_helpers.py

def create_agent(email: str = "", session_id: str = "") -> Agent:
    model = BedrockModel(...)
    
    # Session manager — AgentCore Memory handles persistence
    session_manager = None
    if email and session_id:
        memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
        if memory_id:
            config = AgentCoreMemoryConfig(
                memory_id=memory_id,
                session_id=session_id,
                actor_id=email_to_actor_id(email),
            )
            session_manager = AgentCoreMemorySessionManager(
                agentcore_memory_config=config,
                region_name="us-east-1",
            )
    
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[...],
        session_manager=session_manager,  # ← NEW
    )
    return agent
```

**What this gives us for free:**
- Full Converse API message persistence (tool_use, tool_result, images — everything)
- Automatic conversation reload on next request for the same session
- Monotonic timestamp ordering
- Batching support (configurable)

### Phase 2: Remove Manual Message R/W from chat.py (~1 hour)

The `AgentCoreMemorySessionManager` handles message persistence automatically via Strands hooks. Remove the manual DDB writes:

**Before (current):**
```python
# Save messages manually
msgs_table.put_item(Item={...role: "user", content: message})
msgs_table.put_item(Item={...role: "assistant", content: agent_response})
```

**After:**
```python
# AgentCoreMemorySessionManager saves messages automatically
# Just pass email + session_id to create_agent()
agent = create_agent(email=email, session_id=session_id)
response = agent(full_prompt)
# Messages are already persisted — no manual write needed
```

Also remove the manual history loading — the session manager loads it automatically:

**Before:**
```python
# Manual history load from DDB
result = msgs_table.query(...)
history_text = "\n".join([...])
full_prompt = f"[Previous conversation:\n{history_text}\n]\n\nUser: {message}"
```

**After:**
```python
# Session manager auto-loads history into agent context
response = agent(message)  # Just the new message, history is handled
```

### Phase 3: Update sessions.py Message Reading (~1 hour)

`GET /sessions/{id}` currently reads messages from DDB. Change to read from AgentCore Memory.

The `AgentCoreMemorySessionManager` already has `list_messages()` which calls `ListEvents` and converts via `AgentCoreMemoryConverter.events_to_messages()` → returns `list[SessionMessage]` with full Converse API content (tool_use, tool_result, images — everything). We use the session manager directly instead of raw API calls:

```python
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

MAX_HISTORY_EVENTS = 200

def get_session_messages(session_id: str, email: str) -> list:
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=email_to_actor_id(email),
    )
    sm = AgentCoreMemorySessionManager(
        agentcore_memory_config=config,
        region_name="us-east-1",
    )
    
    # list_messages returns SessionMessage objects with full Converse API content
    session_messages = sm.list_messages(
        session_id=session_id,
        agent_id="storyteller",
    )
    
    if len(session_messages) >= MAX_HISTORY_EVENTS:
        logger.warning(
            "Session %s hit max history limit (%d messages). "
            "Older messages may be truncated.",
            session_id, MAX_HISTORY_EVENTS,
        )
    
    # Convert SessionMessage → frontend format
    # Frontend gets display text + eventId only. No raw tool_use/tool_result.
    # Tool status updates ("reading a doc") are extracted as progress labels.
    return [
        {
            "role": sm.message["role"],
            "content": extract_display_text(sm.message),  # text for chat bubbles
            "event_id": sm.message_id,  # needed for edit/restore (fork point)
            "timestamp": sm.created_at,
        }
        for sm in session_messages
    ]
```

**Key:** Frontend only sees display text + `event_id` (for the edit/fork-point feature). Full Converse API messages (tool_use/tool_result) stay server-side — the session manager handles them internally when loading history for the agent.

### Phase 4: Update CDK Infrastructure (~30 min)

- Memory resource created in CDK via custom resource (Phase 0)
- Add `AGENTCORE_MEMORY_ID` env var to chat Lambda (from SSM/CDK output)
- Add IAM permissions to Lambda role:
  - `bedrock-agentcore:CreateEvent`
  - `bedrock-agentcore:ListEvents`
  - `bedrock-agentcore:GetEvent`
  - `bedrock-agentcore:DeleteEvent` (needed for edit/regenerate — update_message does delete+create)
  - `bedrock-agentcore:ListSessions`
- Add `bedrock-agentcore[strands-agents]` to Lambda dependencies
- Keep `storyteller-messages` table (read-only fallback during migration window)

### Phase 4b: Unit Tests (~1 hour)

```python
# tests/test_helpers.py
import pytest
from agent.helpers import email_to_actor_id

class TestEmailToActorId:
    def test_simple_email(self):
        assert email_to_actor_id("gili@amazon.com") == "gili-at-amazon-com"

    def test_plus_addressing(self):
        assert email_to_actor_id("gili+oc3@amazon.com") == "gili-oc3-at-amazon-com"

    def test_matches_actorId_pattern(self):
        import re
        pattern = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-_/]*$")
        emails = ["a@b.com", "user+tag@corp.co.uk", "test.name@domain.org"]
        for email in emails:
            result = email_to_actor_id(email)
            assert pattern.match(result), f"{email} → {result} doesn't match actorId pattern"

    def test_roundtrip_uniqueness(self):
        # Different emails must produce different actor IDs
        ids = {email_to_actor_id(e) for e in ["a@b.com", "a@c.com", "b@b.com"]}
        assert len(ids) == 3
```

### Phase 5: One-Time DDB → AgentCore Memory Migration (~1 hour to build, minutes to run)

**Feasibility: ✅ Yes**

The `CreateEvent` API accepts `eventTimestamp` — we can replay DDB messages with their original timestamps, preserving chronological order.

**Migration script outline:**

```python
"""One-time migration: DDB messages → AgentCore Memory events."""
import boto3
import json
import time
from datetime import datetime, timezone

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
agentcore = boto3.client("bedrock-agentcore", region_name="us-east-1")

MEMORY_ID = "<from-ssm>"
MESSAGES_TABLE = "storyteller-messages"
SESSIONS_TABLE = "storyteller-sessions"

def email_to_actor_id(email):
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")

def migrate():
    sess_table = dynamodb.Table(SESSIONS_TABLE)
    msgs_table = dynamodb.Table(MESSAGES_TABLE)
    
    # 1. Build session_id → email mapping
    sessions = sess_table.scan()["Items"]
    session_email = {s["session_id"]: s["email"] for s in sessions}
    
    # 2. Scan all messages, grouped by session
    all_msgs = []
    last_key = None
    while True:
        kwargs = {}
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        result = msgs_table.scan(**kwargs)
        all_msgs.extend(result["Items"])
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
    
    # Group by session_id, sort by timestamp
    from collections import defaultdict
    by_session = defaultdict(list)
    for m in all_msgs:
        by_session[m["session_id"]].append(m)
    
    migrated = 0
    skipped = 0
    
    for session_id, messages in by_session.items():
        email = session_email.get(session_id)
        if not email:
            print(f"  ⚠️ No email for session {session_id}, skipping")
            skipped += len(messages)
            continue
        
        actor_id = email_to_actor_id(email)
        messages.sort(key=lambda m: m["timestamp"])
        
        for msg in messages:
            # Convert DDB message to Converse API format
            role = msg["role"].upper()  # USER or ASSISTANT
            content = msg.get("content", "")
            
            ts = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
            
            # Create event with original timestamp
            try:
                agentcore.create_event(
                    memoryId=MEMORY_ID,
                    actorId=actor_id,
                    sessionId=session_id,
                    eventTimestamp=ts,
                    payload=[{
                        "conversational": {
                            "role": role,
                            "content": {"text": json.dumps({
                                "message": {
                                    "role": role.lower(),
                                    "content": [{"text": content}]
                                },
                                "message_id": 0,
                                "created_at": msg["timestamp"]
                            })}
                        }
                    }],
                )
                migrated += 1
            except Exception as e:
                if "ThrottledException" in str(type(e).__name__):
                    time.sleep(2)  # Back off on throttle
                    # Retry once
                    agentcore.create_event(...)
                else:
                    print(f"  ❌ Failed: {e}")
                    skipped += 1
            
            time.sleep(0.1)  # Rate limit safety (174 msgs → ~17 seconds)
    
    print(f"\n✅ Migrated: {migrated}, Skipped: {skipped}")

if __name__ == "__main__":
    migrate()
```

**Rate limiting notes:**
- 174 messages total — with 100ms delay, completes in ~17 seconds
- `CreateEvent` is rate-limited but 174 calls is well within any reasonable quota
- `eventTimestamp` preserves original ordering
- `clientToken` can be used for idempotency (re-runnable)

### Phase 6: Deprecate storyteller-messages Table (after validation)

1. Deploy Phase 1-4
2. Run Phase 5 migration script
3. Test: verify conversations load correctly from AgentCore Memory
4. Remove `storyteller-messages` DDB read fallback
5. Optionally delete the DDB table (or leave with TTL to auto-clean)

---

---

## Phase 7: Edit Message & Restore Point ("go back in time")

### The Feature
User clicks on any previous message → edits it → agent regenerates from that point forward, discarding everything after.

### How AgentCore Memory Branching Makes This Work

AgentCore Memory has **first-class branching** — exactly the primitive we need:

- `CreateEvent` accepts `branch: {name, rootEventId}`
- `ListEvents` accepts `filter.branch: {name, includeParentBranches}`
- Events on `main` branch up to the `rootEventId` are the "parent" history
- New events on the child branch are the "edited" continuation

### Concrete Example: Editing Your Last Message

```
main branch (current state):
  E1 [user: "video about Docker"]
  E2 [assistant: researches, uses tools, responds with plan]
  E3 [user: "make it shorter"]        ← you want to change this
  E4 [assistant: shorter version]
```

You want to replace E3 ("make it shorter") with "focus on networking".

**Step 1:** Branch from **E2** — the last event *before* the one being edited:

```python
CreateEvent(
    branch={"name": "edit-a3f8", "rootEventId": "E2"},
    payload="focus on networking"   # the new user message
)
# → creates E5 on branch edit-a3f8
```

**Step 2:** Agent loads history with `includeParentBranches=True`:

```python
ListEvents(branch="edit-a3f8", includeParentBranches=True)
# → E1, E2 (from main) + E5 (from edit-a3f8)
# Agent sees: E1 → E2 → E5. Never sees E3 or E4.
```

Agent responds naturally to "focus on networking" with the full prior context → creates E6.

**Result — two timelines coexist, nothing deleted:**

```
main:       E1 → E2 → E3 → E4          (preserved, never deleted)
edit-a3f8:  E1 → E2 → E5 → E6          (active branch)
                 ↑
            fork point
```

Session metadata in DDB tracks `current_branch: "edit-a3f8"` so the next request continues on the right branch. Switching back to `main` = "undo the edit".

### API Implementation

```python
# POST /sessions/{id}/edit
def edit_message(session_id: str, email: str, body: dict):
    fork_event_id = body["fork_event_id"]  # E2 — last event BEFORE the one being edited
    new_message = body["message"]          # the replacement user message
    branch_name = f"edit-{uuid4().hex[:8]}"
    
    # 1. Create session manager targeting the NEW branch
    config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=email_to_actor_id(email),
    )
    # Session manager needs branch awareness (subclass or config extension)
    # - Writes go to branch_name with rootEventId=fork_event_id
    # - Reads use BranchFilter(name=branch_name, includeParentBranches=True)
    
    # 2. Create agent — history auto-loads from branch
    #    Sees: E1 → E2 (parent events up to fork point)
    agent = create_agent(email=email, session_id=session_id)
    
    # 3. Run with the new message — response goes on the new branch
    response = agent(new_message)
    
    # 4. Store current branch name in session metadata (DDB sessions table)
    update_session_branch(email, session_id, branch_name)
    
    # 5. Subsequent requests for this session use the same branch
    #    (regular /chat reads current_branch from DDB, passes to session manager)
```

### Continuing After an Edit

After the edit, the user keeps chatting. All new messages go on the same branch:

```
edit-a3f8:  E1 → E2 → E5 → E6 → E7[user] → E8[assistant] → ...
```

If the user edits again (say, E7), we branch again:

```
edit-a3f8:  E1 → E2 → E5 → E6 → E7 → E8          (abandoned)
edit-b91c:  E1 → E2 → E5 → E6 → E9 → E10          (active)
                                  ↑
                             fork from E6
```

`includeParentBranches=True` walks up the chain automatically — branches of branches work.

### Feasibility Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| Branch creation | ✅ Native API | `CreateEvent` with `branch.rootEventId` |
| History loading from branch | ✅ Native API | `ListEvents` with `includeParentBranches=true` |
| Strands session manager branch support | ⚠️ Partial | SDK stores events on `main` by default. Need to pass branch config or extend the session manager to support custom branch names |
| Multiple edits (branch of a branch) | ✅ Works | Each edit creates a new branch; `includeParentBranches` walks up the chain |
| Frontend: identify which event to branch from | 🔧 Needs work | Frontend needs `eventId` per message — add to Phase 3 response |
| No data loss | ✅ Immutable | Old branch events are never deleted, just "abandoned" |

### What Needs Custom Code

The `AgentCoreMemorySessionManager` currently writes all events on the `main` branch. For edit/restore we need:

1. **Branch-aware config** — pass `branch_name` + `root_event_id` to the session manager (or subclass it)
2. **Branch-aware reads** — `list_messages` must use `BranchFilter(name=branch_name, includeParentBranches=True)`
3. **Session metadata** — store `current_branch` in the DDB sessions table so the next request knows which branch to load
4. **Frontend** — expose `eventId` per message, add "Edit" button that sends `POST /sessions/{id}/edit`

Estimate: ~4 hours on top of the base migration (most is extending the session manager for branch awareness).

### Why This Is Better Than the DDB Approach

With DDB, edit/regenerate would mean:
- Deleting messages after the edit point (destructive)
- Losing the original conversation forever
- No way to "undo" the edit

With AgentCore Memory branching:
- Original conversation is preserved on `main`
- Each edit creates an immutable fork
- User could even switch between branches ("undo edit")
- Full audit trail of all versions

---

## What We Get

| Feature | Before (DDB) | After (AgentCore Memory) |
|---------|--------------|-------------------------|
| Message persistence | Text only (tool calls lost) | Full Converse API messages |
| History loading | Manual DDB query + string concat | Automatic via session_manager |
| Conversation resume | Broken (missing context) | Complete |
| Edit/regenerate | Blocked | Unblocked — via branching (immutable, undo-able) |
| Long-term memory | None | Available (Phase 2 — add LTM strategies later) |
| Cross-session knowledge | None | LTM namespace queries (future) |
| Session metadata | In DDB | Still in DDB (no change) |
| Async job tracking | In DDB | Still in DDB (no change) |

---

## Risk & Rollback

| Risk | Mitigation |
|------|-----------|
| AgentCore Memory API latency | Batching (batch_size=5), flush_interval | 
| Rate limiting on CreateEvent | 100ms delay in migration, exponential backoff in prod |
| Data loss during cutover | Keep DDB table read-only as fallback; migration is additive |
| actorId mapping breaks | Deterministic transform, bidirectional (can reverse) |
| Region availability | us-east-1 same as existing DDB — no cross-region issues |

**Rollback:** Revert code to DDB reads. DDB data is untouched. No data loss.

---

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 0: Create memory resource | 5 min | None |
| Phase 1: Wire session_manager | 2 hours | Phase 0 |
| Phase 2: Remove manual R/W | 1 hour | Phase 1 |
| Phase 3: Update sessions.py | 1 hour | Phase 1 |
| Phase 4: CDK infra update | 30 min | Phase 0 |
| Phase 4b: Unit tests | 1 hour | Phase 1 |
| Phase 5: Migration script | 1 hour build, minutes to run | Phase 0 |
| Phase 6: Deprecate DDB table | 15 min | Phase 1-5 validated |
| Phase 7: Edit/restore point | 4 hours | Phase 1-4 + branch-aware session manager |

**Total: ~11 hours of work, phased rollout.**

---

## Future: Long-Term Memory (Phase 2 — later)

Add LTM strategies to the memory resource:

```bash
agentcore memory update storyteller-memory \
    --strategies '[
        {"summaryMemoryStrategy": {
            "name": "SessionSummarizer",
            "namespaces": ["/summaries/{actorId}/{sessionId}"]
        }},
        {"userPreferenceMemoryStrategy": {
            "name": "UserPrefs",
            "namespaces": ["/preferences/{actorId}"]
        }},
        {"semanticMemoryStrategy": {
            "name": "FactExtractor",
            "namespaces": ["/facts/{actorId}"]
        }}
    ]'
```

This enables:
- **Session summaries** — agent remembers previous conversation context without replaying all events
- **User preferences** — "I prefer Hebrew", "my channel focuses on tech" persists across sessions
- **Fact extraction** — key facts from research auto-extracted for cross-session knowledge

LTM generation happens automatically in the background after STM events are created. No code changes needed — just add retrieval_config to the AgentCoreMemoryConfig.
