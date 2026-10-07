# cloudag: Declarative JSON DAG Workflow Engine

A production-grade Python orchestration engine that executes complex workflows defined declaratively in JSON. Designed for hybrid pipelines combining deterministic data tasks (HTTP, API, scrapers) alongside non-deterministic LLM agent steps.

---

## Key Features

- **Non-Cyclical DAG Dependency Graphs:** Native topological sorting with parallel branching (fan-out) and join barriers (fan-in).
- **Deep Dynamic Variable Interpolation:** Recursive resolution supporting `${workflow.input.param}`, `${step_id.output.path.to.key}`, list indexing `${summarizer.output.items.0.title}`, and strict type preservation.
- **Checkpointing, Caching, and Resumption:** SHA-256 step hashing of `(action, resolved_inputs)`. Instant (< 50ms) warm cache reuse. Resumes failed runs by skipping completed checkpoints.
- **Hybrid Executors:**
  - `HTTPExecutor`: Async HTTP/Webhook/Lambda dispatch via `httpx`.
  - `PythonFnExecutor`: Sandboxed local Python worker with function registry and dynamic imports.
  - `LLMAgentExecutor`: Structured JSON output synthesis and LLM provider integration.
  - `DataTransformExecutor`: Deterministic projection, mapping, and filtering.
- **FastAPI REST API:** Full lifecycle management including registration, execution, polling, resumption, and external webhook callback ingestion.
- **Async Persistence:** SQLAlchemy 2.0 with async SQLite or PostgreSQL.

---

## Project Structure

```
cloudag/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── README.md
├── cloudag/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schema.py          # Pydantic v2 schemas for workflow & step definitions
│   │   └── state.py           # DB models for WorkflowRun, StepRun, ExecutionState
│   ├── core/
│   │   ├── __init__.py
│   │   ├── graph.py           # DAG validator, cycle detector, topological sorter
│   │   ├── interpolator.py    # Recursive variable resolver (${step.output.key})
│   │   └── engine.py          # Async graph traversal orchestrator & fan-in barrier
│   ├── executors/
│   │   ├── __init__.py
│   │   ├── base.py            # Abstract BaseExecutor & ExecutionContext
│   │   ├── http.py            # HTTP/Webhook/Lambda executor (httpx)
│   │   ├── python_fn.py       # Sandboxed local Python worker
│   │   ├── llm_agent.py       # LLM executor with structured JSON output support
│   │   └── data_transform.py  # Deterministic JSON transforms & mappings
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py        # SQLAlchemy 2.0 async engine & sessionmaker
│   │   └── repository.py      # Checkpoint persistence, state transitions, step caching
│   └── api/
│       ├── __init__.py
│       └── server.py          # FastAPI application for workflows, runs, and webhooks
├── nexusflow/                 # Compatibility alias package for cloudag
└── tests/
    ├── test_graph.py          # Cycle detection and topological ordering tests
    ├── test_interpolator.py   # Variable resolution and nested path tests
    ├── test_engine.py         # End-to-end fan-out / fan-in DAG execution tests
    ├── test_cache.py          # Step caching and run resumption tests
    └── test_api.py            # FastAPI REST lifecycle and webhook callback tests
```

---

## Quickstart

### 1. Installation

```bash
pip install -e .
```

### 2. Running Tests

```bash
pytest -v
```

All 25 tests pass in ~1.8 seconds, verifying DAG cycles, variable interpolation, concurrency fan-out/fan-in barriers, cache reuse < 50ms, and API endpoints.

### 3. Starting the API Server

```bash
uvicorn cloudag.api.server:app --host 0.0.0.0 --port 8000
```

Access Swagger UI documentation at `http://localhost:8000/docs`.

---

## Declarative Workflow Specification

```json
{
  "workflow_id": "hybrid_market_insights",
  "version": "1.0.0",
  "trigger": { "type": "manual" },
  "steps": [
    {
      "id": "step_1",
      "type": "HTTP_DISPATCH",
      "action": "GET https://api.trends.ai/search",
      "inputs": {
        "topic": "${workflow.input.topic}"
      },
      "cache_executed_step": true
    },
    {
      "id": "step_2",
      "type": "PYTHON_WORKER",
      "action": "scrape_news_worker",
      "inputs": {
        "topic": "${workflow.input.topic}"
      },
      "cache_executed_step": true
    },
    {
      "id": "step_3",
      "type": "LLM_AGENT",
      "action": "gpt-4o",
      "depends_on": ["step_1", "step_2"],
      "inputs": {
        "prompt": "Synthesize trends for ${workflow.input.topic}. Trends: ${step_1.output.trends.0}, Volume: ${step_1.output.volume}. Top headline: ${step_2.output.headlines.0}.",
        "temperature": 0.5
      },
      "cache_executed_step": true
    }
  ]
}
```

---

## Deployment with Coolify or Docker

### Option 1: Coolify (Web UI)

1. Open your Coolify dashboard (e.g. at `http://<your-server-ip>:8000`).
2. Click **Create New Resource** -> **Application** -> **Public/Private Git Repository** or **Docker Compose**.
3. Point to this repository. Coolify will automatically detect the [Dockerfile](file:///home/nam/Documents/git-repos/active/cloudag/Dockerfile) and [docker-compose.yml](file:///home/nam/Documents/git-repos/active/cloudag/docker-compose.yml).
4. Set container port to `8080` (or leave default).
5. Click **Deploy**. Your API will be live with automatic HTTPS and health checking!

### Option 2: Docker Compose (Local / VPS)

```bash
docker compose up -d --build
```
