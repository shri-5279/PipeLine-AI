from groq import Groq
import json
import logging
import os
import urllib.request
import urllib.parse
from dotenv import load_dotenv
from app.database import get_session, PipelineFailure

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY)


def search_past_failures(repository: str) -> str:
    """Tool 1: Search database for past failures from this repository."""
    try:
        session = get_session()
        failures = session.query(PipelineFailure).filter(
            PipelineFailure.repository == repository,
            PipelineFailure.status == "analyzed",
            PipelineFailure.root_cause.isnot(None)
        ).order_by(
            PipelineFailure.processed_at.desc()
        ).limit(5).all()
        session.close()

        if not failures:
            return f"No past analyzed failures found for repository: {repository}"

        results = []
        for f in failures:
            results.append(
                f"Run {f.run_id} on branch {f.branch}: "
                f"Category={f.failure_category}, "
                f"Root cause={str(f.root_cause)[:100]}, "
                f"Fix={str(f.suggested_fix)[:100]}"
            )
        return f"Found {len(failures)} past failures:\n" + "\n".join(results)

    except Exception as e:
        logger.error(f"Error searching past failures: {str(e)}")
        return f"Error searching past failures: {str(e)}"


def search_github_issues(query: str) -> str:
    """Tool 2: Search GitHub Issues for known solutions."""
    try:
        encoded_query = urllib.parse.quote(f"{query} is:issue")
        url = f"https://api.github.com/search/issues?q={encoded_query}&per_page=3&sort=relevance"

        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", "PipeLine-AI")

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        issues = data.get("items", [])
        if not issues:
            return f"No GitHub issues found for: {query}"

        results = []
        for issue in issues[:3]:
            results.append(
                f"Issue: {issue.get('title', 'No title')}\n"
                f"URL: {issue.get('html_url', '')}\n"
                f"State: {issue.get('state', 'unknown')}"
            )
        return f"Found {len(issues)} GitHub issues:\n\n" + "\n\n".join(results)

    except Exception as e:
        logger.error(f"GitHub search failed: {str(e)}")
        return f"GitHub search unavailable: {str(e)}"


def run_agent(failure_data: dict) -> dict:
    # This implements the agentic loop manually using Groq
    # The LLM decides which tools to call — same concept as LangChain agents
    # but without the dependency conflicts

    logger.info(f"Running agent for failure: {failure_data.get('repository')}")

    # Define tools as a schema the LLM can call
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_past_failures",
                "description": "Search the database for past pipeline failures from a specific repository to find if we have seen similar failures before",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repository": {
                            "type": "string",
                            "description": "The repository name like 'shri-5279/PipeLine-AI'"
                        }
                    },
                    "required": ["repository"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_github_issues",
                "description": "Search GitHub Issues for known solutions to CI/CD problems",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query like 'pytest ImportError missing module'"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    # Map tool names to actual functions
    tool_map = {
        "search_past_failures": search_past_failures,
        "search_github_issues": search_github_issues
    }

    messages = [
        {
            "role": "system",
            "content": """You are an expert DevOps engineer investigating CI/CD pipeline failures.
Your job is to:
1. Search for past similar failures in our database
2. Search GitHub Issues for known solutions if needed
3. Synthesize everything into a comprehensive fix recommendation

Always search past failures first, then GitHub Issues if the failure category suggests a known library issue."""
        },
        {
            "role": "user",
            "content": f"""Analyze this CI/CD pipeline failure:

Repository: {failure_data.get('repository', 'unknown')}
Workflow: {failure_data.get('workflow', 'unknown')}
Branch: {failure_data.get('branch', 'unknown')}
Commit SHA: {failure_data.get('commit_sha', 'unknown')}
Initial AI analysis: {failure_data.get('root_cause', 'Not available')}
Failure category: {failure_data.get('failure_category', 'unknown')}

Search for past similar failures and GitHub issues, then provide a comprehensive fix recommendation."""
        }
    ]

    try:
        # Agentic loop — runs until the LLM stops calling tools
        # Max 5 iterations to prevent infinite loops
        for iteration in range(5):
            logger.info(f"Agent iteration {iteration + 1}")

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=2000,
                temperature=0
            )

            message = response.choices[0].message

            # If no tool calls — the agent is done, return its final answer
            if not message.tool_calls:
                logger.info("Agent finished — no more tool calls")
                return {
                    "agent_output": message.content,
                    "status": "completed",
                    "iterations": iteration + 1
                }

            # Add the assistant's message to history
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            # Execute each tool the agent called
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                logger.info(f"Agent calling tool: {tool_name} with args: {tool_args}")

                # Call the actual tool function
                if tool_name in tool_map:
                    tool_result = tool_map[tool_name](**tool_args)
                else:
                    tool_result = f"Unknown tool: {tool_name}"

                logger.info(f"Tool result preview: {str(tool_result)[:100]}")

                # Add the tool result back to the conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })

        # If we hit max iterations, return what we have
        return {
            "agent_output": "Agent reached maximum iterations. Please review manually.",
            "status": "max_iterations_reached",
            "iterations": 5
        }

    except Exception as e:
        logger.error(f"Agent execution failed: {str(e)}")
        return {
            "agent_output": f"Agent analysis failed: {str(e)}",
            "status": "failed"
        }