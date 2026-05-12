from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
import os
import boto3
import json
import logging

# logging is a built-in Python module for printing messages
# It's better than 'print()' for real applications because:
# - You can set levels (DEBUG, INFO, WARNING, ERROR)
# - You can easily turn off debug logs in production
# - Logs include timestamps and severity automatically
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="PipeLine AI",
    description="AI-powered CI/CD failure analysis",
    version="0.1.0"
)

# Read environment variables we set in .env
# os.getenv() reads a variable by name
# The second argument is the DEFAULT value if the variable isn't found
# This prevents your app from crashing if someone forgets to set a variable
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def get_sqs_client():
    # boto3 is the AWS SDK — it lets Python talk to AWS services
    # boto3.client() creates a client for a specific AWS service
    # 'sqs' tells it we want to talk to the Simple Queue Service
    # region_name tells it which AWS data center to use
    return boto3.client("sqs", region_name=AWS_REGION)


@app.get("/")
def root():
    return {
        "service": "PipeLine AI",
        "status": "running",
        "version": "0.1.0",
        "message": "Welcome to PipeLine AI"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "PipeLine AI",
        "version": "0.1.0"
    }


# Request is a FastAPI object that represents the incoming HTTP request
# It gives us access to the body, headers, method, URL — everything
@app.post("/webhook/github")
async def github_webhook(request: Request):
    # 'async' means this function can pause and wait for slow operations
    # (like network calls to AWS) without blocking other requests
    # This is important for performance — while waiting for AWS to respond,
    # FastAPI can handle other incoming requests
    try:
        # request.json() reads the body of the POST request
        # and parses it from JSON text into a Python dictionary
        # 'await' means "wait for this to finish before continuing"
        # We use await because reading the request body is an I/O operation
        payload = await request.json()

        # Log that we received something — helpful for debugging
        logger.info(f"Received webhook from GitHub")
        logger.info(f"Repository: {payload.get('repository', {}).get('full_name', 'unknown')}")

        # Extract the important fields from the GitHub Actions payload
        # .get() safely reads a key from a dict — returns None if key doesn't exist
        # This prevents KeyError crashes if GitHub sends unexpected data
        event_data = {
            # The repository where the pipeline ran
            "repository": payload.get("repository", {}).get("full_name", "unknown"),

            # The workflow that failed (e.g. "CI Pipeline")
            "workflow": payload.get("workflow", "unknown"),

            # The specific run ID — unique identifier for this pipeline run
            "run_id": payload.get("workflow_run", {}).get("id", "unknown"),

            # Was it a failure? success? cancelled?
            "conclusion": payload.get("workflow_run", {}).get("conclusion", "unknown"),

            # Which branch triggered this
            "branch": payload.get("workflow_run", {}).get("head_branch", "unknown"),

            # The commit that triggered this pipeline
            "commit_sha": payload.get("workflow_run", {}).get("head_sha", "unknown"),

            # When it happened
            "created_at": payload.get("workflow_run", {}).get("created_at", "unknown"),
        }

        # Only process failures — we don't care about successful runs
        # This is a business logic decision: why store and analyze success?
        if event_data["conclusion"] != "failure":
            logger.info(f"Pipeline conclusion was '{event_data['conclusion']}' — skipping")
            return {
                "status": "skipped",
                "reason": f"conclusion was {event_data['conclusion']}, only failures are processed"
            }

        # Push the failure event to SQS
        # This is the key architectural step — we're decoupling receipt from processing
        sqs = get_sqs_client()

        # sqs.send_message() puts a message onto our queue
        # MessageBody must be a STRING — so we convert our dict to JSON text
        # json.dumps() = "dump to string" (converts Python dict → JSON string)
        response = sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(event_data)
        )

        # The MessageId is SQS's unique ID for this message
        message_id = response.get("MessageId", "unknown")
        logger.info(f"Pushed to SQS with MessageId: {message_id}")

        # Respond to GitHub immediately — fast acknowledgement
        # GitHub expects a response within 10 seconds or it retries
        # Since we're just dropping into a queue, this is nearly instant
        return {
            "status": "received",
            "message": "Pipeline failure queued for analysis",
            "message_id": message_id,
            "repository": event_data["repository"]
        }

    except json.JSONDecodeError:
        # If the body isn't valid JSON, raise an HTTP 400 error
        # 400 = Bad Request — the caller sent us something malformed
        # HTTPException is FastAPI's way of returning error responses
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    except Exception as e:
        # Catch any other unexpected error
        # Log it so we can debug it, but don't expose internal details
        # to the caller — that's a security best practice
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")