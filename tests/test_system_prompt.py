"""Tests for system prompt — guardrails and conversation flow instructions."""

import pytest


class TestSystemPrompt:
    """Verify system prompt contains required sections."""

    def test_prompt_builds_successfully(self):
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert len(prompt) > 500

    def test_scope_boundaries(self):
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "Scope & Boundaries" in prompt
        assert "YouTube" in prompt
        assert "politely redirect" in prompt.lower() or "פוליטיקה" in prompt or "off-topic" in prompt.lower()

    def test_security_rules(self):
        """Verify anti-disclosure and prompt injection guardrails."""
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "Security" in prompt or "Self-Disclosure" in prompt
        assert "NEVER reveal" in prompt or "NEVER list" in prompt
        assert "system prompt" in prompt.lower()
        assert "prompt injection" in prompt.lower()
        assert "infrastructure" in prompt.lower()

    def test_conversation_flow_present(self):
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "Conversation Flow" in prompt
        assert "ask for materials" in prompt.lower() or "חומרים" in prompt
        assert "NEVER skip straight to web research" in prompt

    def test_progress_updates_section(self):
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "Progress Updates" in prompt
        assert "מחפש" in prompt or "מנתח" in prompt

    def test_language_rules(self):
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "Hebrew" in prompt
        assert "English" in prompt
        assert "Think and plan internally in English" in prompt

    def test_video_constraints(self):
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "3–7 minutes" in prompt or "3-7 minutes" in prompt
        assert "10 minutes" in prompt

    def test_content_levels(self):
        """Verify L100-L400 content levels are in the prompt."""
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "L100" in prompt
        assert "L200" in prompt
        assert "L300" in prompt
        assert "L400" in prompt
        assert "Introductory" in prompt or "מבוא" in prompt
        assert "Expert" in prompt or "מומחה" in prompt
        # Additional dimensions
        assert "טכני" in prompt
        assert "עסקי" in prompt
        assert "Hands-on" in prompt

    def test_no_aws_sa_reference(self):
        """Verify we removed the AWS SA-specific language."""
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "Solution Architects" not in prompt

    def test_pr_guidelines_present(self):
        """Verify PR/content safety guardrails are in the prompt."""
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "PR Guidelines" in prompt or "Content & PR" in prompt
        assert "LinkedIn Test" in prompt
        assert "embarrass" in prompt.lower()
        assert "competitor" in prompt.lower() or "clickbait" in prompt.lower()

    def test_methodology_included(self):
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        # The methodology.md content should be embedded
        assert "methodology" in prompt.lower() or "הוק" in prompt or "hook" in prompt.lower()

    def test_virality_included(self):
        from agent.system_prompt import build_system_prompt
        prompt = build_system_prompt()
        assert "virality" in prompt.lower() or "ויראלי" in prompt or "retention" in prompt.lower()
