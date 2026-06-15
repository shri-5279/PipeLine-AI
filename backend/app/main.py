from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.storage import save_failure_log
from app.database import get_recent_failures, get_session, PipelineFailure
from app.agent import run_agent
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/failures")
def get_failures():
    try:
        failures = get_recent_failures(limit=10)
        return {
            "status": "success",
            "count": len(failures),
            "failures": failures
        }
    except Exception as e:
        logger.error(f"Failed to retrieve failures: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve failures")


@app.post("/failures/{failure_id}/analyze")
def run_agent_analysis(failure_id: int):
    try:
        session = get_session()
        failure = session.query(PipelineFailure).filter(
            PipelineFailure.id == failure_id
        ).first()
        session.close()

        if not failure:
            raise HTTPException(
                status_code=404,
                detail=f"Failure {failure_id} not found"
            )

        logger.info(f"Running agent analysis for failure_id: {failure_id}")
        agent_result = run_agent(failure.to_dict())

        return {
            "status": "success",
            "failure_id": failure_id,
            "agent_analysis": agent_result["agent_output"],
            "agent_status": agent_result["status"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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

        s3_key = save_failure_log(event_data)
        logger.info(f"Log saved to S3 at key: {s3_key}")

        event_data["s3_key"] = s3_key

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