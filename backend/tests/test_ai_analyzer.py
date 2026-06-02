from unittest.mock import patch, MagicMock
import json
from app.ai_analyzer import analyze_failure


SAMPLE_EVENT = {
    "repository": "shri-5279/PipeLine-AI",
    "workflow": "CI Pipeline",
    "run_id": 99999,
    "branch": "main",
    "commit_sha": "abc123",
    "created_at": "2024-01-15T10:30:00Z",
}

SAMPLE_AI_RESPONSE = {
    "root_cause": "Missing dependency: requests library not installed",
    "suggested_fix": "Run pip install requests and update requirements.txt",
    "failure_category": "dependency_error",
    "confidence": "high",
    "additional_context": "Check your requirements.txt file",
}


def mock_groq_response(content):
    mock_choice = MagicMock()
    mock_choice.message.content = content

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    return mock_response


@patch("app.ai_analyzer.client")
def test_analyze_failure_returns_required_fields(mock_client):
    mock_client.chat.completions.create.return_value = mock_groq_response(
        json.dumps(SAMPLE_AI_RESPONSE)
    )

    result = analyze_failure(SAMPLE_EVENT)

    assert "root_cause" in result
    assert "suggested_fix" in result
    assert "failure_category" in result
    assert "confidence" in result


@patch("app.ai_analyzer.client")
def test_analyze_failure_returns_correct_category(mock_client):
    mock_client.chat.completions.create.return_value = mock_groq_response(
        json.dumps(SAMPLE_AI_RESPONSE)
    )

    result = analyze_failure(SAMPLE_EVENT)

    assert result["failure_category"] == "dependency_error"
    assert result["confidence"] == "high"


@patch("app.ai_analyzer.client")
def test_analyze_failure_handles_groq_error_gracefully(mock_client):
    mock_client.chat.completions.create.side_effect = Exception("Groq unavailable")

    result = analyze_failure(SAMPLE_EVENT)

    assert "root_cause" in result
    assert "suggested_fix" in result
    assert result["failure_category"] == "unknown"
    assert result["confidence"] == "low"


@patch("app.ai_analyzer.client")
def test_analyze_failure_handles_invalid_json_response(mock_client):
    mock_client.chat.completions.create.return_value = mock_groq_response(
        "This is not JSON at all"
    )

    result = analyze_failure(SAMPLE_EVENT)

    assert result["failure_category"] == "unknown"