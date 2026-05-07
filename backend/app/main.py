# FastAPI is the framework we import to build our API
# A framework is pre-written code that handles the repetitive boring parts
# so you only write the parts unique to your application
from fastapi import FastAPI

# We import a specific tool from FastAPI called Response
# We'll use this to control exactly what we send back
from fastapi.responses import JSONResponse

# load_dotenv reads your .env file and loads the key=value pairs
# inside it into your program's memory as environment variables
from dotenv import load_dotenv

# 'os' is a built-in Python module that lets you interact with
# the operating system — we use it to READ environment variables
import os

# Call load_dotenv() early — before anything else
# This must run before you try to read any env variables
# otherwise they won't exist yet in memory
load_dotenv()

# Create the FastAPI application instance
# This 'app' object is the heart of everything
# Every route, every endpoint, every setting attaches to this object
# The title and description show up in the auto-generated docs page
app = FastAPI(
    title="PipeLine AI",
    description="AI-powered CI/CD failure analysis — turns 40-minute debug sessions into 30-second answers",
    version="0.1.0"
)

# This is a ROUTE DECORATOR
# A decorator in Python starts with '@' and sits directly above a function
# It wraps that function with extra behaviour
# '@app.get("/")' means:
#   - Listen for HTTP GET requests
#   - On the path "/" (the root, like visiting a homepage)
#   - When one arrives, run the function below
@app.get("/")
def root():
    # This function returns a Python dictionary
    # FastAPI automatically converts any dictionary you return
    # into JSON format — the universal language of APIs
    # JSON looks like: {"key": "value"}
    return {
        "service": "PipeLine AI",
        "status": "running",
        "version": "0.1.0",
        "message": "Welcome to PipeLine AI"
    }


# A health check endpoint is an industry standard
# Every production service exposes /health
# Monitoring tools, load balancers, and Kubernetes ping this endpoint
# to check if the service is alive and healthy
# If /health returns 200, the service is up
# If it doesn't respond, something is wrong
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "PipeLine AI",
        "version": "0.1.0"
    }


# This is the most important endpoint in the entire project
# It will receive failure logs from GitHub Actions via webhook
# For now it's a STUB — meaning it exists but doesn't do real work yet
# We're building the skeleton first, then adding muscle in Phase 1
# 'POST' because GitHub is SENDING us data, not asking for data
@app.post("/webhook/github")
def github_webhook():
    # For now we just acknowledge we received something
    # In Phase 1 this will parse the real GitHub Actions payload
    # and push it into our SQS queue for processing
    return {
        "status": "received",
        "message": "Webhook received — processing pipeline failure"
    }