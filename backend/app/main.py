import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_market, routes_other
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import setup_logging
from app.providers.registry import get_registry

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
    setup_logging()
    s = get_settings()
    for p in get_registry().status():
        caps = {k: v for k, v in p["capabilities"].items() if v is True}
        log.info("provider %-14s configured=%-5s capabilities=%s", p["name"], p["configured"], list(caps))
    log.info("telegram configured=%s, ollama=%s (%s)", s.telegram_configured, s.ollama_base_url, s.ollama_model)
    log.info("No real order placement exists in this build. Paper trading only.")
    sched = None
    if s.scheduler_enabled:
        from app.services.scheduler import start_scheduler

        sched = start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(
    title="Personal AI Stock Market Assistant",
    version="0.1.0",
    lifespan=lifespan,
    description="Decision support for Indian equities. Educational signals, paper trading only.",
)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])
install_error_handlers(app)
app.include_router(routes_market.router)
app.include_router(routes_other.router)
