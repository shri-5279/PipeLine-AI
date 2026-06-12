from unittest.mock import patch, MagicMock
import json
from app.agent import run_agent, search_past_failures, search_github_issues

SAMPLE_FAILURE = {
    "id": 1,
    "repository": "shri-5279/PipeLine-AI",
    "workflow": "CI Pipeline",
    "branch": "main",
    "commit_sha": "abc123",
    "root_cause": "Missing dependency in requirements.txt",
    "failure_category": "dependency_error",
    "status": "analyzed"
}


@patch("app.agent.client")
def test_run_agent_returns_output(mock_client):
    # Mock the Groq client to return a final answer immediately
    mock_message = MagicMock()
    mock_message.content = "Update requirements.txt with the missing package"
    mock_message.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create.return_value = mock_response

    result = run_agent(SAMPLE_FAILURE)

    assert "agent_output" in result
    assert "status" in result
    assert result["status"] == "completed"


@patch("app.agent.client")
def test_run_agent_handles_failure_gracefully(mock_client):
    mock_client.chat.completions.create.side_effect = Exception("Groq unavailable")

    result = run_agent(SAMPLE_FAILURE)

    assert "agent_output" in result
    assert result["status"] == "failed"


@patch("app.agent.get_session")
def test_search_past_failures_no_results(mock_get_session):
    mock_session = MagicMock()
    mock_get_session.return_value = mock_session
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    result = search_past_failures("shri-5279/PipeLine-AI")
    assert "No past analyzed failures" in result


@patch("app.agent.get_session")
def test_search_past_failures_with_results(mock_get_session):
    mock_session = MagicMock()
    mock_get_session.return_value = mock_session

    mock_failure = MagicMock()
    mock_failure.run_id = "99999"
    mock_failure.branch = "main"
    mock_failure.failure_category = "dependency_error"
    mock_failure.root_cause = "Missing numpy package"
    mock_failure.suggested_fix = "Add numpy to requirements.txt"

    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_failure]

    result = search_past_failures("shri-5279/PipeLine-AI")
    assert "Found 1 past failures" in result


def test_search_github_issues_returns_string():
    result = search_github_issues("pytest ImportError")
    assert isinstance(result, str)
    assert len(result) > 0


@patch("app.agent.client")
def test_run_agent_calls_tools(mock_client):
    # First call returns a tool call, second call returns final answer
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "search_past_failures"
    mock_tool_call.function.arguments = json.dumps(
        {"repository": "shri-5279/PipeLine-AI"}
    )

    mock_message_with_tool = MagicMock()
    mock_message_with_tool.content = ""
    mock_message_with_tool.tool_calls = [mock_tool_call]

    mock_message_final = MagicMock()
    mock_message_final.content = "Based on past failures, update requirements.txt"
    mock_message_final.tool_calls = None

    mock_choice_tool = MagicMock()
    mock_choice_tool.message = mock_message_with_tool

    mock_choice_final = MagicMock()
    mock_choice_final.message = mock_message_final

    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[mock_choice_tool]),
        MagicMock(choices=[mock_choice_final])
    ]

    with patch("app.agent.search_past_failures") as mock_search:
        mock_search.return_value = "Found 1 past failure: dependency_error"
        result = run_agent(SAMPLE_FAILURE)

    assert result["status"] == "completed"