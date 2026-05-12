from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)

# Sample payloads — reused across multiple tests
SAMPLE_FAILURE_PAYLOAD = {
    "repository": {
        "full_name": "shri-5279/test-repo"
    },
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
    "repository": {
        "full_name": "shri-5279/test-repo"
    },
    "workflow": "CI Pipeline",
    "workflow_run": {
        "id": 12346,
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "abc123def456",
        "created_at": "2024-01-15T10:30:00Z"
    }
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
    # Mock S3 save — return a fake S3 key
    mock_save_log.return_value = "failures/shri-5279/test-repo/2024-01-15/run-12345.json"

    # Mock SQS send
    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "fake-message-id-123"}
    mock_sqs_client.return_value = mock_sqs

    response = client.post("/webhook/github", json=SAMPLE_FAILURE_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "received"

    # Verify SQS was actually called
    assert mock_sqs.send_message.called


@patch("app.main.save_failure_log")
@patch("app.main.get_sqs_client")
def test_webhook_saves_to_s3(mock_sqs_client, mock_save_log):
    # Verify that save_failure_log is called for failures
    mock_save_log.return_value = "failures/shri-5279/test-repo/2024-01-15/run-12345.json"

    mock_sqs = MagicMock()
    mock_sqs.send_message.return_value = {"MessageId": "fake-id-456"}
    mock_sqs_client.return_value = mock_sqs

    response = client.post("/webhook/github", json=SAMPLE_FAILURE_PAYLOAD)

    assert response.status_code == 200
    data = response.json()

    # Response must include the S3 key
    assert "s3_key" in data

    # save_failure_log must have been called
    assert mock_save_log.called


@patch("app.main.save_failure_log")
@patch("app.main.get_sqs_client")
def test_webhook_success_is_skipped(mock_sqs_client, mock_save_log):
    mock_sqs = MagicMock()
    mock_sqs_client.return_value = mock_sqs

    response = client.post("/webhook/github", json=SAMPLE_SUCCESS_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"

    # Neither S3 nor SQS should be called for successful runs
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

    event = {
        "repository": "shri-5279/test-repo",
        "run_id": 99999
    }

    key = build_s3_key(event)

    assert key.startswith("failures/")
    assert "shri-5279" in key
    assert "test-repo" in key
    assert key.endswith(".json")