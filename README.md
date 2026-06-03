# CRM + Proactive Sales Agent

A multi-tenant CRM and a **proactive sales agent** that recommends the next best
action (NBA) for a deal, grounded in a **per-tenant knowledge graph** built from
the CRM data. Built for the take-home in `docs/` (read `docs/REQUIREMENTS.md`).

> Original task brief preserved in `docs/`. This README is my own writeup.

---

## What I built

- **FastAPI backend** (one service) with JWT auth, full CRUD over the data model,
  the agent endpoints, and a static UI served from the same app.
- **Postgres (SQLAlchemy ORM)** as the relational source of truth. Schema is
  created automatically on startup — no manual migration step.
- **FalkorDB knowledge graph**, one graph key per tenant (`crm:{company_id}`),
  built at signup from Postgres. Modeled for traversal, not as a SQL mirror
  (see `app/graph/SCHEMA.md`).
- **LangGraph ReAct agent** (Anthropic) with five **typed, graph-backed tools**.
  It reads the graph only — never Postgres — and must cite activity evidence.
- **Proactivity via two real triggers**: a background scheduler ("morning brief"
  that ranks open deals and runs the agent on the top N) and a reactive trigger
  (creating an activity re-evaluates that deal). Both write to a `recommendations`
  inbox; `GET /proactive/feed` only reads it. Per-tenant off switch.
- **Static UI**: signup/login → deal list → deal detail with timeline + add-activity
  → a right-hand **agent chat**: proactive recommendations arrive as assistant
  messages (ranked, with evidence), and the rep can ask **grounded follow-up
  questions** about a deal (quick-reply chips + free text). Proactive on/off toggle
  in the header.

## Architecture

```
Static UI (app/static) ──fetch──► FastAPI (app/main.py)
                                     │
        ┌────────────────────────────┼────────────────────────────┐
   SQLAlchemy/Postgres        FalkorDB (per-tenant key)       LangGraph agent
   source of truth + inbox    crm:{company_id} snapshot       (Anthropic, ReAct)
                                     ▲                              │
                                     └──── typed tools read graph ──┘
   Proactive scheduler (asyncio) + reactive-on-activity ──► recommendations inbox
```

## Where things live (code map)

| Concern | Path |
|---|---|
| App entry / route wiring / scheduler lifecycle | `app/main.py` |
| Config (env) | `app/config.py` |
| Auth (bcrypt + JWT) | `app/auth/security.py`, `app/auth/deps.py` |
| ORM models | `app/db/models.py` |
| Tenant seeder (fixtures → Postgres) | `app/seed/seeder.py` |
| CRUD + agent routes | `app/api/routes/*.py` |
| Graph build / queries / schema | `app/graph/build.py`, `queries.py`, `SCHEMA.md` |
| Agent loop / tools / prompts | `app/agent/graph_agent.py`, `tools.py`, `prompts.py` |
| Proactive triggers + ranking | `app/agent/proactive.py` |
| UI | `app/static/` |
| Tests | `tests/` |

## How the agent reasons

The recommendation quality signals are driven by the **activity stream**, because
the seed data has no usable deal size (all `0.00`) and no usable contact roles
(all `unknown`/`inferred`). So the agent weighs:

- **Silence** — days since last inbound (buyer→us) / outbound (us→buyer).
- **Stage age & progression** — funnel position via `Stage` nodes + `NEXT` edges.
- **Momentum / sentiment & concrete asks** — read from recent activity snippets.

It **stays silent** on closed deals (short-circuited before any LLM call) and on
healthy deals with no open thread. Every recommendation cites the activity ids /
subjects / timestamps it used, so the UI can link back.

---

## Run it (5-minute demo)

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, JWT_SECRET (openssl rand -hex 32),
# and the FalkorDB connection (see "FalkorDB" note below).

make up                # postgres + falkordb + app
# wait for health:
curl localhost:8000/health      # {"status":"ok",...}
```

Then open **http://localhost:8000/** → **Sign up** → you land on a seeded CRM
(10 deals, 305 activities). Click a deal → **Get recommendation**, or watch the
**Inbox** populate from the proactive scan. Toggle **Proactive** off to stop it.

API-only demo:

```bash
TOKEN=$(curl -s localhost:8000/auth/signup -H 'content-type: application/json' \
  -d '{"email":"demo@x.io","password":"secret123"}' | jq -r .access_token)

curl -s localhost:8000/deals -H "Authorization: Bearer $TOKEN" | jq '.items[].deal_name'
DEAL=$(curl -s localhost:8000/deals -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')
curl -s -X POST localhost:8000/deals/$DEAL/recommendation -H "Authorization: Bearer $TOKEN" | jq
curl -s localhost:8000/proactive/feed -H "Authorization: Bearer $TOKEN" | jq
```

Inspect the graph directly:

```bash
make falkor-cli
> GRAPH.QUERY crm:<company_id> "MATCH (d:Deal)-[:IN_STAGE]->(s:Stage) RETURN d.name, s.label"
```

Run the tests (needs the infra up):

```bash
docker compose exec app pytest tests -q
```

## Key endpoints

`POST /auth/signup|login`, `GET /auth/me`, `GET /health`,
CRUD: `/pipelines`, `/buyers`, `/contacts`, `/deals` (+ `/deals/{id}/activities`,
`/deals/{id}/contacts`), and the agent surface:
`POST /deals/{id}/recommendation`, `POST /deals/{id}/chat` (grounded follow-up
Q&A), `GET /proactive/feed`, `POST /proactive/{true|false}`, `POST /graph/rebuild`.
Full interactive docs at `/docs`.

---

## Decisions & trade-offs

- **Per-tenant graph key** (`crm:{company_id}`) over a shared+namespaced graph:
  isolation is structural — a query against tenant A's key physically cannot read
  tenant B — rather than a `WHERE company_id` we might forget.
- **Graph is a static snapshot** built at signup / `/graph/rebuild`. CRM writes do
  **not** sync to the graph (explicit v1 limitation). The reactive trigger fires on
  new activities, but the agent reasons over the snapshot, so a brand-new activity
  isn't reflected until a rebuild.
- **Ranking excludes deal size** (all zero in the data); it scores on
  silence × funnel progression. Documented in `app/agent/proactive.py`.
- **Schema via `create_all` on startup**, not Alembic — right call for a one-day
  build with a fixed model.
- **18 stage rows kept verbatim** in Postgres (identity in `pipeline_stage_id`,
  deals reference the duplicates); the graph dedupes to 9 `Stage` nodes ordered by
  a canonical funnel map.

### FalkorDB target (cold-start caveat)

The FalkorDB connection is **fully env-driven** (`FALKORDB_HOST/PORT/USERNAME/
PASSWORD`). As configured in `.env` it points at a **remote** instance, which means
the demo depends on that instance being reachable. To run fully self-contained on
any machine, blank `FALKORDB_HOST` (and username/password) in `.env` — the app
then uses the local `falkordb` service in `docker-compose.yml`. Per-tenant graph
keys keep multiple signups isolated on either target.

## What I cut

- Alembic migrations, refresh tokens, password reset (out of scope per brief).
- Embeddings/RAG over activity bodies — the graph + structured signals do the work.
- A polished UI / build pipeline — vanilla HTML+JS, functional over pretty.
- Outbound content generation — the deliverable is a *recommendation*.

## What I'd do next

- **Graph sync**: incremental updates on CRM writes (or event-sourced rebuild)
  so reactive recommendations see the new activity without a full rebuild.
- **Sentiment/topic nodes** + an "open ask" extractor to sharpen the NBA.
- **Eval harness** for recommendation quality on the three deal archetypes
  (healthy / silent / closed) and a fallback when the LLM errors or is unreachable.
- Scale: batch the scheduler, cache graph reads, move the agent to a worker queue.
