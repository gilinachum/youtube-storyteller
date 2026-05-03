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

### Phase 0: Create Memory Resource (one-time, ~5 min)

```bash
# Install the CLI
pip install bedrock-agentcore

# Create memory (STM only for now)
agentcore memory create storyteller-memory \
    --description "StoryTeller conversation memory" \
    --region us-east-1 \
    --wait
```

Save the returned `memory_id` in SSM Parameter Store:
```bash
aws ssm put-parameter \
    --name /storyteller/agentcore-memory-id \
    --type String \
    --value "<memory-id>"
```

### Phase 1: Wire AgentCoreMemorySessionManager into the Agent (~2 hours)

**`agent/main.py` changes:**

```python
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

def email_to_actor_id(email: str) -> str:
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")

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

`GET /sessions/{id}` currently reads messages from DDB. Change to read from AgentCore Memory:

```python
from bedrock_agentcore.memory import MemoryClient

def get_session_messages(session_id: str, email: str) -> list:
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    client = MemoryClient(region_name="us-east-1")
    
    events = client.list_events(
        memory_id=memory_id,
        actor_id=email_to_actor_id(email),
        session_id=session_id,
        max_results=100,
    )
    
    # Convert events to frontend message format
    messages = []
    for event in reversed(events):  # oldest first
        for payload in event.get("payload", []):
            if "conversational" in payload:
                conv = payload["conversational"]
                messages.append({
                    "role": conv["role"].lower(),
                    "content": extract_text_content(conv),
                    "timestamp": str(event["eventTimestamp"]),
                })
    return messages
```

### Phase 4: Update CDK Infrastructure (~30 min)

- Add `AGENTCORE_MEMORY_ID` env var to chat Lambda (from SSM)
- Add `bedrock-agentcore:CreateEvent`, `bedrock-agentcore:ListEvents`, `bedrock-agentcore:GetEvent` to Lambda IAM role
- Add `bedrock-agentcore[strands-agents]` to Lambda dependencies
- Keep `storyteller-messages` table (read-only fallback during migration window)

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

## What We Get

| Feature | Before (DDB) | After (AgentCore Memory) |
|---------|--------------|-------------------------|
| Message persistence | Text only (tool calls lost) | Full Converse API messages |
| History loading | Manual DDB query + string concat | Automatic via session_manager |
| Conversation resume | Broken (missing context) | Complete |
| Edit/regenerate | Blocked | Unblocked |
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
| Phase 5: Migration script | 1 hour build, minutes to run | Phase 0 |
| Phase 6: Deprecate DDB table | 15 min | Phase 1-5 validated |

**Total: ~6 hours of work, phased rollout.**

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
