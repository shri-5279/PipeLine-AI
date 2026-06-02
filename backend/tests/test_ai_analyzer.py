from unittest.mock import patch, MagicMock
import json
from app.ai_analyzer import analyze_failure

SAMPLE_EVENT = {
    "repository": "shri-5279/PipeLine-AI",
    "workflow": "CI Pipeline",
    "run_id": 99999,
    "branch": "main",
    "commit_sha": "abc123",
    "created_at": "2024-01-15T10:30:00Z"
}

SAMPLE_AI_RESPONSE = {
    "root_cause": "Missing dependency: requests library not installed",
    "suggested_fix": "Run pip install requests and update requirements.txt",
    "failure_category": "dependency_error",
    "confidence": "high",
    "additional_context": "Check your requirements.txt file"
}


@patch("app.ai_analyzer.get_bedrock_client")
def test_analyze_failure_returns_required_fields(mock_bedrock_client):
    # Mock the Bedrock client
    mock_client = MagicMock()
    mock_bedrock_client.return_value = mock_client

    # Mock the response from Bedrock
    # Bedrock returns a streaming body — we mock it to return our sample response
    mock_response_body = MagicMock()
    mock_response_body.read.return_value = json.dumps({
        "content": [{"text": json.dumps(SAMPLE_AI_RESPONSE)}]
    }).encode()

    mock_client.invoke_model.return_value = {"body": mock_response_body}

    result = analyze_failure(SAMPLE_EVENT)

    assert "root_cause" in result
    assert "suggested_fix" in result
    assert "failure_category" in result
    assert "confidence" in result


@patch("app.ai_analyzer.get_bedrock_client")
def test_analyze_failure_returns_correct_category(mock_bedrock_client):
    mock_client = MagicMock()
    mock_bedrock_client.return_value = mock_client

    mock_response_body = MagicMock()
    mock_response_body.read.return_value = json.dumps({
        "content": [{"text": json.dumps(SAMPLE_AI_RESPONSE)}]
    }).encode()

    mock_client.invoke_model.return_value = {"body": mock_response_body}

    result = analyze_failure(SAMPLE_EVENT)
    assert result["failure_category"] == "dependency_error"
    assert result["confidence"] == "high"


@patch("app.ai_analyzer.get_bedrock_client")
def test_analyze_failure_handles_bedrock_error_gracefully(mock_bedrock_client):
    # If Bedrock is unavailable, should return a safe fallback
    mock_client = MagicMock()
    mock_bedrock_client.return_value = mock_client
    mock_client.invoke_model.side_effect = Exception("Bedrock unavailable")

    result = analyze_failure(SAMPLE_EVENT)

    # Should not crash — returns a fallback response
    assert "root_cause" in result
    assert "suggested_fix" in result
    assert result["failure_category"] == "unknown"
    assert result["confidence"] == "low"


@patch("app.ai_analyzer.get_bedrock_client")
def test_analyze_failure_handles_invalid_json_response(mock_bedrock_client):
    # If Claude returns non-JSON, should handle gracefully
    mock_client = MagicMock()
    mock_bedrock_client.return_value = mock_client

    mock_response_body = MagicMock()
    mock_response_body.read.return_value = json.dumps({
        "content": [{"text": "This is not JSON at all"}]
    }).encode()

    mock_client.invoke_model.return_value = {"body": mock_response_body}

    result = analyze_failure(SAMPLE_EVENT)
    assert result["failure_category"] == "unknown"