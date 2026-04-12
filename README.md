# CodeLens

**LLM-powered codebase analysis and documentation platform**

CodeLens takes any GitHub repository, parses it with a real AST parser, constructs a module dependency graph, then runs a three-pass GPT-4o pipeline that produces structured documentation — not just file summaries, but a genuine understanding of how a codebase is architected. The output is searchable with natural language via a code-optimised embedding model.

> Built as a demonstration of non-trivial LLM integration: static analysis, async distributed architecture, semantic chunking, and vector search — all working together in production on AWS.

**Live demo:** [http://codelens-frontend-017562255303.s3-website.eu-west-2.amazonaws.com/]

---

## Why this is non-trivial

Most LLM + code projects send a file to an API and ask for a summary. CodeLens does something more interesting:

- **AST-level parsing** — tree-sitter builds a full syntax tree. Symbols are extracted by type (function, class, method) with line ranges, docstrings, and parent relationships — not by splitting on newlines.
- **Semantic chunking** — chunks are formed around logical units (a class with its methods stays together) and respect a token budget, with import context prepended so the model has full scope.
- **Dependency graph** — NetworkX constructs a directed import graph across the repository. Cycle detection, centrality metrics, and topological ordering are computed before any LLM call is made.
- **Three-pass analysis** — each pass builds on the previous. Pass 3 has access to the full dependency graph and all module summaries before generating the architecture narrative.
- **Production async pipeline** — jobs are submitted via REST, queued in SQS, processed by Lambda, tracked in DynamoDB, and persisted in S3. Nothing blocks the API layer.
- **Semantic search** — chunks are embedded with `voyage-code-3` (a code-optimised model) and stored in Qdrant. Natural language queries are embedded at search time for genuine semantic retrieval.

---

## Architecture

<img width="1378" height="1116" alt="image" src="https://github.com/user-attachments/assets/c51848e8-3677-4e7a-9cd4-30e0d567d864" />


---

## How it works

### Ingestion

When you submit a repository URL, FastAPI clones it with `gitpython` (depth=1 for speed), uploads the source files to S3, creates a job record in DynamoDB, and enqueues an SQS message. The HTTP response returns immediately with a `job_id`. The frontend polls `/api/analysis/status/{job_id}` every 2.5 seconds.

### Static analysis (inside Lambda)

Lambda picks up the SQS message and begins the analysis pipeline:

**1. AST parsing** — tree-sitter parses every `.py`, `.ts`, and `.js` file into a concrete syntax tree. The parser walks the tree and extracts `CodeSymbol` objects — each with a name, kind (function/class/method), source text, line range, and any existing docstring. This is language-aware: it understands `async def`, arrow functions, class inheritance, and method ownership.

**2. Semantic chunking** — the chunker groups symbols into LLM-ready chunks. Classes are kept together with their methods (up to a token budget). When a class exceeds the budget, its methods are split into separate chunks, each with the class header prepended as context. Free functions are batched greedily. Import blocks are always prepended so the model sees full scope. Chunks are content-addressed with a stable SHA-256 ID.

**3. Dependency graph** — `DependencyGraph.build()` creates a NetworkX `DiGraph` where nodes are modules and edges are resolved import relationships. It computes cycle detection (`nx.simple_cycles`), in/out-degree centrality, topological sort, and isolated modules. The graph metrics are serialised into a prose narrative that gets injected into Pass 3.

### Three-pass LLM analysis

**Pass 1 — Symbol documentation (parallel)**

Every chunk is sent to GPT-4o concurrently, subject to a three-layer rate limiter:
- A sliding 60-second token budget window prevents pre-emptive over-submission
- An `asyncio.Semaphore` caps simultaneous in-flight requests
- Exponential backoff with jitter handles any 429s that slip through

Each call returns a structured docstring for every symbol in the chunk: what it does, non-obvious behaviour, and return conditions.

**Pass 2 — Module summaries (sequential, topological order)**

Modules are processed in dependency order — leaves first, so when a module is summarised, its dependencies have already been summarised. The prompt for each module injects:
- All Pass 1 outputs for that module's symbols
- The module's position in the dependency graph (what imports it, what it imports)
- Up to 5 upstream dependency summaries as additional context

The output is a 3–5 paragraph technical summary covering purpose, responsibilities, key abstractions, design decisions, and integration with the broader system.

**Pass 3 — Architecture narrative (single call)**

One final call receives:
- The full dependency graph adjacency list
- The graph metrics narrative (centrality, cycles, isolation)
- All Pass 2 module summaries (truncated to fit context)

GPT-4o produces a `ARCHITECTURE.md` covering system overview, layer structure, key data flows, coupling analysis, and recommended reading order for new engineers joining the codebase.

### Embedding and indexing

After the three passes, every chunk (code + Pass 1 documentation) is embedded using `voyage-code-3` — Voyage AI's model trained specifically on code. Embeddings are upserted into a Qdrant Cloud collection named `codelens_{job_id}`. The Qdrant collection persists between sessions so previously-analysed repositories remain searchable.

### Semantic search

When a user queries the codebase, the query string is embedded with `voyage-code-3` using `input_type="query"` (a separate embedding pathway optimised for retrieval). Qdrant returns the top-k chunks by cosine similarity. Each result surfaces the symbol names, file path, similarity score, code snippet, and the LLM-generated documentation.

---

## Architecture layers explained

| Layer | Technology | Responsibility |
|---|---|---|
| **Frontend** | React 18, TypeScript, Vite, TanStack Query | Repository submission, real-time job progress, semantic search UI, architecture viewer |
| **API** | FastAPI, Python 3.12 | HTTP interface, repository cloning, S3 upload, SQS enqueue, DynamoDB poll |
| **Job queue** | AWS SQS | Decouples the API from analysis. Visibility timeout of 15 minutes matches Lambda timeout. Dead-letter queue captures failed jobs after 3 retries |
| **Orchestrator** | AWS Lambda (Docker image) | Runs the full analysis pipeline. Docker image used because tree-sitter requires compiled C extensions that can't be layered |
| **State** | AWS DynamoDB (PAY_PER_REQUEST) | Job lifecycle tracking with TTL auto-expiry. GSI on status+created_at for dashboard queries |
| **Storage** | AWS S3 | Raw source upload (7-day lifecycle expiry) and generated documentation (ARCHITECTURE.md, per-module .md files, manifest.json) |
| **AST parser** | tree-sitter | Language-aware symbol extraction for Python, TypeScript, JavaScript. Produces structured `CodeSymbol` objects, not line-count chunks |
| **Chunker** | Custom (Python) | Groups symbols into token-budgeted chunks that keep class+methods together, prepend import context, and produce stable content-addressed IDs |
| **Dependency graph** | NetworkX | Directed import graph with cycle detection, topological sort, and centrality metrics. Graph narrative injected into Pass 3 prompt |
| **LLM** | OpenAI GPT-4o | Three-pass analysis pipeline. Async parallel for Pass 1, sequential topological for Pass 2, single call for Pass 3 |
| **Embeddings** | Voyage AI voyage-code-3 | Code-optimised embedding model. Separate `document` and `query` input types for better retrieval quality |
| **Vector DB** | Qdrant Cloud | Per-job collections, cosine similarity search, payload filtering by language |
| **Infrastructure** | AWS CDK (TypeScript) | All AWS resources defined as code: Lambda, SQS, DynamoDB, S3, IAM roles, event source mappings |

---

## Tech stack

```
Frontend:    React 18 · TypeScript · Vite · TanStack Query
Backend:     FastAPI · Python 3.12 · boto3
Analysis:    tree-sitter · NetworkX · custom chunker
LLM:         OpenAI GPT-4o (3-pass pipeline)
Embeddings:  Voyage AI voyage-code-3
Vector DB:   Qdrant Cloud
AWS:         Lambda · SQS · DynamoDB · S3 · EC2 · CDK
Hosting:     S3 static (frontend) · EC2 systemd service (API)
```

---

## Getting started

### Prerequisites

- Python 3.12+, Node 20+, Docker
- AWS account with CLI configured
- OpenAI API key, Voyage AI API key, Qdrant Cloud cluster

### Local development

```bash
cp .env.example .env          # fill in your keys
make infra-up                 # starts LocalStack + Qdrant, creates AWS resources

cd services/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v              # 25 tests, all passing
uvicorn main:app --reload --port 8000

cd frontend
npm install && npm run dev    # http://localhost:5173
```

### Deploy to AWS

```bash
# Store secrets
aws ssm put-parameter --name "/codelens/openai-api-key"  --value "sk-..." --type String --region eu-west-2
aws ssm put-parameter --name "/codelens/voyage-api-key"  --value "pa-..." --type String --region eu-west-2
aws ssm put-parameter --name "/codelens/qdrant-url"      --value "https://..." --type String --region eu-west-2
aws ssm put-parameter --name "/codelens/qdrant-api-key"  --value "..." --type String --region eu-west-2

cd infrastructure
npm install
cdk bootstrap aws://ACCOUNT_ID/eu-west-2
ENVIRONMENT=dev cdk deploy
```

---

## Project structure

```
codelens/
├── infrastructure/              # AWS CDK stack (TypeScript)
│   └── lib/codelens-stack.ts    # Lambda, SQS, DynamoDB, S3, IAM
├── services/
│   ├── api/                     # FastAPI — REST, job management
│   │   ├── core/                # parser.py, chunker.py, graph.py
│   │   ├── routers/             # analysis, search, docs endpoints
│   │   └── services/            # embedder.py, aws_client.py
│   └── lambda/                  # Lambda orchestrator
│       ├── handler.py           # SQS event handler
│       ├── orchestrator.py      # 3-pass pipeline
│       ├── prompts.py           # prompt templates
│       └── rate_limiter.py      # token budget + backoff
└── frontend/                    # React + TypeScript + Vite
    └── src/
        ├── pages/               # AnalysisPage, SearchPage, ArchitecturePage, HistoryPage
        └── api/client.ts        # typed API client
```

---

## Key design decisions

**Why Lambda for the orchestrator?** Analysis jobs are long-running (3–10 minutes), memory-intensive (tree-sitter + embedding batches), and sporadic. Lambda's pay-per-invocation model fits perfectly — no idle cost between analyses. The 15-minute timeout covers all but the largest repositories.

**Why a Docker image for Lambda?** tree-sitter's Python bindings include compiled C extensions that vary by platform. A Docker image built on the Lambda Amazon Linux base guarantees the right binaries, unlike Lambda Layers which can have subtle compatibility issues.

**Why three passes instead of one?** A single pass asking "document this entire codebase" produces generic summaries because the model can't hold the full context. The three-pass structure is a deliberate context management strategy: Pass 1 keeps each LLM call small and parallelisable; Pass 2 injects upstream summaries so the model understands dependencies before summarising a module; Pass 3 uses the graph structure (not just file contents) to generate an accurate architecture narrative.

**Why topological order for Pass 2?** Processing modules in dependency order (leaves first) means that when module A imports module B, B's summary is already available to inject into A's context. This produces more accurate summaries than processing files alphabetically or in arbitrary order.

**Why Voyage AI over OpenAI embeddings?** `voyage-code-3` is trained on code-specific data and understands the semantic relationship between a natural language question ("where is authentication handled?") and the code that implements it. Standard text embeddings treat code as prose, which degrades retrieval quality significantly for identifier-heavy code.
