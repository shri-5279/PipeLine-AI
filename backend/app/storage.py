import boto3
import json
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def get_s3_client():
    # Creates and returns a boto3 S3 client
    # boto3 automatically uses your AWS credentials from
    # the ~/.aws/credentials file we configured earlier
    return boto3.client("s3", region_name=AWS_REGION)


def build_s3_key(event_data: dict) -> str:
    # Builds the file path (key) where the log will live inside S3
    # Format: failures/{owner}/{repo}/{date}/run-{run_id}.json
    # Example: failures/shri-5279/test-repo/2024-01-15/run-99999.json

    # Get today's date in UTC as a string like "2024-01-15"
    # UTC = Coordinated Universal Time — standard timezone for servers worldwide
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Repository comes as "owner/repo-name" — split it into two parts
    repository = event_data.get("repository", "unknown/unknown")
    parts = repository.split("/")
    owner = parts[0] if len(parts) > 0 else "unknown"
    repo = parts[1] if len(parts) > 1 else "unknown"

    run_id = event_data.get("run_id", "unknown")

    return f"failures/{owner}/{repo}/{date_str}/run-{run_id}.json"


def save_failure_log(event_data: dict) -> str:
    # Saves a failure event dictionary to S3 as a JSON file
    # Returns the S3 key (path) where the file was saved

    try:
        s3 = get_s3_client()

        # Build the S3 path for this specific failure
        s3_key = build_s3_key(event_data)

        # Stamp exactly when we stored this
        event_data["stored_at"] = datetime.utcnow().isoformat()

        # Convert Python dict → JSON string
        # indent=2 makes it human-readable if you open it in S3
        log_content = json.dumps(event_data, indent=2)

        # Upload the file to S3
        # Bucket = the container
        # Key = the file path inside the container
        # Body = the actual file content
        # ContentType = tells S3 this is a JSON file
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=log_content,
            ContentType="application/json"
        )

        logger.info(f"Saved failure log to S3: s3://{S3_BUCKET_NAME}/{s3_key}")
        return s3_key

    except Exception as e:
        logger.error(f"Failed to save log to S3: {str(e)}")
        raise


def get_failure_log(s3_key: str) -> dict:
    # Retrieves a previously saved failure log from S3
    # Returns the log as a Python dictionary
    # Phase 2 will use this when the AI needs to read and analyze the log

    try:
        s3 = get_s3_client()

        # Download the file from S3
        response = s3.get_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key
        )

        # response["Body"] is raw bytes — decode to string first
        # then parse the JSON string into a Python dict
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)

    except Exception as e:
        logger.error(f"Failed to retrieve log from S3: {str(e)}")
        raise