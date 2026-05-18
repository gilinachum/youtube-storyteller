# Long-Term Memory for StoryTeller — Implementation Design

_Version 1.0 | 2026-05-10 | Gili (Today2008)_

---

## 1. Current State

**Memory ID:** `storytellerDevMemory-rStdOCAQvm`  
**Mode:** Short-term memory only (Converse events, 365-day TTL, no strategies)  
**Actors:** User emails converted via `email_to_actor_id()`  
**Existing:** Bare memory storage — summary/userpreference extraction is **not** configured.

Session flow: `runtime_app.py` → AgentCoreMemorySessionManager → `CreateEvent` on each turn.

---

## 2. Architecture Decisions (Confirmed)

### Two-Tier Memory System
```
                ┌─────────────────────────────────────┐
                │         LONG-TERM MEMORY (LTM)       │
                │                                     │
 User asks →    │  ┌─────────────────────────────┐    │   Get exact
 "same style    │  │ Session Summaries           │    │   details
 as K8s"       │  │ - What happened              │    │   via sub-agent
                │  │ - Which session ID           │    │
                │  └────────────┬────────────────┘    │
                │               │ semantic search      │
                │               ▼                      │
                │  ┌─────────────────────────────┐    │
                │  │ User Preferences           │    │
                │  │ - Content style (L200/…)   │    │
                        ▲ ▲)                 │
                │  │ - Thumbnail style        │    │
                └────────────┴─────────────────────────────┘
                               │
                               │ found session_id="K8s-session-123"
                               │
                               ▼
                ┌─────────────────────────────────────────────┐
                │        SHORT-TERM MEMORY (STM)             │
                │                                            │
                │  ┌─────────────────────────────────────┐  │
                │  │ recall_session_details tool         │  │
                │  │ - Load full conversation            │  │
                │  │   via ListEvents                    │  │
                │  │ - Sub-agent extracts                │  │
                │  │   exact details                     │  │
                │  └─────────────────────────────────────┘  │
                └─────────────────────────────────────────────┘
```

**Key decisions:**
- **Retrieval trigger:** Option B — no cold-open retrieval. Wait for user's first message, then `RetrieveMemoryRecords` with semantic search matched to their intent.
- **Memory strategies:** Start with built-in → Session Summaries + User Preferences
- **Custom strategy later:** For Hebrew-aware + YouTube-specific extraction
- **Boundary:** Long-term memory stores "what we talked about." Raw details come from short-term memory via `recall_session_details` tool.

---

## 3. Implementation Phases

### Phase 1: Add Strategies to Existing Memory (1 day)
**Goal:** Enable long-term extraction without breaking current flows.

#### Step 1 — Update Memory Configuration
`infra/scripts/update_memory.py` (new):

```python
import boto3
import os

region = os.environ.get("AWS_REGION", "us-west-2")
client = boto3.client("bedrock-agentcore-control", region_name=region)

MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID", "storytellerDevMemory-rStdOCAQvm")

def update_memory_with_strategies():
    """Update memory resource to add session summary + user preference strategies."""
    
    # Get current config first (critical — UpdateMemory is FULL REPLACE, not PATCH)
    current = client.get_memory(memoryId=MEMORY_ID)
    existing_kms_key = current.get("encryptionKeyArn")
    existing_tags = current.get("tags", {})
    existing_event_expiry = current.get("eventExpiryDuration", "P365D")
    
    # Add new strategies while keeping existing short-term memory behavior
    response = client.update_memory(
        memoryId=MEMORY_ID,
        name="storytellerMemory",  # keep same
        eventExpiryDuration=existing_event_expiry,
        encryptionKeyArn=existing_kms_key,
        tags=existing_tags,
        memoryStrategies=[
            {
                "userPreferenceMemoryStrategy": {
                    "name": "StoryTellerPreferences",
                    "description": "Extracts user's content style, audience, thumbnail preferences, structural choices.",
                    "namespaceTemplates": ["/users/{actorId}/preferences/"]
                }
            },
            {
                "summaryMemoryStrategy": {
                    "name": "StoryTellerSessionSummaries", 
                    "description": "Creates concise summaries of each planning session.",
                    "namespaceTemplates": ["/sessions/{actorId}/{sessionId}/"]
                }
            }
        ]
    )
    return response

if __name__ == "__main__":
    update_memory_with_strategies()
```

**Note:** Must read `GetMemory` first — `UpdateMemory` is full replacement, not patch. Must preserve encryption key, tags, expiration.

#### Step 2 — Memory Retrieval Integration in `runtime_app.py`
Insert after agent creation in `_get_or_create_agent`:

```python
def _get_or_create_agent(email: str, app_session_id: str) -> "Agent":
    cache_key = f"{email}:{app_session_id}"
    if cache_key in _agents:
        return _agents[cache_key]
    
    agent = create_agent(email=email, session_id=app_session_id)
    
    # NEW: Memory retrieval (Option B — deferred to first user message)
    # We'll modify create_agent to accept 'initial_message' param later
    # For now, flag that agent needs memory injection on first turn
    
    # Rest of existing function...
```

Better pattern: Pass memory retrieval into `create_agent` after we have the first user message:

```python
def create_agent(email: str, session_id: str, user_message: str = None) -> Agent:
    # ... existing code
    
    # If user_message provided — retrieve long-term memories
    if user_message and memory_id:
        memories = retrieve_long_term_memories(email, user_message)
        if memories:
            system_prompt = add_memories_to_prompt(system_prompt, memories)
    
    return Agent(...)
```

---

### Phase 2: Enhanced Memory Injection System (2 days)
**Goal:** Seamless memory injection without breaking streaming.

#### Files to Modify:

**1. `agent/main.py`** — Add `retrieve_long_term_memories()`:
```python
from bedrock_agentcore.memory.session import MemorySessionManager

def retrieve_long_term_memories(email: str, query_text: str):
    """Retrieve relevant long-term memories based on user's first message."""
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id:
        return []
    
    try:
        actor_id = email_to_actor_id(email)
        session_manager = MemorySessionManager(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id="dummy",  # Not session-specific — cross-session search
            region_name=os.environ.get("AWS_REGION", "us-west-2")
        )
        
        # Search summaries for this user
        memories = session_manager.search_long_term_memories(
            namespace=f"/sessions/{actor_id}/",
            query=query_text,  # The user's first message
            top_k=3
        )
        # Search user preferences
        prefs = session_manager.search_long_term_memories(
            namespace=f"/users/{actor_id}/preferences/",
            query=query_text,
            top_k=2
        )
        return memories + prefs
    except Exception as e:
        logger.warning(f"Failed to retrieve long-term memories: {e}")
        return []
```

**2. `agent/runtime_app.py`** — Modify `_get_or_create_agent` to accept `first_message`:
```python
def _get_or_create_agent(email: str, app_session_id: str, first_message: str = None):
    # ... existing code
    
    # Pass first_message to create_agent for memory injection
    agent = create_agent(email=email, session_id=app_session_id, user_message=first_message)
    
    # Rest remains same
```

**3. `agent/system_prompt.py`** — Add `add_memories_to_prompt()`:
```python
def add_memories_to_prompt(base_prompt: str, memories: list) -> str:
    if not memories:
        return base_prompt
    
    memory_block = "\n\n# Long-Term Memory Context\n"
    memory_block += "These memories from past conversations may be relevant:\n"
    for i, mem in enumerate(memories[:3], 1):
        # Assume memory record has 'text' attribute
        mem_text = mem.get("text", str(mem))
        memory_block += f"* {mem_text}\n"
    
    memory_block += "\nReference these memories naturally in your response when relevant.\n"
    
    # Insert before the methodology section
    if "# Conversation Flow - IMPORTANT" in base_prompt:
        return base_prompt.replace("# Conversation Flow - IMPORTANT", memory_block + "# Conversation Flow - IMPORTANT")
    return base_prompt + memory_block
```

---

### Phase 3: `recall_session_details` Tool (2 days)
**Goal:** Implement the on-demand detail extraction pattern.

**File:** `/home/ec2-user/.openclaw/workspace/projects/storyteller/agent/tools/recall_session_details.py`

```python
"""recall_session_details tool — loads a past session via short-term memory and extracts details."""

import os
import boto3
from strands import tool
from strands import Agent
from strands.models import BedrockModel
import logging

logger = logging.getLogger(__name__)

# Memory client for listing sessions and events
region = os.environ.get("AWS_REGION", "us-west-2")
client = boto3.client("bedrock-agentcore", region_name=region)

# Sub-agent for extraction
_EXTRACTION_AGENT = None

def _get_extraction_agent():
    global _EXTRACTION_AGENT
    if _EXTRACTION_AGENT is None:
        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-6",
            region_name=region,
            max_tokens=2000,
        )
        system_prompt = """You are an extraction assistant.
Given a conversation history and a query about specific details, extract exactly what's asked for.
Return structured information in JSON when possible.
Query examples:
- "thumbnail design details: colors, fonts, layout, prompt used"
- "research findings about quantum computing"
- "video structure outline (timestamps, sections)"
- "script draft exported from this session"
"""
        _EXTRACTION_AGENT = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=[]
        )
    return _EXTRACTION_AGENT

def _email_to_actor_id(email: str) -> str:
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")

def make_recall_session_details_tool(email: str):
    """Factory returning a tool bound to the user's email."""

    @tool
    def recall_session_details(session_id: str, query: str) -> dict:
        """Load full conversation from a past session and extract specific details.
        
        Use this when the user references something from a specific past session
        (e.g., "same thumbnail style as the K8s session"). First identify the session ID
        via long-term memory search, then call this tool with the session_id and
        a precise description of what details to extract.
        
        Args:
            session_id: The AgentCore session ID (from memory search)
            query: What details to extract (e.g., "thumbnail design: colors, fonts, layout, Gemini prompt")
            
        Returns:
            Structured details extracted from the session conversation.
        """
        memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
        if not memory_id:
            return {"error": "AgentCore Memory not configured"}
        
        actor_id = _email_to_actor_id(email)
        
        try:
            # Load all events from that session (short-term memory)
            events = []
            next_token = None
            while True:
                kwargs = {
                    "memoryId": memory_id,
                    "actorId": actor_id,
                    "sessionId": session_id,
                    "maxResults": 50
                }
                if next_token:
                    kwargs["nextToken"] = next_token
                
                response = client.list_events(**kwargs)
                events.extend(response.get("events", []))
                next_token = response.get("nextToken")
                if not next_token:
                    break
            
            # Build conversation text
            conversation = []
            for event in events:
                for payload in event.get("payload", []):
                    conv = payload.get("conversational")
                    if conv:
                        role = conv.get("role", "").lower()
                        content = conv.get("content", {}).get("text", "")
                        if role in ("user", "assistant") and content:
                            conversation.append(f"{role}: {content}")
            
            if not conversation:
                return {"error": "No conversation found for that session"}
            
            # Pass to extraction sub-agent
            full_conv = "\n".join(conversation[:50])  # Limit tokens
            agent = _get_extraction_agent()
            
            prompt = f"""Extract the following details from this conversation:
Query: {query}

Conversation:
{full_conv}

Return only the extracted details, structured if possible."""
            
            extracted = agent(prompt)
            return {
                "session_id": session_id,
                "query": query,
                "extracted": extracted,
                "conversation_snippet": full_conv[:500],  # for debugging
                "event_count": len(events)
            }
            
        except Exception as e:
            logger.error(f"Failed to recall session details: {e}", exc_info=True)
            return {"error": str(e)}
    
    return recall_session_details
```

**Integration in `main.py`:**
```python
# Add to imports
from agent.tools.recall_session_details import make_recall_session_details_tool

def create_agent(email: str, session_id: str, user_message: str = None) -> Agent:
    # ... existing code
    
    recall_tool = make_recall_session_details_tool(email)  # NEW
    
    tools = [
        # ... existing tools
        recall_tool,  # ADD HERE
    ]
    
    # ... rest
```

---

### Phase 4: Agent Memory-Aware Flow (1 day)
**Goal:** Teach agent to use memory naturally.

**Update system prompt (already added in REQUIREMENTS.md):**

Add concrete examples:
```
## Memory Examples

When you retrieve relevant memories, use them like this:

1. **Continuity:**
   User: "חושב על סרטון חדש"
   Memory: "ב-2026-05-09 עבדנו על סרטון קוברנטיס עם זווית 'למה החברה שלך לא צריכה K8s'"
   Response: "שלום! בפעם האחרונה עבדנו על נושא קוברנטיס — רוצה להמשיך עם זה או נושא חדש?"

2. **Preferences:**
   User: "אין לי רעיונות"
   Memory: "המשתמש מעדיף סרטונים L200 עם הומור והוק ישיר"
   Response: "בוא נבדוק קודם באיזה רמה — אתה רגיל ל-L200 עם הומור. יש לך נושא שאתה רוצה לחקור?"

3. **Cross-session detail:**
   User: "אותו סטייל טאמבנייל כמו הסשן על קוברנטיס"
   Response: "חפש ב-long-term memory את סשן הקוברנטיס → מצא session_id → call recall_session_details(session_id, 'thumbnail design: colors, fonts, layout, prompt')"
```

---

## 4. Agent Flow with Memory (End State)

### User Joins Session
```
Frontend → API GW → runtime_app.py/invoke

1. Parse payload (email, session_id, first_message)
2. _get_or_create_agent(email, session_id, first_message)
3. Agent creation:
   a. Retrieve long-term memories using first_message as query
   b. Inject memories into system prompt
   c. Create agent with recall_session_details tool
4. Agent streams response (already references memories naturally)
```

### Cross-Session Detail Request
```
User: "רוצה אותו סטייל תמונה ממוזערת כמו סשן הקוברנטיס"

1. Agent internally calls retrieve_long_term_memories("cookie", "kubernetes session")
   → Gets summary saying "Session K8s-session-123 was about K8s"
2. Agent calls recall_session_details("K8s-session-123", "thumbnail design details: colors, fonts, layout, prompt used, user photo")
   → Tool loads full conversation via ListEvents
   → Sub-agent extracts exact prompt + style
   → Returns {"colors": "red/white", "font": "Impact", "prompt": "..."}
3. Agent uses details to guide design_thumbnail tool
4. Agent responds: "אני זוכר את העיצוב עם רקע אדום וגופן Impact. אעצב אחד דומה!"
```

---

## 5. Memory Strategy Configurations

### 1. Built-in User Preferences
```json
{
  "userPreferenceMemoryStrategy": {
    "name": "StoryTellerPreferences",
    "namespaceTemplates": ["/users/{actorId}/preferences/"],
    "description": "Extracts YouTube content preferences"
  }
}
```

**Extracts:**
- Content level (L100-L400)
- Tone preference (humor/serious)
- Structure preference (hook-first/story-arc)
- Thumbnail style (colors, layout, text style)
- Audience targeting (technical/business)

### 2. Built-in Session Summaries
```json
{
  "summaryMemoryStrategy": {
    "name": "StoryTellerSessionSummaries",
    "namespaceTemplates": ["/sessions/{actorId}/{sessionId}/"],
    "description": "Summarizes video planning sessions"
  }
}
```

**Extracts:**
- Main topic covered
- Decisions made (which angle chosen)
- Plan exported (yes/no)
- Thumbnail created (yes/no)
- Session duration/outcome

### 3. Future Custom Strategy
Custom extraction/consolidation prompts for Hebrew-aware YouTube facts:
- Channel metrics (subscriber count, niche)
- Competitor analysis findings
- Successful thumbnail prompt patterns
- Video performance learnings

---

## 6. Key API Calls Reference

### Update Memory (add strategies)
```python
# Critical: Read current first
current = client.get_memory(memoryId=MEMORY_ID)
response = client.update_memory(
    memoryId=MEMORY_ID,
    name=current["name"],
    eventExpiryDuration=current["eventExpiryDuration"],
    encryptionKeyArn=current.get("encryptionKeyArn"),
    tags=current.get("tags", {}),
    memoryStrategies=[...]  # NEW STRATEGIES
)
```

### Retrieve Memories (semantic search)
```python
memories = client.retrieve_memory_records(
    memoryId=MEMORY_ID,
    searchCriteria={
        "searchQuery": "user's first message or topic",
        "namespace": "/users/actor123/preferences/",
        "topK": 3
    }
)
```

### List Events (short-term memory)
```python
events = client.list_events(
    memoryId=MEMORY_ID,
    actorId=actor_id,
    sessionId="K8s-session-123",
    maxResults=100
)
```

---

## 7. Testing Plan

### Unit Tests
1. `test_retrieve_long_term_memories.py` — Mock AgentCore API, verify query building
2. `test_recall_session_details.py` — Mock ListEvents, verify extraction flow
3. `test_memory_injection.py` — Verify system prompt gets memory block correctly

### Integration Tests (Live)
1. **Memory retrieval flow:**
   - Deploy updated memory with strategies
   - Wait 5 min for first extraction cycle
   - Start a session, check logs for memory retrieval
   
2. **Cross-session detail:**
   - Create session A (thumbnail + plan)
   - Wait for summary extraction
   - Start session B, ask for "same style as session A"
   - Verify agent finds session ID and calls recall tool

### Monitoring Metrics
- **Memory hit rate:** % of sessions where relevant memories found
- **Recall tool usage:** Count of cross-session detail requests
- **Extraction latency:** Time from user message to memory injection
- **Sub-agent extraction success rate:** % of recall calls returning useful details

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **UpdateMemory wipes config** | Always read current config first, preserve all fields |
| **Memory extraction delay** (async) | UX: Don't promise immediate recall for brand new sessions |
| **Short-term memory TTL (365d)** | Plan migration or accept that old sessions lose detail extraction |
| **Sub-agent token limit** | Cap loaded conversation to ~50 exchanges per recall |
| **Memory poisoning** | Input validation in `CreateEvent`, don't trust user-provided metadata |

---

## 9. Files Summary

**New files:**
```
agent/tools/recall_session_details.py           # On-demand extraction tool
infra/scripts/update_memory.py                  # CLI to add strategies
tests/test_long_term_memory.py                  # Unit/integration tests
docs/DESIGN-LONG-TERM-MEMORY.md                 # This document
```

**Modified files:**
```
agent/main.py                                   # Add memory retrieval in create_agent()
agent/runtime_app.py                            # Pass first_message to create_agent
agent/system_prompt.py                          # Already updated (memory guidance)
docs/REQUIREMENTS.md                            # Already updated (Section 14)
deploy.sh (.env.dev)                            # No changes — memory ID already present
```

---

## 10. Deployment Checklist

### Pre-deploy
- [ ] Backup current memory config (`GetMemory` → JSON dump)
- [ ] Turn on extraction in dev memory via `update_memory.py`
- [ ] Wait 2 hours for first extractions to complete
- [ ] Test memory retrieval flow manually
- [ ] Write tests for new components

### Deploy Phased
- [ ] **Phase 1:** Deploy memory update script, run it (non-breaking)
- [ ] **Phase 2:** Deploy memory retrieval + injection 
- [ ] **Phase 3:** Deploy `recall_session_details` tool
- [ ] **Phase 4:** Update system prompt with examples

### Post-deploy
- [ ] Monitor CloudWatch logs for memory-related errors
- [ ] Track user feedback on memory continuity ("did it remember me?")
- [ ] Analyze recall tool usage patterns

---

**Architects:** Gili (Today2008)  
**Status:** Design ready for implementation  
**Next:** Start with `update_memory.py` to enable strategies on existing memory