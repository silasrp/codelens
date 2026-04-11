# CodeLens 🔍

> LLM-powered codebase analysis and documentation platform

CodeLens parses any repository with tree-sitter, builds a semantic dependency
graph with NetworkX, then runs a three-pass GPT-4o pipeline to produce
structured documentation and enable natural language search over the codebase.

## What makes this non-trivial

| Feature | Implementation |
|---|---|
| **Multi-pass LLM** | Pass 1: per-symbol docstrings (parallel). Pass 2: module summaries with upstream context. Pass 3: architecture narrative from graph |
| **Semantic chunking** | tree-sitter AST split by logical unit — never by line count |
| **Dependency graph** | NetworkX import graph with cycle detection and centrality metrics |
| **Async pipeline** | FastAPI → SQS → Lambda, DynamoDB tracks state, S3 stores artefacts |
| **Semantic search** | voyage-code-3 embeddings in Qdrant, natural language queries |

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, TanStack Query |
| Backend | FastAPI, Python 3.12 |
| LLM | OpenAI GPT-4o (3-pass pipeline) |
| Embeddings | Voyage AI voyage-code-3 |
| Vector DB | Qdrant |
| Async | AWS Lambda + SQS |
| State | AWS DynamoDB |
| Storage | AWS S3 |
| Infrastructure | AWS CDK (TypeScript) |
| Local dev | LocalStack + Docker Compose |

## Getting started

```bash
cp .env.example .env        # fill in OPENAI_API_KEY and VOYAGE_API_KEY
make infra-up               # starts LocalStack + Qdrant, creates all resources
```

```bash
cd services/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v            # 25 tests, all should pass
uvicorn main:app --reload --port 8000
```

```bash
cd frontend
npm install && npm run dev  # http://localhost:5173
```

See the full step-by-step restart guide in `RESTART.md`.

## Deploy to AWS

```bash
# Store secrets
aws ssm put-parameter --name "/codelens/openai-api-key" --value "sk-..." --type SecureString --region eu-west-2
aws ssm put-parameter --name "/codelens/voyage-api-key" --value "pa-..." --type SecureString --region eu-west-2
aws ssm put-parameter --name "/codelens/qdrant-url"     --value "https://..." --type String --region eu-west-2
aws ssm put-parameter --name "/codelens/qdrant-api-key" --value "..." --type SecureString --region eu-west-2

cd infrastructure && npm install
cdk bootstrap aws://ACCOUNT_ID/eu-west-2
ENVIRONMENT=dev cdk deploy
```
