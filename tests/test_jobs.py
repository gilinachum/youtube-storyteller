"""Unit tests for the long-running jobs system.

Tests cover:
- jobs_poll: has_pending / has_unconsumed logic
- job_resolver: scan and dispatch behavior
- transcription_handler: completed / failed / in-progress branches + idempotency
- start_transcription tool: job record creation
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest
import boto3
from moto import mock_aws

# Ensure project root on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("JOBS_TABLE", "test-jobs")
os.environ.setdefault("SESSIONS_TABLE", "test-sessions")
os.environ.setdefault("UPLOAD_BUCKET", "test-uploads")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("TRANSCRIPTION_HANDLER_FN", "storyteller-transcription-handler")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_jobs_table(dynamodb):
    """Create the test jobs table with the correct schema."""
    table = dynamodb.create_table(
        TableName="test-jobs",
        KeySchema=[
            {"AttributeName": "session_id", "KeyType": "HASH"},
            {"AttributeName": "job_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "session_id", "AttributeType": "S"},
            {"AttributeName": "job_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "status-index",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return table


def _make_sessions_table(dynamodb):
    return dynamodb.create_table(
        TableName="test-sessions",
        KeySchema=[
            {"AttributeName": "email", "KeyType": "HASH"},
            {"AttributeName": "session_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "email", "AttributeType": "S"},
            {"AttributeName": "session_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _put_job(table, session_id, job_id, status, consumed, job_type="transcription", result=None, error=None):
    item = {
        "session_id": session_id,
        "job_id": job_id,
        "email": "test@example.com",
        "job_type": job_type,
        "status": status,
        "consumed": consumed,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"transcribe_job_name": f"transcribe-{job_id}"},
        "ttl": int(time.time()) + 86400,
    }
    if result:
        item["result"] = result
    if error:
        item["error"] = error
    table.put_item(Item=item)
    return item


# ── jobs_poll tests ───────────────────────────────────────────────────────────

class TestJobsPoll:

    @mock_aws
    def test_no_jobs_returns_all_false(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _make_jobs_table(dynamodb)

        from api.jobs_poll import handler
        event = {
            "queryStringParameters": {"session_id": "sess-1"},
            "requestContext": {"authorizer": {"claims": {"email": "test@example.com"}}},
        }
        result = handler(event, None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["has_pending"] is False
        assert body["has_unconsumed"] is False

    @mock_aws
    def test_started_unconsumed_job_sets_has_pending(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-1", "job-1", "started", consumed=False)

        from api.jobs_poll import handler
        event = {
            "queryStringParameters": {"session_id": "sess-1"},
            "requestContext": {"authorizer": {"claims": {"email": "test@example.com"}}},
        }
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["has_pending"] is True
        assert body["has_unconsumed"] is False

    @mock_aws
    def test_completed_unconsumed_sets_has_unconsumed(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-1", "job-2", "completed", consumed=False,
                 result={"s3_key": "uploads/t.txt", "text_preview": "hello"})

        from api.jobs_poll import handler
        event = {
            "queryStringParameters": {"session_id": "sess-1"},
            "requestContext": {"authorizer": {"claims": {"email": "test@example.com"}}},
        }
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["has_pending"] is False
        assert body["has_unconsumed"] is True

    @mock_aws
    def test_consumed_jobs_are_ignored(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-1", "job-3", "completed", consumed=True)

        from api.jobs_poll import handler
        event = {
            "queryStringParameters": {"session_id": "sess-1"},
            "requestContext": {"authorizer": {"claims": {"email": "test@example.com"}}},
        }
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["has_pending"] is False
        assert body["has_unconsumed"] is False

    @mock_aws
    def test_mixed_jobs_both_flags_set(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-1", "job-4", "started", consumed=False)
        _put_job(table, "sess-1", "job-5", "completed", consumed=False)

        from api.jobs_poll import handler
        event = {
            "queryStringParameters": {"session_id": "sess-1"},
            "requestContext": {"authorizer": {"claims": {"email": "test@example.com"}}},
        }
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["has_pending"] is True
        assert body["has_unconsumed"] is True

    @mock_aws
    def test_failed_job_unconsumed_sets_has_unconsumed(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-1", "job-6", "failed", consumed=False, error="Transcribe failed")

        from api.jobs_poll import handler
        event = {
            "queryStringParameters": {"session_id": "sess-1"},
            "requestContext": {"authorizer": {"claims": {"email": "test@example.com"}}},
        }
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["has_pending"] is False
        assert body["has_unconsumed"] is True

    @mock_aws
    def test_missing_session_id_returns_400(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _make_jobs_table(dynamodb)

        from api.jobs_poll import handler
        event = {
            "queryStringParameters": {},
            "requestContext": {"authorizer": {"claims": {"email": "test@example.com"}}},
        }
        result = handler(event, None)
        assert result["statusCode"] == 400


# ── job_resolver tests ────────────────────────────────────────────────────────

class TestJobResolver:

    @mock_aws
    def test_no_jobs_dispatches_nothing(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _make_jobs_table(dynamodb)

        with patch("api.job_resolver.lambda_client") as mock_lambda:
            from api import job_resolver
            # Reload to pick up mock
            import importlib
            importlib.reload(job_resolver)

            result = job_resolver.handler({}, None)
            assert result["dispatched"] == 0
            mock_lambda.invoke.assert_not_called()

    @mock_aws
    def test_started_jobs_are_dispatched(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-1", "job-1", "started", consumed=False)
        _put_job(table, "sess-2", "job-2", "started", consumed=False)

        with patch("boto3.client") as mock_boto_client:
            mock_lambda = MagicMock()
            mock_transcribe = MagicMock()
            mock_boto_client.side_effect = lambda service, **kwargs: (
                mock_lambda if service == "lambda" else mock_transcribe
            )

            import importlib
            import api.job_resolver
            importlib.reload(api.job_resolver)

            result = api.job_resolver.handler({}, None)
            assert result["dispatched"] == 2
            assert mock_lambda.invoke.call_count == 2

    @mock_aws
    def test_unknown_job_type_skipped(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-1", "job-1", "started", consumed=False, job_type="unknown_type")

        with patch("boto3.client") as mock_boto_client:
            mock_lambda = MagicMock()
            mock_boto_client.side_effect = lambda service, **kwargs: mock_lambda

            import importlib
            import api.job_resolver
            importlib.reload(api.job_resolver)

            result = api.job_resolver.handler({}, None)
            assert result["dispatched"] == 0


# ── transcription_handler tests ───────────────────────────────────────────────

class TestTranscriptionHandler:

    def _base_event(self):
        return {
            "job_id": "job-abc",
            "session_id": "sess-xyz",
            "email": "test@example.com",
            "job_type": "transcription",
            "metadata": {
                "transcribe_job_name": "storyteller-abc-12345",
                "s3_key": "uploads/test@example.com/sess-xyz/abc-interview.mp4",
                "file_id": "abc",
                "filename": "interview.mp4",
            },
        }

    @mock_aws
    def test_in_progress_does_nothing(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-xyz", "job-abc", "started", consumed=False)
        _make_sessions_table(dynamodb)

        import importlib
        import api.transcription_handler
        importlib.reload(api.transcription_handler)

        mock_transcribe = MagicMock()
        mock_transcribe.get_transcription_job.return_value = {
            "TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}
        }

        with patch.object(api.transcription_handler, "transcribe_client", mock_transcribe), \
             patch.object(api.transcription_handler, "dynamodb", dynamodb):
            api.transcription_handler.handler(self._base_event(), None)

        # Job should still be "started"
        item = table.get_item(Key={"session_id": "sess-xyz", "job_id": "job-abc"}).get("Item", {})
        assert item.get("status") == "started"

    @mock_aws
    def test_completed_updates_job_and_saves_file(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-xyz", "job-abc", "started", consumed=False)
        sessions_table = _make_sessions_table(dynamodb)
        sessions_table.put_item(Item={
            "email": "test@example.com",
            "session_id": "sess-xyz",
            "name": "test session",
        })

        transcript_json = json.dumps({
            "results": {"transcripts": [{"transcript": "Hello this is the transcript"}]}
        })

        import importlib
        import api.transcription_handler
        importlib.reload(api.transcription_handler)

        mock_transcribe = MagicMock()
        mock_transcribe.get_transcription_job.return_value = {
            "TranscriptionJob": {
                "TranscriptionJobStatus": "COMPLETED",
                "LanguageCode": "en-US",
                "Transcript": {"TranscriptFileUri": "https://example.com/transcript.json"},
            }
        }
        mock_s3 = MagicMock()

        mock_response = MagicMock()
        mock_response.read.return_value = transcript_json.encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response), \
             patch.object(api.transcription_handler, "transcribe_client", mock_transcribe), \
             patch.object(api.transcription_handler, "s3", mock_s3), \
             patch.object(api.transcription_handler, "dynamodb", dynamodb):
            api.transcription_handler.handler(self._base_event(), None)

        # Verify job updated to completed
        item = table.get_item(Key={"session_id": "sess-xyz", "job_id": "job-abc"}).get("Item", {})
        assert item.get("status") == "completed"
        assert "result" in item
        assert item["result"]["language"] == "en-US"
        assert "text_preview" in item["result"]

        # Verify S3 put_object was called
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "text/plain; charset=utf-8"
        assert b"Hello this is the transcript" in call_kwargs["Body"]

    @mock_aws
    def test_failed_updates_job_status(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        _put_job(table, "sess-xyz", "job-abc", "started", consumed=False)
        _make_sessions_table(dynamodb)

        import importlib
        import api.transcription_handler
        importlib.reload(api.transcription_handler)

        mock_transcribe = MagicMock()
        mock_transcribe.get_transcription_job.return_value = {
            "TranscriptionJob": {
                "TranscriptionJobStatus": "FAILED",
                "FailureReason": "Invalid audio format",
            }
        }

        with patch.object(api.transcription_handler, "transcribe_client", mock_transcribe), \
             patch.object(api.transcription_handler, "dynamodb", dynamodb):
            api.transcription_handler.handler(self._base_event(), None)

        item = table.get_item(Key={"session_id": "sess-xyz", "job_id": "job-abc"}).get("Item", {})
        assert item.get("status") == "failed"
        assert "Invalid audio format" in item.get("error", "")

    @mock_aws
    def test_idempotent_completed_twice(self):
        """Second invocation on completed job should be a no-op (conditional check)."""
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)
        # Job already completed (not started)
        _put_job(table, "sess-xyz", "job-abc", "completed", consumed=False,
                 result={"s3_key": "old.txt", "text_preview": "old"})
        _make_sessions_table(dynamodb)

        transcript_json = json.dumps({
            "results": {"transcripts": [{"transcript": "New transcript text"}]}
        })

        import importlib
        import api.transcription_handler
        importlib.reload(api.transcription_handler)

        mock_transcribe = MagicMock()
        mock_transcribe.get_transcription_job.return_value = {
            "TranscriptionJob": {
                "TranscriptionJobStatus": "COMPLETED",
                "LanguageCode": "en-US",
                "Transcript": {"TranscriptFileUri": "https://example.com/t.json"},
            }
        }
        mock_s3 = MagicMock()

        mock_response = MagicMock()
        mock_response.read.return_value = transcript_json.encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response), \
             patch.object(api.transcription_handler, "transcribe_client", mock_transcribe), \
             patch.object(api.transcription_handler, "s3", mock_s3), \
             patch.object(api.transcription_handler, "dynamodb", dynamodb):
            # Should not raise — conditional update fails silently
            api.transcription_handler.handler(self._base_event(), None)

        # Job should still have old result (conditional update was rejected)
        item = table.get_item(Key={"session_id": "sess-xyz", "job_id": "job-abc"}).get("Item", {})
        assert item.get("status") == "completed"
        assert item.get("result", {}).get("s3_key") == "old.txt"


# ── start_transcription tool tests ────────────────────────────────────────────

def _import_start_transcription():
    """Import start_transcription module directly, bypassing __init__.py (no strands needed)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "start_transcription",
        os.path.join(PROJECT_ROOT, "agent", "tools", "start_transcription.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    # Provide a minimal strands.tool stub so the @tool decorator works
    import types
    strands_stub = types.ModuleType("strands")
    strands_stub.tool = lambda fn: fn  # identity decorator
    sys.modules.setdefault("strands", strands_stub)
    spec.loader.exec_module(mod)
    return mod


class TestStartTranscriptionTool:

    @mock_aws
    def test_creates_job_record_in_ddb(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = _make_jobs_table(dynamodb)

        mock_transcribe = MagicMock()
        mock_transcribe.start_transcription_job.return_value = {}
        mock_s3 = MagicMock()
        mock_s3.head_object.return_value = {"ContentLength": 5 * 1024 * 1024}  # 5MB

        st_module = _import_start_transcription()

        with patch.object(st_module, "boto3") as mock_boto:
            mock_boto.client.side_effect = lambda service, **kwargs: (
                mock_transcribe if service == "transcribe" else mock_s3
            )
            mock_boto.resource.return_value = dynamodb

            tool_fn = st_module.make_start_transcription_tool("user@example.com", "sess-test")
            result = tool_fn(
                s3_key="uploads/user/sess/abc-video.mp4",
                file_id="abc",
                filename="video.mp4",
            )

        assert "job_id" in result
        assert "estimated_seconds" in result
        assert result["estimated_seconds"] >= 30

        # Check DDB record
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("session_id").eq("sess-test")
        )
        items = response.get("Items", [])
        assert len(items) == 1
        job = items[0]
        assert job["status"] == "started"
        assert job["consumed"] is False
        assert job["job_type"] == "transcription"
        assert job["metadata"]["filename"] == "video.mp4"
        mock_transcribe.start_transcription_job.assert_called_once()

    def test_estimation_floor_at_30s(self):
        st_module = _import_start_transcription()
        mock_s3 = MagicMock()
        mock_s3.head_object.return_value = {"ContentLength": 100}  # tiny file
        result = st_module._estimate_seconds(mock_s3, "some/key")
        assert result == 30

    def test_estimation_ceiling_at_1200s(self):
        st_module = _import_start_transcription()
        mock_s3 = MagicMock()
        mock_s3.head_object.return_value = {"ContentLength": 2000 * 1024 * 1024}  # 2GB
        result = st_module._estimate_seconds(mock_s3, "some/key")
        assert result == 1200

    def test_estimation_fallback_on_error(self):
        st_module = _import_start_transcription()
        mock_s3 = MagicMock()
        mock_s3.head_object.side_effect = Exception("S3 error")
        result = st_module._estimate_seconds(mock_s3, "some/key")
        assert result == 180  # fallback default
