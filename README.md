# PipeLine AI

![CI](https://github.com/shri-5279/PipeLine-AI/actions/workflows/ci.yml/badge.svg)

> AI-powered CI/CD failure analysis -> turns 40-minute debug sessions into 30-second answers.

## What it does
When a CI pipeline fails, PipeLine AI automatically reads the failure log,
finds the root cause using AI, searches for known solutions, and gives you
a specific fix — in seconds.

## Architecture
GitHub Actions → Webhook → API Gateway → SQS → Log Ingestion → S3 → Parser → Vector DB → RAG → AI Agent → Dashboard

## Phases
- Phase 0: Foundations ✅
- Phase 1: The Plumbing ✅
- Phase 2: The Intelligence ✅
- Phase 3: The Agent ✅
- Phase 4: The Surface ✅

## Tech Stack
- **Backend:** Python, FastAPI
- **Cloud:** AWS (SQS, S3, RDS, Bedrock, OpenSearch, EKS)
- **AI:** RAG, LLMs, Agentic AI, Vector Databases
- **DevOps:** Docker, Kubernetes, GitHub Actions, Terraform
