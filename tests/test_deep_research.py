"""Integration tests for the deep_research tool — real backends, no mocks.

Exercises agent/tools/deep_research.py end-to-end: real Gateway Web Search
Tool call (web_research.py), real Perplexity call (trend_analysis.py), and
real Nova 2 Lite summarization. This is deliberately NOT a mocked unit test
— the point is to verify the actual live integration (Gateway auth, MCP
tool name, Perplexity secret, Bedrock summarization) keeps working end to
end, especially after swapping web_research.py from Tavily to the AgentCore
Gateway Web Search Tool.

Run: pytest tests/test_deep_research.py -v --tb=short
Skip if no AWS/Bedrock access: tests auto-skip when credentials are unavailable.

Note on flakiness: in some dev sandboxes, short-lived assumed-role sessions
(e.g. Isengard) can expire mid-run when this file executes late in a long
full-suite run, causing a transient 401 from the Gateway. This matches the
same category of pre-existing flakiness as test_youtube_search.py's and
test_e2e_youtube_analysis.py's live tests in this suite. Re-authenticate
(`ada credentials update ...`) and re-run if you hit a 401 here.
"""

import importlib
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# conftest.py sets fake ("testing") AWS creds for moto-based unit tests. This
# file needs real creds to reach Bedrock, the Gateway, and Secrets Manager
# (for the Perplexity key), so strip the fakes and fall back to whatever the
# environment actually has (instance profile / SSO / env creds).
_REAL_CREDS_RESTORED = False


def _restore_real_aws_creds():
    global _REAL_CREDS_RESTORED
    if _REAL_CREDS_RESTORED:
        return
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
        os.environ.pop(key, None)
    _REAL_CREDS_RESTORED = True


def _has_live_access() -> bool:
    """Check we can reach both Bedrock (for summarization) and Secrets Manager
    (for the Perplexity key that trend_analysis.py needs) with real creds.

    Pins the region explicitly rather than trusting AWS_REGION/AWS_DEFAULT_REGION
    from the ambient environment — in some dev shells those resolve to an
    unrelated region (e.g. a personal Isengard default, or a region another
    test module set at import time — several test files do
    `os.environ["AWS_DEFAULT_REGION"] = ...` unconditionally), which would
    otherwise silently skip these tests with a misleading "no access" reason
    instead of the real "wrong region" cause.
    """
    _restore_real_aws_creds()
    try:
        import boto3
        region = _dev_region()
        sm = boto3.client("secretsmanager", region_name=region)
        sm.get_secret_value(SecretId="perplexity/api-key")
        boto3.client("bedrock-runtime", region_name=region)
        return True
    except Exception:
        return False


def _dev_region() -> str:
    """StoryTeller dev stage's fixed region (see infra/app.py CONFIG['dev'])."""
    return "us-west-2"


_GATEWAY_URL_CACHE = None


def _real_gateway_url() -> str:
    """Fetch the deployed Web Search Gateway URL from its CFN stack output.

    Deliberately not hardcoded here — infra/stacks/gateway_search_stack.py
    is the single source of truth (same as scripts/deploy.sh's
    SEARCH_GATEWAY_URL lookup). A hardcoded URL in this test would silently
    go stale if the gateway is ever recreated (new gateway ID in the URL).
    """
    global _GATEWAY_URL_CACHE
    if _GATEWAY_URL_CACHE is not None:
        return _GATEWAY_URL_CACHE
    import boto3
    cfn = boto3.client("cloudformation", region_name="us-east-1")
    outputs = cfn.describe_stacks(StackName="storyteller-gateway-search")["Stacks"][0]["Outputs"]
    _GATEWAY_URL_CACHE = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "GatewayUrl")
    return _GATEWAY_URL_CACHE


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _has_live_access(),
        reason="No live AWS access (Bedrock + Secrets Manager) — set real AWS credentials",
    ),
]


class TestDeepResearchLive:
    """Live integration tests — real Gateway Web Search, real Perplexity, real Nova summarization."""

    @classmethod
    def setup_class(cls):
        _restore_real_aws_creds()

    def setup_method(self, method):
        # Scope the region override to THIS test only, via monkeypatch, so it
        # never leaks into other test files (they run in the same process —
        # several rely on AWS_REGION/AWS_DEFAULT_REGION being left alone by
        # unrelated test files; see the comments in test_public_sharing.py
        # and test_session_sharing.py for why unconditional os.environ[...] =
        # assignments are a known cross-file isolation hazard here).
        self._monkeypatch = pytest.MonkeyPatch()
        self._monkeypatch.setenv("AWS_REGION", _dev_region())
        self._monkeypatch.setenv("AWS_DEFAULT_REGION", _dev_region())
        self._monkeypatch.setenv("SEARCH_GATEWAY_URL", _real_gateway_url())

        # web_research.py reads SEARCH_GATEWAY_URL into a module-level
        # constant at import time. conftest.py sets a placeholder URL as a
        # default so unrelated unit tests can import the module without a
        # real gateway; reload it here so GATEWAY_URL picks up the real
        # value for these live tests.
        #
        # Must go through sys.modules, not `import ... as x` — agent/tools/
        # __init__.py does `from .web_research import web_research`, which
        # shadows the submodule name with the @tool-decorated function
        # object on the `agent.tools` package namespace. A plain
        # `import agent.tools.web_research as m` after that returns the
        # DecoratedFunctionTool, not the module, and importlib.reload() on
        # it fails with "module web_research not in sys.modules".
        import sys
        import agent.tools.web_research  # noqa: F401 (ensures it's imported)
        web_research_mod = sys.modules["agent.tools.web_research"]
        importlib.reload(web_research_mod)

        # Force re-creation of any lazily-cached clients that may have bound
        # to the fake moto credentials (or a stray ambient AWS_REGION) during
        # collection/import or an earlier test file's run.
        import agent.tools.trend_analysis as trend_analysis_mod
        web_research_mod._sm_client = None
        trend_analysis_mod._sm_client = None

        # agent.tools.deep_research and agent.tools.__init__ import
        # web_research directly (`from .web_research import web_research`),
        # so the reload above doesn't automatically propagate to their
        # already-bound references. Reload the chain so deep_research._tool_func
        # ends up calling the reloaded module's web_research, not a stale one
        # bound to the placeholder GATEWAY_URL.
        import agent.tools as tools_pkg
        import agent.tools.deep_research as deep_research_mod
        importlib.reload(tools_pkg)
        importlib.reload(deep_research_mod)

    def teardown_method(self, method):
        self._monkeypatch.undo()

    def test_research_returns_structured_brief(self):
        """A real topic should produce a research brief with all expected sections."""
        from agent.tools.deep_research import deep_research

        result = deep_research._tool_func(topic="AWS Lambda SnapStart")

        assert isinstance(result, str)
        assert result.startswith("# Research Brief:")
        assert "AWS Lambda SnapStart" in result
        # Timing line proves both the parallel fan-out and the summarization
        # step actually ran (not short-circuited by an early exception).
        assert "Tools:" in result and "Summary:" in result and "Total:" in result

    def test_research_uses_both_search_sources(self):
        """web_research (Gateway Web Search) and trend_analysis (Perplexity)
        should both contribute — neither should silently no-op."""
        from agent.tools.deep_research import _run_parallel_research

        results = _run_parallel_research("Kubernetes on AWS")

        assert "web_results" in results and "trend_results" in results
        # Neither should be an [Error]/[Timeout] placeholder under normal
        # conditions — if one is, that source's live integration is broken.
        for key in ("web_results", "trend_results"):
            value = results[key]
            assert not value.startswith("["), f"{key} failed or timed out: {value[:200]}"
            assert len(value) > 50, f"{key} returned suspiciously little content: {value!r}"

    def test_research_completes_within_time_budget(self):
        """Parallel fan-out + summarization should stay well under serial time.
        STORYTELLER-CONTEXT.md documents ~16s for the equivalent pipeline
        (12s parallel + 4s Nova) vs 60s+ sequential — assert a generous
        upper bound so this doesn't flake on normal network variance while
        still catching a regression back to serial execution."""
        from agent.tools.deep_research import deep_research

        start = time.time()
        deep_research._tool_func(topic="Amazon EKS Auto Mode")
        elapsed = time.time() - start

        assert elapsed < 45, f"deep_research took {elapsed:.1f}s (budget: 45s)"

    def test_research_with_url_included(self):
        """Passing a URL should fetch and fold it into the brief without
        breaking the web_research/trend_analysis fan-out."""
        from agent.tools.deep_research import deep_research

        result = deep_research._tool_func(
            topic="AWS Lambda SnapStart",
            urls="https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html",
        )

        assert result.startswith("# Research Brief:")
        # The URL fetch runs as an extra parallel future (url_0) — confirm it
        # didn't silently fail and take down the rest of the brief.
        assert "Tools:" in result
