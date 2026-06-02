from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)

SAMPLE_FAILURE_PAYLOAD = {
    "repository": {"full_name": "shri-5279/test-repo"},
    "workflow": "CI Pipeline",
    "workflow_run": {
        "id": 12345,
        "conclusion": "failure",
        "head_branch": "main",
        "head_sha": "abc123def456",
        "created_at": "2024-01-15T10:30:00Z"
    }
}

SAMPLE_SUCCESS_PAYLOAD = {
    "repository": {"full_name": "shri-5279/test-repo"},
    "workflow": "CI Pipeline",
    "workflow_run": {
        "id": 12346,
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "abc123def456",
        "created_at": "2024-01-15T10:30:00Z"
    }
}

SAMPLE_AI_RESULT = {
    "root_cause": "Missing dependency in requirements.txt",
    "suggested_fix": "Add the missing package and push again",
    "failure_category": "dependency_error",
    "confidence": "high",
    "additional_context": "Check all imports"
}


def test_root_status_code():
    response = client.get("/")
    assert response.status_code == 200


def test_root_returns_correct_data():
    response = client.get("/")
    data = response.json()
    assert data["service"] == "PipeLine AI"
    assert data["status"] == "running"


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@patch("app.main.save_failure_log")
@patch("app.main.get_sqs_client")
def test_webhook_failure_is_queued(mock_sqs_client, mock_save_log):
    mock_save_log.return_value = "failures/shri-5279/test-repo/2024-01-15/run-12345.json"
    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "fake-message-id-123"}
    mock_sqs_client.return_value = mock_sqs

    response = client.post("/webhook/github", json=SAMPLE_FAILURE_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "received"
    assert mock_sqs.send_message.called


@patch("app.main.save_failure_log")
@patch("app.main.get_sqs_client")
def test_webhook_saves_to_s3(mock_sqs_client, mock_save_log):
    mock_save_log.return_value = "failures/shri-5279/test-repo/2024-01-15/run-12345.json"
    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "fake-id-456"}
    mock_sqs_client.return_value = mock_sqs

    response = client.post("/webhook/github", json=SAMPLE_FAILURE_PAYLOAD)

    assert response.status_code == 200
    assert "s3_key" in response.json()
    assert mock_save_log.called


@patch("app.main.save_failure_log")
@patch("app.main.get_sqs_client")
def test_webhook_success_is_skipped(mock_sqs_client, mock_save_log):
    mock_sqs = MagicMock()
    mock_sqs_client.return_value = mock_sqs

    response = client.post("/webhook/github", json=SAMPLE_SUCCESS_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    assert not mock_save_log.called
    assert not mock_sqs.send_message.called


def test_webhook_invalid_json():
    response = client.post(
        "/webhook/github",
        content="this is not json",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_build_s3_key_format():
    from app.storage import build_s3_key
    event = {"repository": "shri-5279/test-repo", "run_id": 99999}
    key = build_s3_key(event)
    assert key.startswith("failures/")
    assert "shri-5279" in key
    assert "test-repo" in key
    assert key.endswith(".json")


@patch("app.main.get_recent_failures")
def test_get_failures_endpoint(mock_get_failures):
    mock_get_failures.return_value = [
        {
            "id": 1,
            "repository": "shri-5279/test-repo",
            "status": "analyzed",
            "run_id": "12345",
            "root_cause": "Missing dependency",
            "suggested_fix": "Add package to requirements.txt",
            "failure_category": "dependency_error"
        }
    ]

    response = client.get("/failures")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["count"] == 1
    assert len(data["failures"]) == 1


# These two tests now mock ALL four dependencies
# get_failure_log (S3), save_failure_to_db (DB write),
# analyze_failure (Bedrock AI), update_failure_analysis (DB update)
@patch("app.ingestion.update_failure_analysis")
@patch("app.ingestion.analyze_failure")
@patch("app.ingestion.save_failure_to_db")
@patch("app.ingestion.get_failure_log")
def test_process_message_returns_true_on_success(
    mock_get_log, mock_save_db, mock_analyze, mock_update
):
    from app.ingestion import process_message
    import json

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

    mock_get_log.return_value = SAMPLE_EVENT
    mock_save_db.return_value = 1
    mock_analyze.return_value = SAMPLE_AI_RESULT
    mock_update.return_value = None

    result = process_message(SAMPLE_SQS_MESSAGE)
    assert result is True
    assert mock_save_db.called
    assert mock_analyze.called
    assert mock_update.called


@patch("app.ingestion.update_failure_analysis")
@patch("app.ingestion.analyze_failure")
@patch("app.ingestion.save_failure_to_db")
@patch("app.ingestion.get_failure_log")
def test_process_message_handles_s3_failure_gracefully(
    mock_get_log, mock_save_db, mock_analyze, mock_update
):
    from app.ingestion import process_message
    import json

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

    mock_get_log.side_effect = Exception("S3 connection failed")
    mock_save_db.return_value = 1
    mock_analyze.return_value = SAMPLE_AI_RESULT
    mock_update.return_value = None

    result = process_message(SAMPLE_SQS_MESSAGE)
    assert result is True