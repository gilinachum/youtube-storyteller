"""One-time migration: DynamoDB messages → AgentCore Memory events (prod).

Reads all messages from storyteller-messages DDB table, groups by session,
maps email→actorId, and creates events in AgentCore Memory with original timestamps.

Usage:
    python3 scripts/migrate-ddb-to-memory.py [--dry-run]
"""
import boto3
import json
import time
import sys
import logging
from collections import defaultdict
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────
REGION = "us-east-1"
MEMORY_ID = "storytellerProdMemory-57pkTg67x6"
SESSIONS_TABLE = "storyteller-sessions"
MESSAGES_TABLE = "storyteller-messages"
DRY_RUN = "--dry-run" in sys.argv

dynamodb = boto3.resource("dynamodb", region_name=REGION)
agentcore = boto3.client("bedrock-agentcore", region_name=REGION)


def email_to_actor_id(email: str) -> str:
    """Convert email to valid AgentCore actorId."""
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")


def scan_all(table_name: str) -> list:
    """Paginated DDB scan."""
    table = dynamodb.Table(table_name)
    items = []
    last_key = None
    while True:
        kwargs = {}
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        result = table.scan(**kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
    return items


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    # Handle various formats
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        # Fallback
        return datetime.now(timezone.utc)


def migrate():
    log.info("=" * 60)
    log.info("DDB → AgentCore Memory Migration")
    log.info(f"  Region:    {REGION}")
    log.info(f"  Memory ID: {MEMORY_ID}")
    log.info(f"  Dry run:   {DRY_RUN}")
    log.info("=" * 60)

    # 1. Build session_id → email mapping
    log.info("\n📋 Scanning sessions table...")
    sessions = scan_all(SESSIONS_TABLE)
    session_email = {s["session_id"]: s["email"] for s in sessions}
    log.info(f"   Found {len(sessions)} sessions, {len(set(session_email.values()))} unique emails")

    # 2. Scan all messages
    log.info("\n📋 Scanning messages table...")
    all_msgs = scan_all(MESSAGES_TABLE)
    log.info(f"   Found {len(all_msgs)} messages")

    # 3. Group by session, sort by timestamp
    by_session = defaultdict(list)
    for m in all_msgs:
        by_session[m["session_id"]].append(m)

    log.info(f"   Across {len(by_session)} sessions")

    # 4. Migrate
    migrated = 0
    skipped = 0
    errors = 0
    sessions_done = 0

    for session_id, messages in sorted(by_session.items()):
        email = session_email.get(session_id)
        if not email:
            log.warning(f"   ⚠️  No email for session {session_id} ({len(messages)} msgs) — skipping")
            skipped += len(messages)
            continue

        actor_id = email_to_actor_id(email)
        messages.sort(key=lambda m: m.get("timestamp", ""))

        for i, msg in enumerate(messages):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            ts_str = msg.get("timestamp", "")
            ts = parse_timestamp(ts_str)

            # Build the payload in the same format the session manager uses
            # (Converse API message wrapped in JSON)
            converse_message = {
                "message": {
                    "role": role,
                    "content": [{"text": content}]
                },
                "message_id": i,
                "created_at": ts_str,
            }

            payload = [{
                "conversational": {
                    "role": role.upper(),
                    "content": {
                        "text": json.dumps(converse_message, ensure_ascii=False)
                    }
                }
            }]

            if DRY_RUN:
                log.info(f"   [DRY] {session_id[:12]}… | {role:9s} | {ts_str[:19]} | {content[:50]}…")
                migrated += 1
                continue

            # Create event with original timestamp
            for attempt in range(3):
                try:
                    agentcore.create_event(
                        memoryId=MEMORY_ID,
                        actorId=actor_id,
                        sessionId=session_id,
                        eventTimestamp=ts,
                        payload=payload,
                    )
                    migrated += 1
                    break
                except Exception as e:
                    if "Throttl" in type(e).__name__ or "Throttl" in str(e):
                        wait = 2 ** (attempt + 1)
                        log.warning(f"   ⏳ Throttled, waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        log.error(f"   ❌ Failed: {session_id[:12]}… {role} — {e}")
                        errors += 1
                        break

            # Rate limit safety — 100ms between calls
            time.sleep(0.1)

        sessions_done += 1
        if not DRY_RUN:
            log.info(f"   ✅ Session {session_id[:12]}… ({len(messages)} msgs, actor={actor_id})")

    # Summary
    log.info("\n" + "=" * 60)
    log.info("Migration Summary")
    log.info(f"  Sessions processed: {sessions_done}")
    log.info(f"  Messages migrated:  {migrated}")
    log.info(f"  Messages skipped:   {skipped}")
    log.info(f"  Errors:             {errors}")
    if DRY_RUN:
        log.info("\n  ⚠️  DRY RUN — no events were created")
    log.info("=" * 60)


if __name__ == "__main__":
    migrate()
