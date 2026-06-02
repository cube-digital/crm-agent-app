# Requirements — proactive sales agent on a CRM graph

You have **one working day** to build a proactive agent that suggests the next best action for a sales deal, backed by a graph you build from a sample CRM dataset.

Read [SALES_BRIEF.md](SALES_BRIEF.md) first if you haven't.

## What you must deliver

A working system that does these six things:

### 1. Stand up your own storage

- The sample data lives in [`db/fixtures.json`](../db/fixtures.json). There is **no SQL schema and no seed file** — designing the storage layer is part of the test.
- Decide what you want: a Postgres schema you design and load from the JSON, SQLite, or skip a relational store and load straight into the graph. Justify the choice in your README.
- Whatever you pick must come up automatically when the stack starts. No "first run this script" steps.
- The `docker-compose.yml` ships with an empty Postgres service ready for you to use. Drop it if you don't want it.

### 2. Build a knowledge graph from the CRM

- Pick what becomes a **node** (Deal? Buyer? Contact? Activity? Stage? Topic? Stakeholder role?) and what becomes an **edge**, and *why*.
- Ingest the data from `db/fixtures.json` (or from your own DB if you loaded it there first) into FalkorDB.
- Make the build **re-runnable** — drop & rebuild the graph on demand without breaking the app.
- Document your graph schema in a short `app/graph/SCHEMA.md` (or inline doc) — node types, edge types, properties, and one Mermaid diagram.

A graph here isn't a checkbox. The reason we want it is that "what's going on with this deal" is a *relational* question — who talked to whom, about what, before what stage transition. SQL JOINs can do this, but a graph lets the agent traverse and reason much more naturally.

### 3. Build an agent + tools

- Build an agent loop (LangGraph / a hand-rolled ReAct loop / OpenAI tools / Anthropic tool-use / pydantic-ai — your call).
- Give it **at least two tools** backed by the graph (e.g. `get_deal_overview(deal_id)`, `get_recent_activities(deal_id, limit)`, `find_silent_threads(deal_id)`, `get_stakeholder_map(deal_id)`).
- Tools must be **typed** (clear input/output schemas) and must read from the graph, not bypass it back to raw storage. The relational store (if you built one) exists as the *source* for the ingest step.
- The agent's final output for a deal must include:
  - the **recommended next best action**,
  - a one-sentence **rationale**,
  - the **evidence** it used (which activities / nodes), preferably as ids you can click back to.

### 4. Make it proactive

This is the differentiator. "Proactive" means: the system surfaces recommendations **without the user pointing at a specific deal**. Pick one or more mechanisms:

- **Trigger on a signal** — e.g. a deal hasn't had inbound activity in N days, or a stage age threshold has been crossed.
- **Scan on a schedule** — e.g. a "morning brief" job that ranks the top 3 deals to act on today.
- **React to data change** — e.g. when a new activity arrives, re-evaluate the deal and push a notification if the recommendation flips.

You must:

- Implement at least one proactive mechanism end-to-end.
- Explain in your README why you chose it and how you would extend it.
- Have an obvious **off switch** — proactive agents that can't be quieted are unusable.

### 5. Expose an HTTP API

The agent has to be reachable. Build a small HTTP API (FastAPI / Flask / Starlette / your call) with at minimum these endpoints:

| Method | Path                              | Purpose                                                                 |
|-------:|-----------------------------------|-------------------------------------------------------------------------|
| `GET`  | `/health`                         | Liveness check. Returns 200 when the app, the graph, and the DB are up. |
| `GET`  | `/deals`                          | List the deals the agent can reason about (id, name, stage, owner, ...). |
| `GET`  | `/deals/{deal_id}`                | Return a structured overview of one deal (graph-backed).                |
| `POST` | `/deals/{deal_id}/recommendation` | Run the agent against this deal and return the NBA + rationale + evidence. |
| `GET`  | `/proactive/feed`                 | The proactive surface: ranked list of deals that need action *now*, each with its NBA and rationale. |
| `POST` | `/proactive/{enabled}`            | Toggle the proactive mechanism on/off (`true` or `false`). The off switch. |
| `POST` | `/graph/rebuild`                  | Drop & rebuild the FalkorDB graph from the source data. Idempotent.     |

Notes:
- Responses must be JSON. Document the response shapes in your README (a tiny sample is enough).
- The exact path names are not sacred — if you name something differently, document it.
- You may add more endpoints. These are the minimum.

### 6. Ship it with Docker

- Everything runs with `docker compose up`. No manual setup steps after `cp .env.example .env`.
- **You write the Dockerfile** for your app. The `app` service in `docker-compose.yml` is a stub for you to extend (or replace).
- Logs must show what the agent did: which tools it called, what it returned, the final recommendation.

## What we'll spend the most time looking at

In order of weight (see [EVAL.md](EVAL.md) for the full breakdown):

1. **The agent + its proactivity.** How does it decide what to surface? How does it explain *why* now? Is it grounded in real evidence or hallucinated?
2. **The graph design.** Did you pick node/edge types that *help reasoning*, or did you just mirror the JSON 1:1? (The latter is a wasted graph.)
3. **Code structure & repo hygiene.** Can a teammate find anything in 30 seconds? Are tools and the agent decoupled? Are prompts versioned somewhere readable?
4. **API ergonomics.** Are the endpoints obvious, JSON well-shaped, errors meaningful?
5. **Docker / repeatability.** Does it actually run for us cold?

## What is explicitly out of scope

You will lose time if you build any of these:

- Auth, multi-tenancy, RBAC, user management.
- A web UI. JSON over HTTP is enough — we will hit it with curl / httpie / Postman.
- Real CRM integration. The sample fixtures are the world.
- Generating outbound emails / content. The deliverable is a *recommendation*.
- Vector search + RAG over activity bodies. You *can* do it if you want — but the graph + structured signals should do most of the work. Don't reach for embeddings just because they're familiar.
- Production-grade observability. A `logging.info(...)` line per tool call is fine.
- Tests for every function. One or two tests on the recommendation logic is plenty.

## What we expect of your code

- One language end-to-end (Python is the easy path — `app/requirements.txt` is already wired up).
- LLM access via your provider of choice. `.env.example` has slots for `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. You decide.
- A short README of your own (or update this one) explaining: *what I built, what I cut, what I'd do next, how to demo it in 5 minutes*.

Good luck.
