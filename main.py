import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import database
from config import (
    AGENT_HEALTH_INTERVAL,
    AGENT_HEALTH_TIMEOUT_SECONDS,
    AGENT_PKI_DIR,
    AGENT_TIMEOUT_SECONDS,
    AGENT_TLS_INSECURE_SKIP_VERIFY,
    DB_PATH,
)
from routers import api, views
from services.agents import AgentClient
from services.health import AgentHealthMonitor
from services import pki

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(title="vm-builder-dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(views.router)
app.include_router(api.router)


@app.on_event("startup")
async def on_startup():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    await database.init_db()
    pki_paths = pki.ensure(AGENT_PKI_DIR)
    app.state.agent_pki = pki_paths
    app.state.agent_client = AgentClient(
        ca_file=pki_paths["ca_cert"],
        cert_file=pki_paths["client_cert"],
        key_file=pki_paths["client_key"],
        insecure_skip_verify=AGENT_TLS_INSECURE_SKIP_VERIFY,
        timeout=AGENT_TIMEOUT_SECONDS,
    )
    app.state.health_monitor = AgentHealthMonitor(
        database,
        app.state.agent_client,
        interval_seconds=AGENT_HEALTH_INTERVAL,
        timeout_seconds=AGENT_HEALTH_TIMEOUT_SECONDS,
    )
    await app.state.health_monitor.start()


@app.on_event("shutdown")
async def on_shutdown():
    health_monitor = getattr(app.state, "health_monitor", None)
    if health_monitor:
        await health_monitor.stop()
