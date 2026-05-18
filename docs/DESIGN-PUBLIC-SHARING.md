# Design: Public Session Sharing & URL Routing

_Draft v1 | 2026-05-09_

---

## Summary

Add two related features:

1. **Public (read-only) session sharing** — Generate a shareable link. Anyone logged in with the link can view the session (read-only, not in their sidebar).
2. **URL-based session routing** — The browser URL reflects the active session (`/s/{session_id}`), enabling bookmarks and direct links.

---

## Current State

| Aspect | Today |
|--------|-------|
| Sharing | By email only → full read+write, appears in recipient's sidebar |
| URL | Single-page, no routing. URL is always `/` regardless of active session |
| Access model | `shared_with[]` list in DDB → explicit per-user |

---

## Proposed Model (Google Docs analogy)

| Access Level | How Granted | Permissions | In Sidebar? |
|--------------|-------------|-------------|-------------|
| **Owner** | Created the session | Read + Write | ✅ Yes |
| **Collaborator** | Shared by email (existing feature) | Read + Write | ✅ Yes (👥 icon) |
| **Viewer (new)** | Has the link + session is "public" | Read only | ❌ No |

A session gains a new attribute: **`visibility`**
- `"private"` (default) — only owner + explicit collaborators
- `"public"` — anyone logged in with the session URL can view (read-only)

---

## User Flow

### Making a Session Public

1. Owner opens share modal (existing UI)
2. New toggle/section: **"כל מי שיש לו את הקישור יכול לצפות"** (Anyone with the link can view)
3. Toggle switches `visibility` → `public`
4. UI shows the shareable URL: `https://{domain}/s/{session_id}`
5. Copy-link button

### Viewing a Public Session

1. Recipient gets a link: `https://{domain}/s/{session_id}`
2. If not logged in → redirected to login → then back to the link
3. Session opens in read-only mode:
   - Messages displayed normally
   - Input bar hidden (or disabled with "שיחה לקריאה בלבד" label)
   - Session does NOT appear in their sidebar
   - They see a "viewer" indicator

### Bookmarking

- URL always updates to `/s/{session_id}` when a session is active
- Browser back/forward works
- Bookmark any session (own, shared, or public)
- Landing on `/` → no session selected (welcome/new session state)

---

## Technical Design

### 1. Frontend: Client-Side Routing

Add lightweight routing (no react-router needed — use `window.history` + popstate):

```
/                → no session selected (current default state)
/s/{session_id}  → load and display this session
/auth/callback   → OAuth callback (already handled)
```

**Implementation:**
- On session select → `history.pushState({}, '', '/s/' + sessionId)`
- On page load → parse URL, if `/s/{id}` → load that session
- On popstate → sync active session with URL
- CloudFront viewer-request function already rewrites unknown paths to `/index.html` (SPA pattern) ✅

### 2. Backend: Visibility & Access Control

**DDB Changes — Sessions Table:**
```
New attribute: visibility (String) — "private" | "public" (default: "private")
```

**New API endpoint:**
```
PATCH /sessions/{id}/visibility
Body: { "visibility": "public" | "private" }
Auth: Owner only
```

**Modified: GET /sessions/{id}**

Current logic:
1. Look up by owner email
2. If not found, scan `shared_with`

New logic:
1. Look up by owner email → full access
2. Check `shared_with` → full access (collaborator)
3. Check `visibility == "public"` → read-only access
4. If none match → 403

Response includes a new field: `"access": "owner" | "collaborator" | "viewer"`

### 3. API Changes Summary

| Endpoint | Change |
|----------|--------|
| `GET /sessions/{id}` | Add visibility check; return `access` field |
| `PATCH /sessions/{id}/visibility` | **New** — toggle public/private |
| `POST /chat-stream` | Reject if user is viewer-only for that session |
| `DELETE /sessions/{id}/share/{email}` | **New** — remove a collaborator |
| `GET /sessions` | No change (public sessions never appear in others' lists) |

### 4. Frontend: ShareModal Enhancement

```
┌─────────────────────────────────────┐
│  שיתוף שיחה                    ✕   │
│                                     │
│  ┌─ גישה כללית ─────────────────┐  │
│  │ ○ פרטי (רק אתה ומי ששיתפת)  │  │
│  │ ● כל מי שיש לו קישור (צפייה) │  │
│  │                               │  │
│  │ 🔗 https://app.../s/abc123    │  │
│  │         [ העתק קישור ]        │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌─ שיתוף לפי אימייל ──────────┐  │
│  │ [email input]    [שתף]       │  │
│  │ משותף עם:                    │  │
│  │ • user@example.com           │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### 5. Read-Only View UI

When `access === "viewer"`:
- Chat input area replaced with a banner: "📖 שיחה לקריאה בלבד"
- No share button
- No file upload
- Header shows session name + "צפייה" badge
- Voice recording disabled

### 6. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Unauthenticated access | Must be logged in (Cognito JWT required). No anonymous viewing. |
| Enumeration / guessing | Session IDs are UUIDs — 2^122 bits of entropy |
| Revoking access | Owner toggles visibility back to "private" → instant |
| Link leaks | Only grants read access; no PII exposed beyond chat content |
| Rate limiting | Standard API Gateway throttling applies |

### 7. DDB Query Pattern for Public Access

Current `GET /sessions/{id}` does a scan for shared sessions. For public access:

```python
# After failing owner + shared_with checks:
# Direct get by session_id (need GSI or scan)
# Option A: GSI on session_id (recommended)
# Option B: Scan with filter (acceptable for single-session lookups)
```

**Recommendation:** Add a GSI on `session_id` (GSI-SessionId) for direct lookups by session ID regardless of owner. This also benefits the shared session lookup (currently a scan).

---

## Implementation Plan

### Phase 1: URL Routing (no backend changes)
1. Add `pushState`/`popState` handling in App.tsx
2. Parse `/s/{id}` on load → set active session
3. Update URL on session select
4. Test with CloudFront SPA rewrite (already in place)

### Phase 2: Visibility Backend
1. Add `visibility` attribute to sessions table
2. Add `PATCH /sessions/{id}/visibility` endpoint
3. Modify `GET /sessions/{id}` access logic
4. Add GSI on session_id for direct lookups
5. Block chat-stream for viewer-only users

### Phase 3: Frontend Sharing UI
1. Enhance ShareModal with visibility toggle + copy link
2. Add remove-collaborator button (✕ next to each email)
3. Read-only view mode (hide input, show banner)
4. Viewer badge in header
5. Export button visible for viewers

---

## Decisions (2026-05-09)

1. **Real-time for viewers:** No — not worth the extra work. Viewers see a snapshot; refresh to get updates.
2. **Remove collaborators:** Yes — add unshare (remove email) alongside this feature.
3. **Export for viewers:** Yes — viewers can download/export session content.
4. **Visibility model:** Binary private/public is fine. "Public" = anyone logged in with the link.

---

_Next: Get Gili's feedback on open questions, then implement Phase 1 → 2 → 3._
