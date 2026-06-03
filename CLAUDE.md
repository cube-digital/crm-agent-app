# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

One-day take-home interview: build a **proactive sales agent** backed by a **knowledge graph**. The scaffold (docker-compose, sample data, docs) is complete — the entire `app/` is a stub to be implemented.

Key docs (read in this order):
- `docs/SALES_BRIEF.md` — business context (what sales reps do, what "next best action" means)
- `docs/REQUIREMENTS.md` — 7 must-have requirements with endpoint spec
- `docs/DATA_MODEL.md` — entity schema + known data quirks
- `docs/EVAL.md` — grading rubric (agent 35%, graph 25%, code 20%, docker 10%, comms 10%)

## Commands

```bash
# Environment setup (first time)
cp .env.example .env   # then add OPENAI_API_KEY or ANTHROPIC_API_KEY

# Docker operations
make up               # start postgres + falkordb + app
make down             # stop everything
make logs             # follow app logs
make build            # rebuild app image
make reset            # stop + wipe all volumes

# Database shells
make psql             # psql on postgres
make falkor-cli       # redis-cli for FalkorDB (use GRAPH.QUERY commands)

# Python (for local dev without Docker)
pip install -r app/requirements.txt
docker compose up postgres falkordb   # start just the DBs
python -m app.main                    # run app locally
```

App runs on port 8000. No test framework is wired up yet — the requirements ask for only 1-2 tests covering tenant isolation and recommendation logic.

## Architecture

```
HTTP API (FastAPI/Flask)
     │
     ├── PostgreSQL 16  — relational source of truth (tenants, deals, activities, etc.)
     ├── FalkorDB       — graph database for agent queries (Redis-backed, Cypher queries)
     └── LLM API        — OpenAI or Anthropic (set via OPENAI_API_KEY / ANTHROPIC_API_KEY)
```

**Multi-tenancy:** JWT encodes `user_id` + `company_id`. Every query filters by `company_id`. Cross-tenant access returns 403.

**Signup flow:** `POST /auth/signup` → create Company + User → copy all entities from `db/fixtures.json` into Postgres with fresh UUIDs → build FalkorDB graph for that tenant → return JWT.

**Graph vs Postgres:** The FalkorDB graph is a **static snapshot** of Postgres. CRM writes go to Postgres only; the graph does not auto-sync. A `POST /graph/rebuild` endpoint drops and rebuilds the tenant's graph.

**Agent endpoint:** `POST /deals/{id}/recommendation` queries the **graph** (not Postgres directly) via typed tool functions that run parameterised Cypher queries. Returns next best action + rationale + evidence (activity IDs / timestamps).

**Proactive feed:** `GET /proactive/feed` — a signal- or schedule-driven mechanism that ranks deals across the tenant and surfaces the top N needing action. Must be a real trigger (not just an HTTP endpoint wrapper). Toggled by `POST /proactive/{enabled}`.

## Expected App Structure

```
app/
  main.py          # HTTP app entry point + route wiring
  api/
    routes/        # Request/response handlers
    models.py      # Pydantic models
  db.py            # Postgres helpers
  graph/
    build.py       # fixtures.json → FalkorDB ingest
    schema.py      # Node/edge type definitions
    queries.py     # Parameterised Cypher queries
  agent/
    agent.py       # Agent loop (ReAct / tool-use)
    tools.py       # Graph-backed tools (typed inputs/outputs)
    prompts.py     # System + planning prompts
    proactive.py   # Proactive triggers + deal ranking
```

## Sample Data (`db/fixtures.json`)

305 activities across 10 deals and 11 contacts. Known quirks the app must handle:
- `deal_amount` is mostly `"0.00"` or null
- `activities.direction` can be null (treat as "unknown")
- `contacts.buyer_id` can be null (orphaned contacts)
- 18 `pipeline_stages` for 1 pipeline — some are duplicates with different `display_order`
- `activities.full_text` can be empty, HTML, or very long

## Required Endpoints

**Auth (no bearer):** `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`

**CRUD (bearer, company-scoped):**
- `/pipelines`, `/pipelines/{id}/stages`
- `/buyers`, `/buyers/{id}`
- `/contacts`, `/contacts/{id}`
- `/deals`, `/deals/{id}`, `/deals/{id}/activities`, `/deals/{id}/contacts`

**Agent + Graph:**
- `POST /deals/{id}/recommendation` — run agent (must query graph, must cite evidence)
- `GET /proactive/feed` — ranked deals needing action
- `POST /proactive/{enabled}` — toggle proactive mechanism
- `POST /graph/rebuild` — drop + rebuild tenant graph
- `GET /health`

## Common Evaluation Pitfalls

- Agent **must** use graph queries, not direct Postgres reads
- Recommendations **must** cite evidence (activity IDs / timestamps)
- "Proactive" must be a real trigger (signal/schedule/change-driven), not just an endpoint
- `make up` must work cold on the evaluator's machine (write a Dockerfile)
- Graph design must be meaningful (not a 1:1 SQL mirror) — typed edges, properties chosen for query patterns
