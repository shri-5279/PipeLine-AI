import boto3
import json
import logging
import time
import os
from dotenv import load_dotenv
from app.storage import get_failure_log

load_dotenv()

# Set up logging with a format that includes the timestamp
# This is important for a background worker because you need to know
# exactly WHEN each thing happened when reading logs later
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# How many seconds to wait between polling SQS when the queue is empty
# We don't want to hammer AWS with thousands of requests per second
# when there's nothing to process — that wastes money and resources
POLL_INTERVAL_SECONDS = 5

# How many messages to fetch in one SQS request
# SQS allows a maximum of 10 per request
# Fetching multiple at once is more efficient than one at a time
MAX_MESSAGES_PER_POLL = 10

# How long SQS should hide a message from other consumers while we process it
# If we don't delete the message within this time, SQS assumes we crashed
# and makes the message visible again for reprocessing
# 300 seconds = 5 minutes — plenty of time for our processing
VISIBILITY_TIMEOUT = 300


def get_sqs_client():
    return boto3.client("sqs", region_name=AWS_REGION)


def parse_failure_log(event_data: dict) -> dict:
    # This function takes the raw event data and extracts
    # structured, meaningful information from it
    # Right now it's simple — in Phase 2 the AI will do this step
    # For now we just organize what we already have

    logger.info(f"Parsing failure log for repo: {event_data.get('repository')}")

    # Extract key fields and add derived information
    parsed = {
        # Core identity fields
        "repository": event_data.get("repository", "unknown"),
        "workflow": event_data.get("workflow", "unknown"),
        "run_id": event_data.get("run_id", "unknown"),
        "branch": event_data.get("branch", "unknown"),
        "commit_sha": event_data.get("commit_sha", "unknown"),

        # Timing fields
        "created_at": event_data.get("created_at", "unknown"),
        "stored_at": event_data.get("stored_at", "unknown"),

        # Where the raw log lives in S3 — Phase 2 AI will read from here
        "s3_key": event_data.get("s3_key", "unknown"),

        # Status — will be enriched by AI in Phase 2
        # For now we just mark it as "pending_analysis"
        "status": "pending_analysis",

        # Placeholder for AI analysis results — Phase 2 fills these in
        "root_cause": None,
        "suggested_fix": None,
        "failure_category": None,
    }

    logger.info(f"Parsed failure event for run_id: {parsed['run_id']}")
    return parsed


def process_message(message: dict) -> bool:
    # Processes a single SQS message
    # Returns True if successful, False if something went wrong
    # The caller uses this return value to decide whether to delete the message

    try:
        # message["Body"] is a JSON STRING — we need to parse it back
        # into a Python dictionary
        # Remember in main.py we did json.dumps() to convert dict → string
        # Now we do json.loads() to go the other way: string → dict
        event_data = json.loads(message["Body"])

        logger.info(f"Processing message for repository: {event_data.get('repository')}")

        # Step 1: Fetch the full log from S3 if we have the key
        # This confirms S3 storage is working end-to-end
        s3_key = event_data.get("s3_key")
        if s3_key and s3_key != "unknown":
            try:
                # Read the log back from S3
                raw_log = get_failure_log(s3_key)
                logger.info(f"Successfully retrieved log from S3: {s3_key}")
                logger.info(f"Log keys: {list(raw_log.keys())}")
            except Exception as e:
                # If S3 fetch fails, log it but continue
                # The event_data we already have is enough to proceed
                logger.warning(f"Could not fetch from S3 (continuing anyway): {str(e)}")

        # Step 2: Parse and structure the failure data
        parsed_data = parse_failure_log(event_data)

        # Step 3: Store in PostgreSQL (coming in next step)
        # For now just log what we would store
        logger.info(f"Would store to DB: {json.dumps(parsed_data, indent=2)}")

        # Step 4: Return True to signal successful processing
        # The polling loop will then delete this message from SQS
        logger.info(f"Successfully processed run_id: {parsed_data['run_id']}")
        return True

    except json.JSONDecodeError as e:
        # The message body wasn't valid JSON — this message is corrupted
        # Return True anyway so it gets deleted (no point retrying bad data)
        logger.error(f"Invalid JSON in message body: {str(e)}")
        return True

    except Exception as e:
        # Something unexpected went wrong
        # Return False — message stays in queue and will be retried
        logger.error(f"Failed to process message: {str(e)}")
        return False


def delete_message(sqs, receipt_handle: str):
    # Deletes a message from SQS after successful processing
    # 'receipt_handle' is a temporary token SQS gives you when you receive
    # a message — it's like a claim ticket. You give it back to delete the message.
    # It's different from MessageId — receipt_handle is specific to THIS receive operation
    try:
        sqs.delete_message(
            QueueUrl=SQS_QUEUE_URL,
            ReceiptHandle=receipt_handle
        )
        logger.info("Message deleted from SQS successfully")
    except Exception as e:
        logger.error(f"Failed to delete message from SQS: {str(e)}")


def poll_queue():
    # This is the main loop — it runs forever, continuously checking SQS
    # for new messages and processing them one batch at a time

    logger.info("Starting PipeLine AI ingestion service...")
    logger.info(f"Polling queue: {SQS_QUEUE_URL}")
    logger.info(f"Poll interval: {POLL_INTERVAL_SECONDS} seconds")

    sqs = get_sqs_client()

    # 'while True' creates an infinite loop
    # This is intentional — the worker should run forever until stopped
    # You stop it with Ctrl+C which raises a KeyboardInterrupt exception
    while True:
        try:
            # Ask SQS for messages
            # WaitTimeSeconds=20 is called "long polling"
            # Instead of immediately returning empty if no messages,
            # SQS waits UP TO 20 seconds for a message to arrive
            # This is much more efficient than short polling (which returns
            # immediately and makes you loop rapidly burning API calls)
            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=MAX_MESSAGES_PER_POLL,
                WaitTimeSeconds=20,
                VisibilityTimeout=VISIBILITY_TIMEOUT,
                # AttributeNames tells SQS to include extra metadata
                # about each message (like when it was sent)
                AttributeNames=["All"]
            )

            # SQS returns an empty dict if no messages — .get() handles this safely
            messages = response.get("Messages", [])

            if not messages:
                # Queue is empty — wait before polling again
                logger.info(f"Queue empty — waiting {POLL_INTERVAL_SECONDS}s before next poll")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # We got messages — process each one
            logger.info(f"Received {len(messages)} message(s) from SQS")

            for message in messages:
                # Process the message
                success = process_message(message)

                if success:
                    # Processing succeeded — delete from queue
                    # If we don't delete it, SQS will make it visible again
                    # after the VisibilityTimeout and it will be reprocessed
                    delete_message(sqs, message["ReceiptHandle"])
                else:
                    # Processing failed — leave in queue for retry
                    # SQS will make it visible again after VisibilityTimeout
                    logger.warning("Message processing failed — leaving in queue for retry")

        except KeyboardInterrupt:
            # This is triggered when you press Ctrl+C
            # We catch it gracefully so the service shuts down cleanly
            # instead of crashing with an ugly traceback
            logger.info("Shutdown signal received — stopping ingestion service")
            break

        except Exception as e:
            # Something unexpected happened in the polling loop itself
            # Log it and keep going — a worker should never die from one bad iteration
            logger.error(f"Error in polling loop: {str(e)}")
            time.sleep(POLL_INTERVAL_SECONDS)


# This block only runs when you execute this file directly
# i.e. 'python ingestion.py' or 'python -m app.ingestion'
# It does NOT run when the file is imported by another module
# '__name__' is a special Python variable:
#   - When you run a file directly: __name__ == "__main__"
#   - When a file is imported: __name__ == the module name (e.g. "app.ingestion")
if __name__ == "__main__":
    poll_queue()