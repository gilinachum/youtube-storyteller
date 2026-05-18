"""Tests for long-term memory: retrieval, injection, recall tool, and update script."""

import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("AGENTCORE_MEMORY_ID", "test-memory-id")
os.environ.setdefault("AWS_REGION", "us-west-2")
os.environ.setdefault("MESSAGES_TABLE", "test-messages")
os.environ.setdefault("SESSIONS_TABLE", "test-sessions")
os.environ.setdefault("UPLOAD_BUCKET", "test-uploads")


# ── Memory Retrieval Tests ──────────────────────────────────────────────────


class TestRetrieveLongTermMemories:
    """Test retrieve_long_term_memories() — semantic search against AgentCore Memory."""

    @patch("agent.memory_retrieval.boto3")
    def test_returns_records_from_both_namespaces(self, mock_boto3):
        """Should search summaries and preferences, merging results."""
        from agent.memory_retrieval import retrieve_long_term_memories

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # First call: session summaries
        mock_client.retrieve_memory_records.side_effect = [
            {
                "memoryRecordSummaries": [
                    {
                        "content": {"text": "Session about K8s video planning"},
                        "score": 0.92,
                        "namespaces": ["/sessions/gili-at-amazon-com/sess-123/"],
                        "memoryStrategyId": "strategy-1",
                    }
                ]
            },
            # Second call: user preferences
            {
                "memoryRecordSummaries": [
                    {
                        "content": {"text": "Prefers L200 with humor and direct hooks"},
                        "score": 0.85,
                        "namespaces": ["/users/gili-at-amazon-com/preferences/"],
                        "memoryStrategyId": "strategy-2",
                    }
                ]
            },
        ]

        result = retrieve_long_term_memories("gili@amazon.com", "I want to make a K8s video")

        assert len(result) == 2
        assert "K8s" in result[0]["text"]
        assert result[0]["score"] == 0.92
        assert "L200" in result[1]["text"]

        # Verify both namespace searches happened
        assert mock_client.retrieve_memory_records.call_count == 2

    @patch("agent.memory_retrieval.boto3")
    def test_returns_empty_on_client_error(self, mock_boto3):
        """Should return [] on AWS API errors (non-blocking)."""
        from agent.memory_retrieval import retrieve_long_term_memories
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.retrieve_memory_records.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Memory not found"}},
            "RetrieveMemoryRecords",
        )

        result = retrieve_long_term_memories("gili@amazon.com", "hello")
        assert result == []

    def test_returns_empty_when_no_memory_id(self):
        """Should return [] when AGENTCORE_MEMORY_ID is not set."""
        from agent.memory_retrieval import retrieve_long_term_memories

        with patch.dict(os.environ, {"AGENTCORE_MEMORY_ID": ""}):
            result = retrieve_long_term_memories("gili@amazon.com", "hello")
            assert result == []

    def test_returns_empty_for_missing_email(self):
        """Should return [] when email is empty."""
        from agent.memory_retrieval import retrieve_long_term_memories

        result = retrieve_long_term_memories("", "hello")
        assert result == []

    @patch("agent.memory_retrieval.boto3")
    def test_filters_empty_text_records(self, mock_boto3):
        """Should filter out records with empty text content."""
        from agent.memory_retrieval import retrieve_long_term_memories

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.retrieve_memory_records.side_effect = [
            {
                "memoryRecordSummaries": [
                    {"content": {"text": ""}, "score": 0.5, "namespaces": [], "memoryStrategyId": "s1"},
                    {"content": {"text": "Real memory"}, "score": 0.9, "namespaces": [], "memoryStrategyId": "s1"},
                ]
            },
            {"memoryRecordSummaries": []},
        ]

        result = retrieve_long_term_memories("gili@amazon.com", "hello")
        assert len(result) == 1
        assert result[0]["text"] == "Real memory"


class TestFormatMemoriesForPrompt:
    """Test format_memories_for_prompt() — markdown block generation."""

    def test_empty_memories_returns_empty_string(self):
        from agent.memory_retrieval import format_memories_for_prompt

        assert format_memories_for_prompt([]) == ""

    def test_formats_memories_as_markdown(self):
        from agent.memory_retrieval import format_memories_for_prompt

        memories = [
            {"text": "K8s session summary", "score": 0.92},
            {"text": "User prefers humor", "score": 0.85},
        ]
        result = format_memories_for_prompt(memories)

        assert "# Retrieved Long-Term Memories" in result
        assert "K8s session summary" in result
        assert "0.92" in result
        assert "User prefers humor" in result


# ── Recall Session Details Tool Tests ────────────────────────────────────────


class TestRecallSessionDetails:
    """Test make_recall_session_details_tool() — cross-session detail extraction."""

    @patch("agent.tools.recall_session_details.boto3")
    @patch("agent.tools.recall_session_details._get_extraction_agent")
    def test_extracts_details_from_session(self, mock_get_agent, mock_boto3):
        """Should load events, build conversation, and extract via sub-agent."""
        from agent.tools.recall_session_details import make_recall_session_details_tool

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # Mock list_events response
        mock_client.list_events.return_value = {
            "events": [
                {
                    "payload": [
                        {
                            "conversational": {
                                "role": "user",
                                "content": [{"text": "I want a K8s thumbnail with red background"}],
                            }
                        }
                    ]
                },
                {
                    "payload": [
                        {
                            "conversational": {
                                "role": "assistant",
                                "content": [{"text": "Creating thumbnail with Impact font, red background"}],
                            }
                        }
                    ]
                },
            ],
        }

        # Mock extraction agent
        mock_agent = MagicMock()
        mock_agent.return_value = "colors: red/white, font: Impact, layout: centered text"
        mock_get_agent.return_value = mock_agent

        tool = make_recall_session_details_tool("gili@amazon.com")
        result = tool._tool_func(session_id="sess-123", query="thumbnail design details")

        assert result["session_id"] == "sess-123"
        assert "colors" in result["extracted"]
        assert result["event_count"] == 2

    @patch("agent.tools.recall_session_details.boto3")
    def test_returns_error_when_no_events(self, mock_boto3):
        """Should return error dict when session has no events."""
        from agent.tools.recall_session_details import make_recall_session_details_tool

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.list_events.return_value = {"events": []}

        tool = make_recall_session_details_tool("gili@amazon.com")
        result = tool._tool_func(session_id="nonexistent", query="anything")

        assert "error" in result
        assert "No conversation found" in result["error"]

    def test_returns_error_when_no_memory_id(self):
        """Should return error when AGENTCORE_MEMORY_ID is not set."""
        from agent.tools.recall_session_details import make_recall_session_details_tool

        with patch.dict(os.environ, {"AGENTCORE_MEMORY_ID": ""}):
            tool = make_recall_session_details_tool("gili@amazon.com")
            result = tool._tool_func(session_id="sess-123", query="anything")
            assert "error" in result
            assert "not configured" in result["error"]

    def test_returns_error_for_empty_params(self):
        """Should return error when session_id or query is empty."""
        from agent.tools.recall_session_details import make_recall_session_details_tool

        tool = make_recall_session_details_tool("gili@amazon.com")
        result = tool._tool_func(session_id="", query="test")
        assert "error" in result


# ── (update_memory.py tests removed — strategies now managed via CDK) ────────


# ── Integration: create_agent with memory ────────────────────────────────────


class TestCreateAgentWithMemory:
    """Test that create_agent correctly injects memories into system prompt."""

    @patch("agent.main.retrieve_long_term_memories")
    @patch("agent.main.format_memories_for_prompt")
    @patch("agent.main.Agent")
    @patch("agent.main.BedrockModel")
    @patch("agent.main.create_research_agent")
    @patch("agent.main.create_thumbnail_agent")
    @patch("agent.main.AgentSkills")
    def test_injects_memories_when_user_message_provided(
        self, mock_skills, mock_thumb, mock_research, mock_model, mock_agent,
        mock_format, mock_retrieve
    ):
        """When user_message is provided, should retrieve and inject memories."""
        from agent.main import create_agent

        mock_retrieve.return_value = [{"text": "K8s session", "score": 0.9}]
        mock_format.return_value = "# Retrieved Long-Term Memories\n1. K8s session"

        # Mock sub-agents
        mock_research_agent = MagicMock()
        mock_research_agent.as_tool.return_value = MagicMock()
        mock_research.return_value = mock_research_agent

        mock_thumb_agent = MagicMock()
        mock_thumb_agent.as_tool.return_value = MagicMock()
        mock_thumb.return_value = mock_thumb_agent

        with patch.dict(os.environ, {"AGENTCORE_MEMORY_ID": ""}):
            create_agent(email="gili@amazon.com", session_id="sess-1", user_message="K8s video")

        mock_retrieve.assert_called_once_with("gili@amazon.com", "K8s video")
        mock_format.assert_called_once()

        # Verify Agent was called with enriched system prompt
        agent_call = mock_agent.call_args
        system_prompt = agent_call.kwargs.get("system_prompt", "")
        assert "Retrieved Long-Term Memories" in system_prompt

    @patch("agent.main.retrieve_long_term_memories")
    @patch("agent.main.Agent")
    @patch("agent.main.BedrockModel")
    @patch("agent.main.create_research_agent")
    @patch("agent.main.create_thumbnail_agent")
    @patch("agent.main.AgentSkills")
    def test_no_injection_without_user_message(
        self, mock_skills, mock_thumb, mock_research, mock_model, mock_agent,
        mock_retrieve
    ):
        """When user_message is None, should not attempt memory retrieval."""
        from agent.main import create_agent

        mock_research_agent = MagicMock()
        mock_research_agent.as_tool.return_value = MagicMock()
        mock_research.return_value = mock_research_agent

        mock_thumb_agent = MagicMock()
        mock_thumb_agent.as_tool.return_value = MagicMock()
        mock_thumb.return_value = mock_thumb_agent

        with patch.dict(os.environ, {"AGENTCORE_MEMORY_ID": ""}):
            create_agent(email="gili@amazon.com", session_id="sess-1")

        mock_retrieve.assert_not_called()
