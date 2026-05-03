"""Session management tools for StoryTeller (DynamoDB-backed)."""

import os
import boto3
from strands import tool
from datetime import datetime, timezone

TABLE_NAME = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2")))


def make_name_session_tool(email: str, session_id: str):
    """Create a name_session tool pre-bound with email and session_id."""

    @tool
    def name_session(name: str) -> str:
        """Name or rename the current conversation session.

        Use this ONCE after the first meaningful exchange to give the conversation
        a short, descriptive Hebrew name that captures the video topic (max 50 chars).

        Args:
            name: The descriptive name for the session (in Hebrew, max 50 chars).

        Returns:
            Confirmation of the session naming.
        """
        try:
            table = dynamodb.Table(TABLE_NAME)
            now = datetime.now(timezone.utc).isoformat()

            table.update_item(
                Key={"email": email, "session_id": session_id},
                UpdateExpression="SET #n = :name, updated_at = :now",
                ExpressionAttributeNames={"#n": "name"},
                ExpressionAttributeValues={":name": name, ":now": now},
            )
            return f"Session named: {name}"
        except Exception as e:
            return f"Failed to name session: {str(e)}"

    return name_session
