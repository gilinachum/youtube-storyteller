# StoryTeller — TODO / Backlog

## UX

- [ ] **Parallel input while agent writes** — Allow user to type a new message while the agent is still streaming its response (don't block the input textarea during generation)
- [ ] **Auto LTR for English input** — Default textarea is RTL (Hebrew). When user types in English, switch textarea direction to LTR dynamically
- [ ] **Edit last message & regenerate** — Let user edit their last message and get a fresh agent response.
  - **⚠️ Prerequisite: fix conversation persistence first (see below)**
  - Frontend: edit icon on last user bubble → editable textarea → submit calls `POST /sessions/{id}/edit` with `{message_index, new_text}`
  - Backend: truncate message history to that turn, replace user message, re-invoke agent
  - Consider: keep discarded branches for undo/history, or discard initially

- [ ] **🔴 Fix conversation persistence — tool calls are lost** — **Current gap:** `chat.py` only saves `role: user` and `role: assistant` content strings to DynamoDB. Tool calls (`tool_use`), tool results (`tool_result`), and any file content the agent read are **not persisted**. On every invocation, `create_agent()` starts fresh and history is reconstructed as plain text concatenation — not proper Converse API message format. This means:
  - Agent has no memory of what tools it used or what files it read
  - Research results, file contents, uploaded document analysis — all gone after Lambda ends
  - Edit/regenerate would replay without the context that shaped the original response
  - Cross-session resume is superficial (text summary, not full context)
  
  **Solution: Strands SessionManager + AgentCore Memory**
  - Replace manual DynamoDB message storage with `AgentCoreMemorySessionManager`
  - This persists the **full Converse API message array** including `tool_use`/`tool_result` blocks
  - `append_message()` is called by Strands on every message (user, assistant, tool) automatically
  - `initialize()` restores the full message array on session resume — agent picks up exactly where it left off
  - AgentCore Memory STM handles conversation persistence; LTM strategies (summaries, preferences, facts) give cross-conversation awareness for free
  - Edit/regenerate then becomes: call `list_messages()` to get the full array, truncate to the edit point, re-invoke
  - This also enables the **folders & cross-conversation knowledge** TODO — LTM semantic strategy indexes facts across sessions
  
  **Migration path:**
  1. Create an AgentCore Memory resource with STM + LTM strategies
  2. Replace `create_agent()` to accept a `session_manager` parameter
  3. Remove manual `msgs_table.put_item()` calls — Strands handles it
  4. Keep `storyteller-messages` DynamoDB table as read-only fallback during migration
  5. Update history loading to use `session_manager.initialize()` instead of manual query+concat
- [ ] **Research evidence bubbles** — When the agent conducts research, surface findings as small clickable evidence bubbles (similar to ChatGPT's citation chips) so users can inspect sources

## Content Platform Expansion

- [ ] **Multi-format content support** — Expand beyond YouTube videos to support: 1:M webinars, physical sessions, blog posts, social media posts, and combinations where one promotes the other. StoryTeller should suggest how to structure and cross-link content across formats
- [ ] **Dynamic system prompts per content type** — Each media type gets its own system prompt loaded dynamically. **Open question:** should these be skill-style prompt files loaded at session start, or retrieved via tool calls at runtime?
  - *Option A: Skills/prompt files* — simpler, loaded once per session, but less flexible if the user switches content types mid-conversation
  - *Option B: Tool-call retrieval* — more flexible (agent fetches the relevant prompt when needed), supports multi-format sessions, but adds latency per retrieval and complexity
  - *Recommendation:* Hybrid — load a base system prompt, then use a `get_content_prompt(type)` tool that returns the specialized prompt for a given content type. This keeps the base prompt lean and lets the agent pull in what it needs per turn. The prompts themselves live as files (easy to edit/version) but are served dynamically via tool call.

## Knowledge & Organization

- [ ] **Folders and conversations** — Support creating folders (optionally shared) and multiple conversations within them. The agent should have cross-conversation awareness:
  - *Option A: Direct access* — agent can read other conversations in the same folder
  - *Option B: RAG* — conversations are indexed and retrieved semantically
  - *Recommendation:* RAG with optional direct access. Index all conversations in a folder into a vector store (per-folder). Agent gets a `search_folder(query)` tool. For explicit references ("use what we discussed in conversation 2"), allow direct retrieval by conversation ID.

## Agent Behavior

- [ ] **Prioritize user-provided input over research** — System prompt must enforce: if the user provides an input file (bootstrap, brief, URL, etc.) and the agent fails to load/read it, the agent MUST stop and ask the user before proceeding. Never silently skip user input and fall back to internet research. Specifically:
  - If a provided URL/file fails to load → tell the user it failed, ask them to re-provide it (paste content, upload file, etc.)
  - Never auto-substitute research for user-provided input without explicit permission
  - User-provided context always takes priority over agent's own research
  - Research should supplement user input, not replace it
  - Ask for confirmation before investing effort in a plan if key inputs are missing

## Infrastructure

- [ ] **Private auth overlay repo** — Gili to provide private repo details for Amazon-internal auth (Federate/Midway). Clone into `infra-private/`
