import json
from unittest.mock import patch, MagicMock
from app.ingestion import parse_failure_log, process_message

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

SAMPLE_SQS_MESSAGE = {
    "MessageId": "test-message-id-123",
    "ReceiptHandle": "test-receipt-handle-abc",
    "Body": json.dumps(SAMPLE_EVENT),
    "Attributes": {"SentTimestamp": "1705312200000"}
}

SAMPLE_AI_RESULT = {
    "root_cause": "Missing dependency: numpy not found in requirements.txt",
    "suggested_fix": "Add numpy to requirements.txt and push again",
    "failure_category": "dependency_error",
    "confidence": "high",
    "additional_context": "Check all imports in your Python files"
}


def test_parse_failure_log_returns_required_fields():
    result = parse_failure_log(SAMPLE_EVENT)
    assert "repository" in result
    assert "workflow" in result
    assert "run_id" in result
    assert "branch" in result
    assert "commit_sha" in result
    assert "s3_key" in result
    assert "status" in result


def test_parse_failure_log_sets_pending_status():
    result = parse_failure_log(SAMPLE_EVENT)
    assert result["status"] == "pending_analysis"


def test_parse_failure_log_preserves_repository():
    result = parse_failure_log(SAMPLE_EVENT)
    assert result["repository"] == "shri-5279/PipeLine-AI"


def test_parse_failure_log_ai_fields_are_none():
    result = parse_failure_log(SAMPLE_EVENT)
    assert result["root_cause"] is None
    assert result["suggested_fix"] is None
    assert result["failure_category"] is None


@patch("app.ingestion.update_failure_analysis")
@patch("app.ingestion.analyze_failure")
@patch("app.ingestion.save_failure_to_db")
@patch("app.ingestion.get_failure_log")
def test_process_message_returns_true_on_success(
    mock_get_log, mock_save_db, mock_analyze, mock_update
):
    mock_get_log.return_value = SAMPLE_EVENT
    mock_save_db.return_value = 1
    mock_analyze.return_value = SAMPLE_AI_RESULT
    mock_update.return_value = None

    result = process_message(SAMPLE_SQS_MESSAGE)
    assert result is True
    assert mock_save_db.called
    assert mock_analyze.called
    assert mock_update.called


def test_process_message_handles_invalid_json():
    bad_message = {
        "MessageId": "bad-id",
        "ReceiptHandle": "bad-handle",
        "Body": "this is not valid json {{{"
    }
    result = process_message(bad_message)
    assert result is True


@patch("app.ingestion.update_failure_analysis")
@patch("app.ingestion.analyze_failure")
@patch("app.ingestion.save_failure_to_db")
@patch("app.ingestion.get_failure_log")
def test_process_message_handles_s3_failure_gracefully(
    mock_get_log, mock_save_db, mock_analyze, mock_update
):
    mock_get_log.side_effect = Exception("S3 connection failed")
    mock_save_db.return_value = 1
    mock_analyze.return_value = SAMPLE_AI_RESULT
    mock_update.return_value = None

    result = process_message(SAMPLE_SQS_MESSAGE)
    assert result is True


@patch("app.ingestion.update_failure_analysis")
@patch("app.ingestion.analyze_failure")
@patch("app.ingestion.save_failure_to_db")
@patch("app.ingestion.get_failure_log")
def test_ai_analysis_is_called_and_saved(
    mock_get_log, mock_save_db, mock_analyze, mock_update
):
    mock_get_log.return_value = SAMPLE_EVENT
    mock_save_db.return_value = 42
    mock_analyze.return_value = SAMPLE_AI_RESULT
    mock_update.return_value = None

    process_message(SAMPLE_SQS_MESSAGE)

    # Verify analyze_failure was called with the event data
    assert mock_analyze.called

    # Verify update was called with the correct db_id
    mock_update.assert_called_once_with(42, SAMPLE_AI_RESULT)