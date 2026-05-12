from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

# unittest.mock is a built-in Python library for testing
# 'patch' lets you temporarily REPLACE a real function with a fake one
# 'MagicMock' is a fake object that pretends to be whatever you need
# 
# WHY do we mock?
# Our webhook now calls AWS SQS — but in tests we don't want to
# actually call AWS every time. That would be:
# - Slow (network calls)
# - Expensive (AWS charges per request)
# - Unreliable (tests fail if internet is down)
# So we FAKE the AWS call and just verify our code behaves correctly

client = TestClient(app)

# A sample GitHub Actions webhook payload
# This is what GitHub actually sends when a pipeline fails
# We use this in multiple tests so we define it once here
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


# 'patch' temporarily replaces 'app.main.get_sqs_client' with a fake
# The fake is passed into the test as 'mock_sqs_client'
# When the test finishes, the real function is automatically restored
@patch("app.main.get_sqs_client")
def test_webhook_failure_is_queued(mock_sqs_client):
    # Create a fake SQS client object
    mock_sqs = MagicMock()

    # Tell the fake: when send_message() is called, return this fake response
    mock_sqs.send_message.return_value = {"MessageId": "fake-message-id-123"}

    # Tell the patch: when get_sqs_client() is called, return our fake client
    mock_sqs_client.return_value = mock_sqs

    # Send a POST request with a failure payload
    response = client.post("/webhook/github", json=SAMPLE_FAILURE_PAYLOAD)

    # Verify we got a 200 response
    assert response.status_code == 200

    data = response.json()

    # Verify the response says it was received
    assert data["status"] == "received"

    # Verify our code actually called send_message on SQS
    # This confirms the message was actually pushed to the queue
    assert mock_sqs.send_message.called


@patch("app.main.get_sqs_client")
def test_webhook_success_is_skipped(mock_sqs_client):
    # For successful pipelines, we should skip processing
    mock_sqs = MagicMock()
    mock_sqs_client.return_value = mock_sqs

    response = client.post("/webhook/github", json=SAMPLE_SUCCESS_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"

    # Verify SQS was NOT called — we don't queue successful runs
    assert not mock_sqs.send_message.called


def test_webhook_invalid_json():
    # Send raw text instead of JSON — should get a 400 error
    response = client.post(
        "/webhook/github",
        content="this is not json",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400