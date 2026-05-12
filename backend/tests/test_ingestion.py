import json
import pytest
from unittest.mock import patch, MagicMock
from app.ingestion import parse_failure_log, process_message


# Sample event data — what a parsed SQS message body looks like
SAMPLE_EVENT = {
    "repository": "shri-5279/PipeLine-AI",
    "workflow": "CI Pipeline",
    "run_id": 99999,
    "conclusion": "failure",
    "branch": "main",
    "commit_sha": "abc123def456",
    "created_at": "2024-01-15T10:30:00Z",
    "stored_at": "2024-01-15T10:30:05Z",
    "s3_key": "failures/shri-5279/PipeLine-AI/2024-01-15/run-99999.json"
}

# A sample SQS message — this is the full structure SQS returns
# including the receipt handle and message ID
SAMPLE_SQS_MESSAGE = {
    "MessageId": "test-message-id-123",
    "ReceiptHandle": "test-receipt-handle-abc",
    "Body": json.dumps(SAMPLE_EVENT),
    "Attributes": {
        "SentTimestamp": "1705312200000"
    }
}


def test_parse_failure_log_returns_required_fields():
    # Test that parse_failure_log returns all the fields we expect
    result = parse_failure_log(SAMPLE_EVENT)

    # These fields must always be present in the parsed output
    assert "repository" in result
    assert "workflow" in result
    assert "run_id" in result
    assert "branch" in result
    assert "commit_sha" in result
    assert "s3_key" in result
    assert "status" in result


def test_parse_failure_log_sets_pending_status():
    # New failures should always start as 'pending_analysis'
    # The AI in Phase 2 will update this to 'analyzed'
    result = parse_failure_log(SAMPLE_EVENT)
    assert result["status"] == "pending_analysis"


def test_parse_failure_log_preserves_repository():
    # Make sure the repository name passes through correctly
    result = parse_failure_log(SAMPLE_EVENT)
    assert result["repository"] == "shri-5279/PipeLine-AI"


def test_parse_failure_log_ai_fields_are_none():
    # AI fields should be None at this stage — not yet analyzed
    result = parse_failure_log(SAMPLE_EVENT)
    assert result["root_cause"] is None
    assert result["suggested_fix"] is None
    assert result["failure_category"] is None


@patch("app.ingestion.get_failure_log")
def test_process_message_returns_true_on_success(mock_get_log):
    # Mock the S3 fetch so we don't hit real AWS in tests
    mock_get_log.return_value = SAMPLE_EVENT

    # process_message should return True when everything works
    result = process_message(SAMPLE_SQS_MESSAGE)
    assert result is True


def test_process_message_handles_invalid_json():
    # If SQS message body is not valid JSON, should return True
    # (delete the corrupted message — no point retrying it)
    bad_message = {
        "MessageId": "bad-id",
        "ReceiptHandle": "bad-handle",
        "Body": "this is not valid json at all {{{"
    }
    result = process_message(bad_message)
    assert result is True


@patch("app.ingestion.get_failure_log")
def test_process_message_handles_s3_failure_gracefully(mock_get_log):
    # If S3 fetch fails, processing should still succeed
    # because we have enough data in the SQS message itself
    mock_get_log.side_effect = Exception("S3 connection failed")

    result = process_message(SAMPLE_SQS_MESSAGE)

    # Should still return True — S3 failure is non-fatal
    assert result is True