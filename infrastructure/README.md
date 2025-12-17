# Infrastructure

Deployment and local orchestration assets for Alfred.

## Contents

- `aws/` – Terraform/CloudFormation or helper scripts for deploying Alfred services to AWS environments.
- `local/` – tooling for running dependencies locally (e.g., Postgres, MinIO) outside docker-compose.
- `docker-compose.yml` – spins up local service dependencies (database, vector store, etc.) for development and testing.
