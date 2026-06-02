from groq import Groq
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY)


def analyze_failure(event_data: dict) -> dict:
    logger.info(f"Analyzing failure for repo: {event_data.get('repository')}")

    prompt = f"""You are an expert DevOps engineer analyzing CI/CD pipeline failures.

Analyze this pipeline failure and provide a detailed diagnosis:

Repository: {event_data.get('repository', 'unknown')}
Workflow: {event_data.get('workflow', 'unknown')}
Branch: {event_data.get('branch', 'unknown')}
Commit SHA: {event_data.get('commit_sha', 'unknown')}
Failed at: {event_data.get('created_at', 'unknown')}

Respond ONLY with a JSON object in this exact format, no markdown, no backticks:
{{
    "root_cause": "A specific actionable description of what caused this failure",
    "suggested_fix": "Step-by-step instructions to fix this issue",
    "failure_category": "one of: dependency_error, test_failure, build_error, infrastructure_error, auth_error, timeout, configuration_error, unknown",
    "confidence": "high, medium, or low",
    "additional_context": "Any other relevant information"
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=1000,
            temperature=0.1
        )

        ai_response_text = response.choices[0].message.content.strip()

        # Strip markdown code blocks if present
        if ai_response_text.startswith("```"):
            ai_response_text = ai_response_text.split("```")[1]
            if ai_response_text.startswith("json"):
                ai_response_text = ai_response_text[4:]
        ai_response_text = ai_response_text.strip()

        ai_analysis = json.loads(ai_response_text)

        logger.info(f"AI analysis complete. Category: {ai_analysis.get('failure_category')}")
        logger.info(f"Confidence: {ai_analysis.get('confidence')}")

        return {
            "root_cause": ai_analysis.get("root_cause", "Unable to determine root cause"),
            "suggested_fix": ai_analysis.get("suggested_fix", "Please review the logs manually"),
            "failure_category": ai_analysis.get("failure_category", "unknown"),
            "confidence": ai_analysis.get("confidence", "low"),
            "additional_context": ai_analysis.get("additional_context", "")
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {str(e)}")
        return {
            "root_cause": "AI analysis failed to parse response",
            "suggested_fix": "Please review the logs manually",
            "failure_category": "unknown",
            "confidence": "low",
            "additional_context": ""
        }

    except Exception as e:
        logger.error(f"Groq API call failed: {str(e)}")
        return {
            "root_cause": f"AI analysis unavailable: {str(e)}",
            "suggested_fix": "Please review the logs manually",
            "failure_category": "unknown",
            "confidence": "low",
            "additional_context": ""
        }