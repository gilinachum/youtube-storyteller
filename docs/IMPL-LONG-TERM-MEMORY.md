# Long-Term Memory — Implementation Plan

_Phase 1 Implementation | 2026-05-12_

Based on `DESIGN-LONG-TERM-MEMORY.md`. This document specifies the exact code changes for Phase 1 (add strategies) and Phase 2 (memory injection + recall tool).

---

## Scope

**In scope (this PR):**
- Phase 1: `update_memory.py` script to add strategies to existing memory
- Phase 2: Memory retrieval + injection into system prompt on first message
- Phase 3: `recall_session_details` tool for cross-session detail extraction
- Unit tests for all new code

**Out of scope:**
- Phase 4: Agent memory-aware flow (system prompt Hebrew examples) — separate PR
- Custom memory strategy (future)
- DDB migration of existing 174 messages

---

## 1. New Files

### `infra/scripts/update_memory.py`
One-shot CLI script to add `userPreferenceMemoryStrategy` and `summaryMemoryStrategy` to the existing memory resource.

**Key safety:**
- Reads current config via `get_memory()` first (UpdateMemory is FULL REPLACE)
- Preserves `eventExpiryDuration`, tags
- `encryptionKeyArn` may be None — only pass if present
- Accepts `--memory-id` arg or `AGENTCORE_MEMORY_ID` env var
- Dry-run mode by default, `--apply` to execute

### `agent/tools/recall_session_details.py`
Factory function `make_recall_session_details_tool(email)` returning a `@tool`-decorated function.

**Design:**
- Uses raw boto3 `bedrock-agentcore` client (not SDK — consistent with Lambda reader pattern)
- Loads events via paginated `list_events` (maxResults=100 per call)
- Builds conversation text from Converse-format events
- Caps at 50 exchanges to limit token usage
- Passes conversation + query to a lightweight extraction sub-agent (Sonnet)
- Returns dict with `session_id`, `query`, `extracted` (str), `event_count`
- On failure returns `{"error": str}`

### `agent/memory_retrieval.py`
Standalone module for memory retrieval logic. Keeps `main.py` clean.

**Functions:**
- `retrieve_long_term_memories(email: str, query_text: str) -> list[dict]`
  - Uses boto3 `bedrock-agentcore` client `retrieve_memory_records()`
  - Searches two namespaces: session summaries + user preferences
  - Returns up to 5 records (3 summaries + 2 preferences)
  - Returns `[]` on any failure (non-blocking)
- `format_memories_for_prompt(memories: list[dict]) -> str`
  - Formats memory records into a markdown block for system prompt injection
  - Returns empty string if no memories

### `tests/test_long_term_memory.py`
Unit tests covering:
- `update_memory.py`: mock `get_memory`/`update_memory`, verify full-replace safety
- `recall_session_details`: mock `list_events`, verify conversation building and sub-agent call
- `memory_retrieval`: mock `retrieve_memory_records`, verify query construction
- `create_agent` with `user_message`: verify memory injection in system prompt
- Edge cases: no memory ID, API errors, empty results

---

## 2. Modified Files

### `agent/main.py`
Changes:
1. Add import: `from agent.memory_retrieval import retrieve_long_term_memories, format_memories_for_prompt`
2. Add import: `from agent.tools.recall_session_details import make_recall_session_details_tool`
3. Change `create_agent` signature: `def create_agent(email: str = "", session_id: str = "", user_message: str = None) -> Agent`
4. After `system_prompt = build_system_prompt()`, add memory injection:
   ```python
   if user_message and email:
       memories = retrieve_long_term_memories(email, user_message)
       memory_block = format_memories_for_prompt(memories)
       if memory_block:
           system_prompt = memory_block + "\n\n" + system_prompt
   ```
5. Add `recall_session_details` tool to the tools list:
   ```python
   recall_tool = make_recall_session_details_tool(email)
   # Add to tools=[..., recall_tool]
   ```

### `agent/runtime_app.py`
Changes:
1. `_get_or_create_agent` signature: add `first_message: str = None`
2. Pass `user_message=first_message` to `create_agent()`
3. In `invoke()`, pass the user's message to `_get_or_create_agent`:
   ```python
   agent = _get_or_create_agent(email, app_session_id, first_message=full_prompt)
   ```
4. Cache key logic: agent is created once per session. The first message triggers memory retrieval. Subsequent messages reuse the cached agent (no re-retrieval needed — memory is already in the system prompt).

**Important:** The cache means memory is only injected on cold start. This is by design — Option B from the design doc. Memories give context for the session, not per-message.

### `agent/system_prompt.py`
No changes needed. The memory block is prepended to the system prompt in `main.py` before passing to Agent(). The system prompt already has a "Long-Term Memory" section describing how to use memories.

---

## 3. Memory Retrieval Flow

```
User sends first message
    ↓
runtime_app.invoke() parses payload
    ↓
_get_or_create_agent(email, session_id, first_message=msg)
    ↓ (cache miss — cold start)
create_agent(email, session_id, user_message=msg)
    ↓
retrieve_long_term_memories(email, msg)
    ├─ retrieve_memory_records(namespace="/sessions/{actorId}/", query=msg, top_k=3)
    └─ retrieve_memory_records(namespace="/users/{actorId}/preferences/", query=msg, top_k=2)
    ↓
format_memories_for_prompt(memories)
    ↓
system_prompt = memory_block + "\n\n" + base_system_prompt
    ↓
Agent created with enriched system prompt + recall_session_details tool
    ↓
Agent streams response (memories available in context)
```

---

## 4. API Calls Used

### `retrieve_memory_records` (new)
```python
client.retrieve_memory_records(
    memoryId=MEMORY_ID,
    searchCriteria={
        "semanticSearch": {
            "queryText": "user's first message",
            "namespace": "/sessions/{actorId}/",
            "topK": 3
        }
    }
)
```

### `list_events` (existing pattern, now in recall tool)
```python
client.list_events(
    memoryId=MEMORY_ID,
    actorId=actor_id,
    sessionId=session_id,
    maxResults=100  # API cap
)
```

### `update_memory` (one-shot script)
```python
client.update_memory(
    memoryId=MEMORY_ID,
    name=current["name"],
    eventExpiryDuration=current["eventExpiryDuration"],
    memoryStrategies=[
        {"userPreferenceMemoryStrategy": {...}},
        {"summaryMemoryStrategy": {...}}
    ]
)
```

---

## 5. Risk Mitigations

| Risk | Mitigation |
|------|------------|
| `update_memory` wipes config | Script reads current config first, dry-run by default |
| Memory retrieval adds latency to cold start | Non-blocking: returns `[]` on failure, logs warning |
| Sub-agent in recall tool costs tokens | Capped at 50 exchanges, uses Sonnet (cheaper) |
| Agent cache means stale memory | By design — memory is session-level context, not per-message |
| `retrieve_memory_records` API shape unknown | Use boto3 directly, handle any API shape gracefully |
| No strategies deployed yet → no memories to retrieve | Graceful: empty results → no injection → agent works normally |

---

## 6. Testing Strategy

### Unit Tests (mocked)
- `test_update_memory_preserves_config` — verify all fields passed through
- `test_update_memory_dry_run` — verify no API call in dry-run
- `test_retrieve_memories_success` — mock API, verify namespace/query
- `test_retrieve_memories_failure` — mock exception, verify empty list returned
- `test_format_memories_empty` — verify empty string
- `test_format_memories_with_records` — verify markdown block
- `test_recall_session_details_success` — mock list_events, verify extraction
- `test_recall_session_details_no_memory_id` — verify error dict
- `test_create_agent_with_memory` — verify system prompt contains memory block
- `test_create_agent_without_memory` — verify system prompt unchanged

### Integration Test (manual, post-deploy)
1. Run `update_memory.py --apply` on dev memory
2. Wait ~5 min for first extraction cycle
3. Start a new session, check CloudWatch logs for memory retrieval
4. Verify agent response references past context (if any exists)

---

## 7. Deployment Order

1. **Deploy `update_memory.py`** — run against dev memory (non-breaking, adds strategies)
2. **Wait 1-2 hours** — let AgentCore extract summaries/preferences from existing events
3. **Deploy code changes** — `main.py`, `runtime_app.py`, new files
4. **Test** — new session should retrieve memories on cold start
5. **Monitor** — CloudWatch logs for memory-related errors

---

## 8. Files Checklist

```
NEW:
  infra/scripts/update_memory.py
  agent/memory_retrieval.py
  agent/tools/recall_session_details.py
  tests/test_long_term_memory.py

MODIFIED:
  agent/main.py          — add memory injection + recall tool
  agent/runtime_app.py   — pass first_message to create_agent
```
