import boto3
import json
import logging
import time
import os
from dotenv import load_dotenv
from app.storage import get_failure_log
from app.database import save_failure_to_db, create_tables, update_failure_analysis
from app.ai_analyzer import analyze_failure

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

POLL_INTERVAL_SECONDS = 5
MAX_MESSAGES_PER_POLL = 10
VISIBILITY_TIMEOUT = 300


def get_sqs_client():
    return boto3.client("sqs", region_name=AWS_REGION)


def parse_failure_log(event_data: dict) -> dict:
    logger.info(f"Parsing failure log for repo: {event_data.get('repository')}")

    parsed = {
        "repository": event_data.get("repository", "unknown"),
        "workflow": event_data.get("workflow", "unknown"),
        "run_id": event_data.get("run_id", "unknown"),
        "branch": event_data.get("branch", "unknown"),
        "commit_sha": event_data.get("commit_sha", "unknown"),
        "created_at": event_data.get("created_at", "unknown"),
        "stored_at": event_data.get("stored_at", "unknown"),
        "s3_key": event_data.get("s3_key", "unknown"),
        "status": "pending_analysis",
        "root_cause": None,
        "suggested_fix": None,
        "failure_category": None,
    }

    logger.info(f"Parsed failure event for run_id: {parsed['run_id']}")
    return parsed


def process_message(message: dict) -> bool:
    try:
        event_data = json.loads(message["Body"])
        logger.info(f"Processing message for repository: {event_data.get('repository')}")

        # Fetch from S3
        s3_key = event_data.get("s3_key")
        if s3_key and s3_key != "unknown":
            try:
                raw_log = get_failure_log(s3_key)
                logger.info(f"Successfully retrieved log from S3: {s3_key}")
                logger.info(f"Log keys: {list(raw_log.keys())}")
            except Exception as e:
                logger.warning(f"Could not fetch from S3 (continuing anyway): {str(e)}")

        # Parse the failure data
        parsed_data = parse_failure_log(event_data)

        # Save initial record to PostgreSQL
        db_id = save_failure_to_db(parsed_data)
        logger.info(f"Saved to PostgreSQL with id: {db_id}")

        # Run AI analysis
        logger.info(f"Running AI analysis for run_id: {parsed_data['run_id']}")
        ai_result = analyze_failure(event_data)

        # Update the database record with AI analysis results
        update_failure_analysis(db_id, ai_result)
        logger.info(f"AI analysis saved — category: {ai_result['failure_category']}")
        logger.info(f"Root cause: {ai_result['root_cause'][:100]}...")

        logger.info(f"Successfully processed run_id: {parsed_data['run_id']}")
        return True

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in message body: {str(e)}")
        return True

    except Exception as e:
        logger.error(f"Failed to process message: {str(e)}")
        return False


def delete_message(sqs, receipt_handle: str):
    try:
        sqs.delete_message(
            QueueUrl=SQS_QUEUE_URL,
            ReceiptHandle=receipt_handle
        )
        logger.info("Message deleted from SQS successfully")
    except Exception as e:
        logger.error(f"Failed to delete message from SQS: {str(e)}")


def poll_queue():
    logger.info("Starting PipeLine AI ingestion service...")
    logger.info(f"Polling queue: {SQS_QUEUE_URL}")

    logger.info("Initializing database tables...")
    create_tables()

    sqs = get_sqs_client()

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=MAX_MESSAGES_PER_POLL,
                WaitTimeSeconds=20,
                VisibilityTimeout=VISIBILITY_TIMEOUT,
                AttributeNames=["All"]
            )

            messages = response.get("Messages", [])

            if not messages:
                logger.info(f"Queue empty — waiting {POLL_INTERVAL_SECONDS}s before next poll")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            logger.info(f"Received {len(messages)} message(s) from SQS")

            for message in messages:
                success = process_message(message)
                if success:
                    delete_message(sqs, message["ReceiptHandle"])
                else:
                    logger.warning("Message processing failed — leaving in queue for retry")

        except KeyboardInterrupt:
            logger.info("Shutdown signal received — stopping ingestion service")
            break

        except Exception as e:
            logger.error(f"Error in polling loop: {str(e)}")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    poll_queue()