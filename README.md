# crm-agent-app — practical interview

You have one day to build a **proactive sales agent** that suggests the *next best action* for a sales deal, using a **knowledge graph** built on top of a sample CRM dataset.

## What's in this repo

```
.
├── README.md               ← you are here
├── docs/
│   ├── REQUIREMENTS.md     ← the task — read this first
│   ├── SALES_BRIEF.md      ← sales context for non-sales engineers
│   ├── DATA_MODEL.md       ← the shape of the sample data
│   └── EVAL.md             ← how we will evaluate your work
├── db/
│   └── fixtures.json       ← the sample CRM data (10 deals, ~300 activities)
├── docker-compose.yml      ← postgres + falkordb skeleton; the app is yours to add
├── Makefile                ← convenience targets
├── .env.example            ← copy to .env and edit
└── app/                    ← (empty) your code goes here
    └── requirements.txt    ← starter Python deps — extend as needed
```

> You will notice there is **no SQL schema, no seed SQL file, and no Dockerfile**. That is on purpose. Designing the storage layer (or skipping it), modelling the graph, writing the Dockerfile, and exposing the API are part of the test.

## Read the docs in this order

1. **[docs/SALES_BRIEF.md](docs/SALES_BRIEF.md)** — what a sales deal is, what "next best action" means, what makes the agent useful.
2. **[docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)** — the task itself: what to build, what to deliver, what's out of scope.
3. **[docs/DATA_MODEL.md](docs/DATA_MODEL.md)** — the shape of `db/fixtures.json` (entities, relationships, gotchas).
4. **[docs/EVAL.md](docs/EVAL.md)** — what we grade.

## Quick start

```bash
cp .env.example .env
# (optional) set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env

# bring up the infra services
docker compose up -d postgres falkordb

# then add your own `app` service + Dockerfile and:
docker compose up -d --build app
```

The `app` service in `docker-compose.yml` is a *suggestion*. Change it to fit what you build. The Dockerfile is missing on purpose — you write it.

## What you should be doing

1. Read `db/fixtures.json`. Understand the entities and what's noisy.
2. Decide how you want to persist data — postgres (provided empty in compose), sqlite, or load straight into the graph. Justify your call in your README.
3. **Design and build the graph** in FalkorDB. Decide what's a node, what's an edge, what properties matter for reasoning about a deal.
4. **Build the agent** + the tools it can call. At minimum it queries the graph and reasons about a single deal's state.
5. **Make it proactive.** This is the core of the task — see `docs/REQUIREMENTS.md`.
6. **Expose an HTTP API** with the endpoints needed to demo the agent and the proactive feed (see REQUIREMENTS for the minimum set).
7. **Write the Dockerfile** for your service and wire it into `docker-compose.yml`.
8. Polish: repo layout, README of your own, what's missing, trade-offs.

You decide the framework, the LLM provider, the agent style. We care about the *reasoning*, not the brand of toolkit.

## Constraints

- **Everything runs in Docker** via `docker compose up`. No "works on my machine, run these 8 shell commands first."
- **Don't modify `db/fixtures.json`.** Treat it as a fixed export you'd never own. If you want derived data, build it yourself.
- **Time-box.** Don't try to build everything. Pick what you can do well in one day and explain the trade-offs.

Good luck.
