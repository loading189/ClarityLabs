import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.core import router as core_router
from backend.app.api.routes.demo import router as demo_router
from backend.app.api.routes.sim import router as sim_router
from backend.app.api.routes.onboarding import router as onboarding_router
from backend.app.api.routes.integrations import router as integrations_router
from backend.app.api.routes.categorize import router as categorize_router
from backend.app.api.routes.coa import router as coa_router
from backend.app.seed.run import seed_system_categories
from backend.app.api.routes.admin import router as admin_router
from backend.app.api.routes.ledger import router as ledger_router, api_router as ledger_api_router
from backend.app.api.routes.brief import router as brief_router
from backend.app.api.routes.signals import router as signals_router
from backend.app.api.routes.health_score import router as health_score_router
from backend.app.api.routes.audit import router as audit_router
from backend.app.api.routes.diagnostics import router as diagnostics_router
from backend.app.api.routes.monitor import router as monitor_router
from backend.app.api.routes.changes import router as changes_router
from backend.app.api.routes.assistant_thread import router as assistant_thread_router
from backend.app.api.routes.sim_v2 import router as sim_v2_router
from backend.app.api.routes.businesses import router as businesses_router
from backend.app.api.routes.daily_brief import router as daily_brief_router
from backend.app.api.routes.assistant_plans import router as assistant_plans_router
from backend.app.api.routes.assistant_progress import router as assistant_progress_router
from backend.app.api.routes.assistant_work_queue import router as assistant_work_queue_router
from backend.app.api.routes.transactions import router as transactions_router
from backend.app.api.routes.integration_connections import router as integration_connections_router
from backend.app.api.routes.webhooks import router as webhooks_router
from backend.app.api.routes.assistant_tools import router as assistant_tools_router
from backend.app.api.routes.categorize_auto import router as categorize_auto_router
from backend.app.api.routes.plaid import router as plaid_router
from backend.app.api.routes.processing import router as processing_router
from backend.app.api.routes.actions import router as actions_router
from backend.app.api.routes.me import router as me_router


logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS")
    if raw is None:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    else:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        raise RuntimeError("CORS_ALLOW_ORIGINS must not be empty.")
    if not any(origin in origins for origin in ("http://localhost:5173", "http://127.0.0.1:5173")):
        logger.warning("CORS allowlist does not include local dev origins: %s", origins)
    return origins


app = FastAPI(title="Clarity Labs API", version="0.1.0")

# @app.on_event("startup")
# def _startup_seed():
#     db = SessionLocal()
#     try:
#         seed_system_categories(db)
#     finally:
#         db.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Real API
app.include_router(core_router)

# Demo API (frontend depends on these routes)
app.include_router(demo_router)


app.include_router(sim_router)
app.include_router(onboarding_router) # prefix="/onboarding"
app.include_router(integrations_router)
app.include_router(categorize_router)
app.include_router(coa_router)
app.include_router(admin_router)
app.include_router(ledger_router)
app.include_router(ledger_api_router)
app.include_router(brief_router)
app.include_router(signals_router)
app.include_router(health_score_router)
app.include_router(audit_router)
app.include_router(diagnostics_router)
app.include_router(diagnostics_router, prefix="/api")
app.include_router(monitor_router)
app.include_router(changes_router)

app.include_router(assistant_thread_router)
app.include_router(sim_v2_router)
app.include_router(businesses_router)
app.include_router(daily_brief_router)
app.include_router(assistant_plans_router)
app.include_router(assistant_progress_router)

app.include_router(assistant_work_queue_router)
app.include_router(transactions_router)
app.include_router(integration_connections_router)
app.include_router(webhooks_router)
app.include_router(assistant_tools_router)
app.include_router(actions_router)
app.include_router(categorize_auto_router)
app.include_router(plaid_router)
app.include_router(processing_router)
app.include_router(me_router)
