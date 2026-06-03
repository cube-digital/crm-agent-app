"""FastAPI entry point: schema bootstrap, route wiring, static UI, and the
proactive scheduler lifecycle.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent.proactive import scheduler_loop
from app.api.routes import auth, buyers, contacts, deals, graph, health, pipelines, proactive
from app.db.session import init_schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("crm")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Initialising database schema")
    init_schema()
    stop = asyncio.Event()
    task = asyncio.create_task(scheduler_loop(stop))
    try:
        yield
    finally:
        stop.set()
        task.cancel()


app = FastAPI(title="CRM + Proactive Sales Agent", version="1.0.0", lifespan=lifespan)

for _r in (health, auth, pipelines, buyers, contacts, deals, proactive, graph):
    app.include_router(_r.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
