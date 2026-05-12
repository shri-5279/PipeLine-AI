from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from app.storage import save_failure_log
import os
import boto3
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(
    title="PipeLine AI",
    description="AI-powered CI/CD failure analysis",
    version="0.1.0"
)

SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def get_sqs_client():
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


@app.post("/webhook/github")
async def github_webhook(request: Request):
    try:
        payload = await request.json()

        logger.info(f"Received webhook from GitHub")

        event_data = {
            "repository": payload.get("repository", {}).get("full_name", "unknown"),
            "workflow": payload.get("workflow", "unknown"),
            "run_id": payload.get("workflow_run", {}).get("id", "unknown"),
            "conclusion": payload.get("workflow_run", {}).get("conclusion", "unknown"),
            "branch": payload.get("workflow_run", {}).get("head_branch", "unknown"),
            "commit_sha": payload.get("workflow_run", {}).get("head_sha", "unknown"),
            "created_at": payload.get("workflow_run", {}).get("created_at", "unknown"),
        }

        if event_data["conclusion"] != "failure":
            logger.info(f"Skipping non-failure event: {event_data['conclusion']}")
            return {
                "status": "skipped",
                "reason": f"conclusion was {event_data['conclusion']}"
            }

        # Save raw log to S3 first — persist before processing
        s3_key = save_failure_log(event_data)
        logger.info(f"Log saved to S3 at key: {s3_key}")

        # Add S3 key so the processor knows where to find the log
        event_data["s3_key"] = s3_key

        # Push to SQS for async processing
        sqs = get_sqs_client()
        response = sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(event_data)
        )

        message_id = response.get("MessageId", "unknown")
        logger.info(f"Pushed to SQS: {message_id}")

        return {
            "status": "received",
            "message": "Pipeline failure saved and queued for analysis",
            "message_id": message_id,
            "repository": event_data["repository"],
            "s3_key": s3_key
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")