"""Entrypoint for the agent service.

This file is intentionally a stub. Replace it with whatever shape fits your
implementation. The expected shape (per docs/REQUIREMENTS.md §5) is an HTTP
API. You can use FastAPI, Flask, Starlette — your call.

Suggested layout (not enforced):
    app/
        main.py          # HTTP app + route wiring
        api/             # request/response models, route handlers
        db.py            # whatever storage you picked (postgres helpers, etc.)
        graph/           # building & querying the FalkorDB graph
            build.py     # data → graph ingestion
            schema.py    # node/edge types
            queries.py   # parameterised Cypher used by tools
        agent/
            agent.py     # the agent loop
            tools.py     # tools the agent can call (graph-backed)
            prompts.py   # system / planning prompts
            proactive.py # the proactive loop / trigger / off-switch
"""
import os
import time


def main() -> None:
    print("crm-agent-app — stub. Replace app/main.py with your implementation.")
    print(f"  POSTGRES_URL  = {os.environ.get('POSTGRES_URL',  '(unset)')}")
    print(f"  FALKORDB_HOST = {os.environ.get('FALKORDB_HOST', '(unset)')}")
    # Keep the container alive so `docker compose up` succeeds and you can exec in.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
