# Evaluation — how we'll grade your work

We grade on five axes. The headline weight is in parentheses. Use it to decide where to invest your day.

## 1. Agent quality & proactivity (35%)

The most important thing. Specifically:

- Is the recommendation **grounded in real evidence** from the timeline, or is it a generic LLM answer that ignores the data?
- Does the agent **cite the activities** (ids, subjects, timestamps) that justify the recommendation?
- Is there a real **proactive trigger** (signal-based, scheduled, or change-driven) — not just an HTTP endpoint that does work on request?
- Does it **prioritise across deals** rather than treating each one in isolation?
- Does it **say nothing when there's nothing to say** for a given deal?
- Is the **off switch** obvious?

We will deliberately throw it at:
- A healthy deal mid-flight (should produce a useful next step, not a panic alert).
- A deal that's gone silent for weeks (should detect the silence and explain it).
- A deal in `Closed Won` / `Closed Lost` (should *not* suggest anything — these are done).

## 2. Graph design (25%)

We will inspect your FalkorDB graph directly via `redis-cli`. What we look for:

- Did you pick **node types that are meaningful for reasoning** (e.g. `Deal`, `Buyer`, `Contact`, `Activity`, `Stage`, `Topic`, `StakeholderRole`) rather than mirroring the SQL tables 1:1?
- Are **edges typed and directional** in a way that lets the agent traverse naturally (e.g. `(:Contact)-[:WORKS_AT]->(:Buyer)`, `(:Activity)-[:TOUCHES]->(:Deal)`, `(:Deal)-[:IN_STAGE]->(:Stage)`)?
- Are properties on nodes / edges **chosen for query patterns** the agent will run? (Don't dump every column.)
- Is there a **short schema doc** with a diagram and the rationale?
- Is the build **re-runnable** (drop & rebuild the graph cleanly)?

A graph that's just a one-to-one copy of the relational schema is a red flag — it means you didn't think about what the graph *gives* you.

## 3. Code & repo structure (20%)

- Can a teammate find the agent, the tools, the prompts, the graph ingest, and the proactive trigger in **under 30 seconds**?
- Are **tools decoupled from the agent loop** (so you could swap the loop without rewriting tools)?
- Are **prompts in their own file** (not buried as f-strings in the agent loop)?
- Are tool **inputs/outputs typed** (pydantic / dataclasses / TypedDict — pick one)?
- Is there a **short README of your own** explaining what you built, what you cut, and what you'd do next?

## 4. API & Docker / repeatability (10%)

- Does `make up` work on a fresh clone after `cp .env.example .env`?
- Did you write a sensible Dockerfile and wire your app service into compose?
- Does the graph get built automatically on first boot — or is there a single obvious command to build it?
- Do the **HTTP endpoints from REQUIREMENTS §5** exist and behave (correct shapes, correct status codes, off switch works)?
- Does the demo path (1 HTTP request) work end-to-end without manual setup?

## 5. Communication (10%)

- The **demo walkthrough** at the end of the day.
- How you explain the **trade-offs** you made: what you cut, what you faked, what you'd build differently with another day.
- How you handle the **harder questions** ("why a graph here?", "how would you scale this to 10k deals?", "what happens when the LLM gets it wrong?").

We care less about whether you finished everything and more about whether you can defend what you shipped.

## Things we explicitly do not grade

- Number of features. Three solid features beats ten half-built ones.
- Test coverage. One or two tests on the recommendation logic is enough.
- Pretty output. CLI text is fine.
- Performance. As long as it returns within ~30s for a deal, we don't care.
- Choice of LLM, framework, or agent library. Pick what you know.

## What gets you a "no hire"

- The agent ignores the graph and pulls answers directly from Postgres.
- Recommendations that don't cite evidence.
- "Proactive" means "you have to call this endpoint."
- Can't get the stack running on our machine.
- Can't explain *why* you chose the graph schema you chose.
