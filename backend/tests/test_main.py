# TestClient is a tool FastAPI gives us to simulate HTTP requests
# in our tests without actually running a real server
# This means tests run fast and don't need network access
from fastapi.testclient import TestClient

# We import our 'app' object from the file we just wrote
# Python resolves 'app.main' as the file backend/app/main.py
from app.main import app

# Create a test client using our app
# Think of this as a robot browser that talks directly to our API
client = TestClient(app)


# Every test function MUST start with 'test_'
# pytest automatically finds and runs any function starting with test_
# If the function name doesn't start with test_, pytest ignores it

def test_root_status_code():
    # client.get("/") sends a GET request to the "/" path
    # just like your browser does when you visit localhost:8000
    response = client.get("/")

    # 'assert' means "this must be true, otherwise FAIL the test"
    # response.status_code is the HTTP status code that came back
    # 200 means success
    assert response.status_code == 200


def test_root_returns_correct_data():
    response = client.get("/")

    # .json() parses the response body from JSON text into a Python dict
    # so we can check individual fields
    data = response.json()

    # Check that all expected keys exist and have correct values
    assert data["service"] == "PipeLine AI"
    assert data["status"] == "running"
    assert data["version"] == "0.1.0"


def test_health_check_status_code():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_returns_healthy():
    response = client.get("/health")
    data = response.json()

    # Check the status field specifically says "healthy"
    assert data["status"] == "healthy"


def test_webhook_endpoint_exists():
    # We send a POST request to our webhook endpoint
    # client.post() sends a POST — just like GitHub Actions will do
    response = client.post("/webhook/github")

    # 200 means it exists and responded — good enough for now
    assert response.status_code == 200


def test_webhook_returns_received():
    response = client.post("/webhook/github")
    data = response.json()

    # Verify it acknowledges receipt
    assert data["status"] == "received"