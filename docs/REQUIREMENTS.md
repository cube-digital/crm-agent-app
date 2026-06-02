# Requirements — CRM platform + proactive sales agent

You have **one to two working days** to build:

1. a small **CRM platform** — multi-tenant, authenticated, CRUD over the sample data model — and
2. a **proactive sales agent** that recommends the next best action for a deal, backed by a knowledge graph built from your CRM.

Read [SALES_BRIEF.md](SALES_BRIEF.md) first if you haven't, and [DATA_MODEL.md](DATA_MODEL.md) for the shape of the seed data.

## What you must deliver

A working system that does these seven things.

### 1. Build the CRM platform

The sample data in [`db/fixtures.json`](../db/fixtures.json) is a *seed*, not the world. Your job is to stand up a working CRM that hosts it.

- **Design the Postgres schema yourself.** The shape is documented in [DATA_MODEL.md](DATA_MODEL.md). Every entity table must carry `company_id` for tenant scoping (see §2). There is no SQL file in this repo on purpose.
- **Make the schema come up automatically** when the stack starts. No "first run this script" steps. Use migrations, an init script, or whatever fits — document it.
- **Full CRUD coverage of the data model.** Match the entities in [DATA_MODEL.md](DATA_MODEL.md) — nothing missing, nothing extra. Minimum required behaviour per entity:

  | Entity            | List | Read | Create | Update                                | Delete | Notes                                                                                       |
  |-------------------|:----:|:----:|:------:|:-------------------------------------:|:------:|---------------------------------------------------------------------------------------------|
  | `pipelines`       |  ✔   |  ✔   |   —    |                   —                   |   —    | Read-only. Seeded once per tenant (the "Sales Pipeline" from fixtures). No admin UI needed. |
  | `pipeline_stages` |  ✔   |  ✔   |   —    |                   —                   |   —    | Read-only. Seeded with the pipeline. Used in dropdowns when moving a deal.                  |
  | `buyers`          |  ✔   |  ✔   |   ✔    |          name / description / urls / industry          |   —    | Buyer = account / prospect company.                                                          |
  | `contacts`        |  ✔   |  ✔   |   ✔    |       name / email / phone / position / buyer_id       |   —    | Orphan contacts (`buyer_id = null`) are allowed — see [DATA_MODEL.md](DATA_MODEL.md) gotchas. |
  | `deals`           |  ✔   |  ✔   |   ✔    | stage / owner / amount / close_date / is_closed[_won]  |   —    | Stage change is the headline update — wire it in the UI.                                     |
  | `deal_contacts`   |  ✔   |  ✔   |   ✔    |                 `role` only                  |   ✔    | Link/unlink a contact to a deal; set role (champion / decision_maker / blocker / unknown).   |
  | `activities`      |  ✔   |  ✔   |   ✔    |                   —                   |   —    | Create-only after seed. Each activity is immutable in the timeline.                          |
  | `activity_links`  |  —   |  —   |  auto  |                   —                   |   —    | Created automatically by the server when an activity is created — don't expose directly.    |

  - The **core write path** is creating an activity on a deal: `POST /deals/{deal_id}/activities` accepts `activity_type`, `subject`, `full_text`, `direction`, `timestamp` (default `now()`); the server creates the `activities` row, the `activity_links` row tying it to the deal, and any implicit `activity_links` to buyer/contact if you choose to model those. Document the shape you pick.
  - Pagination is required on the high-cardinality lists (`activities`, `deals/{id}/activities`). Cursor or offset is fine.
  - Stage changes must validate the target stage belongs to the tenant's pipeline.
- **Writes do *not* propagate to the graph.** The graph is a static per-tenant snapshot built at seed time (see §3). Document this limitation in your README.
- **Minimal UI.** Pick a framework you can ship in a day — Next.js, React + Vite, HTMX + Jinja, Streamlit, plain HTML, your call. Justify in the README. Functional beats pretty.
  - At minimum: a login/signup screen, a deal list, a deal detail page with the activity timeline, an "add activity" form, and an **inbox panel** that surfaces the agent's recommendations (see §5).
  - No design-system requirements. Don't burn time on CSS.

### 2. Authentication & multi-tenancy

Every CRM has a login screen. Yours does too.

| Method | Path             | Auth   | Purpose                                                                |
|-------:|------------------|--------|------------------------------------------------------------------------|
| `POST` | `/auth/signup`   | none   | Create a Company + User, seed the new tenant with the sample fixtures, return a JWT. |
| `POST` | `/auth/login`    | none   | Verify email + password, return a JWT.                                 |
| `GET`  | `/auth/me`       | bearer | Return the authenticated user + company.                               |

Rules:

- **JWT, Bearer token, `Authorization` header.** Encode `user_id`, `company_id`, and a short `exp` claim (≤ 60 min is fine).
- **Sign the JWT with a secret from `JWT_SECRET` env var.** Don't commit a default secret to git.
- **Hash passwords with bcrypt or argon2.** No plaintext, no MD5, no sha256-without-salt.
- **Every data route must scope by `company_id`** read off the JWT. No cross-tenant reads or writes, ever. This applies to the graph queries too (see §3 and §4).
- **Failure shapes:** `401` when the token is missing / expired / invalid, `403` when authenticated but touching another tenant's row, `404` only when the row genuinely does not exist within that tenant.
- **On signup, seed the new tenant with the full sample dataset.** Copy *every* collection in `db/fixtures.json` into the new company's Postgres rows:
  - `pipelines` (1) and `pipeline_stages` (the 9 distinct labels — de-dupe the 18 rows by `(label, display_order)` if you want, or keep all 18 verbatim; document the choice)
  - `buyers` (10), `contacts` (11)
  - `deals` (10), `deal_contacts` (11)
  - `activities` (305), `activity_links` (305)

  Re-namespace **every entity ID** to fresh UUIDs and rewrite **every `company_id`** (and every foreign key — `buyer_id`, `pipeline_id`, `pipeline_stage_id`, `deal_id`, `contact_id`, `activity_id`, `entity_id` on `activity_links`) so the new tenant gets its own isolated copy. Then build that tenant's graph (§3) over the freshly-seeded data.

Out of scope (don't burn time):

- OAuth / SSO / SAML / magic links.
- Password reset, email verification, 2FA.
- Refresh tokens. Short-lived JWT is enough for the demo.
- Per-deal ACL beyond company-level scoping (no "rep only sees own deals" rule).
- Rate limiting, CSRF, account lockout, audit logs.

### 3. Build a knowledge graph from the CRM

- Pick what becomes a **node** (Deal? Buyer? Contact? Activity? Stage? Topic? StakeholderRole?) and what becomes an **edge**, and *why*.
- The graph is **per tenant**. Either use one FalkorDB graph key per company (e.g. `crm:{company_id}`) or share one graph and namespace every node with a `company_id` property that every query MUST filter on. Pick one and document why.
- The graph is **a static snapshot** of the tenant's Postgres data, built when the tenant is seeded. CRM writes that happen after seeding do **not** propagate to the graph. The student does not have to build a sync mechanism — this is an explicit v1 limitation, called out in the README.
- Make the build **re-runnable** — `/graph/rebuild` drops and rebuilds the *current tenant's* graph from Postgres without touching any other tenant's graph.
- Document the graph schema in a short `app/graph/SCHEMA.md` — node types, edge types, properties, one Mermaid diagram, and a sentence on *why a graph at all*.

A graph here isn't a checkbox. The reason we want it is that "what's going on with this deal" is a *relational* question — who talked to whom, about what, before what stage transition. SQL JOINs can do this, but a graph lets the agent traverse and reason much more naturally.

### 4. Build an agent + tools

- Build an agent loop (LangGraph / a hand-rolled ReAct loop / OpenAI tools / Anthropic tool-use / pydantic-ai — your call).
- Give it **at least two tools** backed by the graph (e.g. `get_deal_overview(deal_id)`, `get_recent_activities(deal_id, limit)`, `find_silent_threads(deal_id)`, `get_stakeholder_map(deal_id)`).
- Tools must be **typed** (clear input/output schemas) and must read from the **graph**, not bypass it back to raw Postgres.
- **Every tool query MUST be scoped by `company_id`** from the JWT — the agent must not be able to see another tenant's subgraph, even by mistake.
- The agent's final output for a deal must include:
  - the **recommended next best action**,
  - a one-sentence **rationale**,
  - the **evidence** it used (activity ids, subjects, timestamps), so the CRM UI can link back to its own rows.

### 5. Make it proactive

"Proactive" means the system surfaces recommendations **without the user pointing at a specific deal**. Pick one or more mechanisms:

- **Signal trigger** — a deal hasn't had inbound activity in N days, or a stage-age threshold was crossed.
- **Scheduled scan** — a "morning brief" job that ranks the top 3 deals to act on today.
- **Reactive** — when a new activity is created via the CRM, re-evaluate that deal and push the result to the inbox.

You must:

- Implement at least one mechanism end-to-end, **per tenant** (the trigger runs in the context of the tenant whose data is being scanned).
- Surface the recommendations in the UI inbox panel.
- Provide an obvious **off switch** — `POST /proactive/{enabled}` plus a UI toggle. Per tenant.

### 6. Expose an HTTP API

At minimum:

| Method | Path                              | Auth   | Purpose                                                              |
|-------:|-----------------------------------|--------|----------------------------------------------------------------------|
| `POST` | `/auth/signup`                    | none   | Create Company + User, seed sample data, return JWT.                  |
| `POST` | `/auth/login`                     | none   | Return JWT.                                                          |
| `GET`  | `/auth/me`                        | bearer | Current user + company.                                              |
| `GET`  | `/health`                         | none   | Liveness — 200 when app + graph + DB are up.                          |
| `GET`  | `/pipelines`                      | bearer | List pipelines for the tenant.                                       |
| `GET`  | `/pipelines/{id}/stages`          | bearer | List stages for a pipeline (used in the deal-stage dropdown).         |
| `GET`  | `/buyers`                         | bearer | List buyers (accounts).                                              |
| `GET`  | `/buyers/{id}`                    | bearer | Read one buyer.                                                      |
| `POST` | `/buyers`                         | bearer | Create a buyer.                                                      |
| `PATCH`| `/buyers/{id}`                    | bearer | Update buyer fields.                                                 |
| `GET`  | `/contacts`                       | bearer | List contacts (filterable by `buyer_id`).                            |
| `GET`  | `/contacts/{id}`                  | bearer | Read one contact.                                                    |
| `POST` | `/contacts`                       | bearer | Create a contact.                                                    |
| `PATCH`| `/contacts/{id}`                  | bearer | Update contact fields (incl. reassigning `buyer_id`).                |
| `GET`  | `/deals`                          | bearer | List deals for the authed tenant.                                    |
| `GET`  | `/deals/{id}`                     | bearer | Deal overview.                                                       |
| `POST` | `/deals`                          | bearer | Create a deal.                                                       |
| `PATCH`| `/deals/{id}`                     | bearer | Update deal (stage move, owner, close).                              |
| `GET`  | `/deals/{id}/activities`          | bearer | Paginated activity timeline for a deal.                              |
| `POST` | `/deals/{id}/activities`          | bearer | Create an activity on a deal (Postgres only — graph stays static).    |
| `GET`  | `/deals/{id}/contacts`            | bearer | List the deal_contacts rows for a deal (contacts + role).             |
| `POST` | `/deals/{id}/contacts`            | bearer | Link a contact to a deal with a role.                                |
| `PATCH`| `/deals/{id}/contacts/{cid}`      | bearer | Update the role on a deal_contact.                                   |
|`DELETE`| `/deals/{id}/contacts/{cid}`      | bearer | Unlink a contact from a deal.                                        |
| `POST` | `/deals/{id}/recommendation`      | bearer | Run the agent against this deal — NBA + rationale + evidence.         |
| `GET`  | `/proactive/feed`                 | bearer | Ranked list of deals needing action now, each with NBA + rationale.   |
| `POST` | `/proactive/{enabled}`            | bearer | Toggle proactive on/off for the tenant. The off switch.               |
| `POST` | `/graph/rebuild`                  | bearer | Drop & rebuild the *current tenant's* graph. Idempotent.              |

Notes:

- Responses JSON. Document the shapes in your README (a tiny sample is enough).
- Path names are not sacred — if you name something differently, document it.
- You may add more endpoints. These are the minimum.
- Cross-tenant access on any bearer route returns `403`, not `404`.

### 7. Ship it with Docker

- Everything runs with `docker compose up`. No manual setup after `cp .env.example .env`.
- **You write the Dockerfile(s)** for your backend. If the frontend is a separate service, write its Dockerfile too and wire it into `docker-compose.yml`.
- Logs must show what the agent did: which tools it called, what it returned, the final recommendation.
- Demo path: `docker compose up` → open the UI → sign up → land on a seeded inbox showing recommendations within ~30s.

## What we'll spend the most time looking at

In order of weight (see [EVAL.md](EVAL.md) for the full breakdown):

1. **CRM correctness + tenant isolation.** JWT validated on every bearer route, queries scoped by `company_id`, no cross-tenant leakage in Postgres *or* the graph. We will try to read tenant A's deals with tenant B's token — you should return `403`.
2. **Agent + proactivity.** Grounded recommendations with evidence ids, a real proactive trigger (not just an HTTP endpoint), sensible off switch, prioritisation across deals, silence on `Closed Won` / `Closed Lost`.
3. **Graph design.** Meaningful node/edge types, not a 1:1 mirror of Postgres. Properties chosen for the agent's query patterns. Per-tenant isolation works.
4. **Code structure.** A teammate can find the auth middleware, the CRUD layer, the agent loop, the tools, the prompts, the graph ingest, and the proactive trigger in **under 30 seconds**.
5. **API & Docker / repeatability.** `make up` works cold. Demo path is one signup + one click.

## What is explicitly out of scope

You will lose time if you build any of these:

- OAuth / SSO / SAML / magic links.
- Password reset, email verification, 2FA, refresh tokens.
- Per-deal ACL beyond company-level scoping.
- Rate limiting, CSRF tokens, account lockout, audit logs.
- A polished UI / design system. JSON over HTTP plus a functional UI is enough.
- Vector search + RAG over activity bodies. The graph + structured signals should do most of the work. Don't reach for embeddings just because they're familiar.
- Generating outbound emails / content. The deliverable is a *recommendation*.
- Production-grade observability. `logging.info(...)` per tool call is fine.
- Tests for every function. One or two tests on the recommendation logic plus one test that proves tenant isolation is plenty.

## What we expect of your code

- One language end-to-end on the backend (Python is the easy path — `app/requirements.txt` is already wired up). Frontend can be a different language.
- LLM access via your provider of choice. `.env.example` has slots for `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. You decide.
- A short README of your own (or update this one) explaining: *what I built, what I cut, what I'd do next, how to demo it in 5 minutes* — including the signup → seeded inbox path.

Good luck.
