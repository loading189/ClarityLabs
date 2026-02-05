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
from backend.app.api.routes.ledger import router as ledger_router
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
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
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
app.include_router(brief_router)
app.include_router(signals_router)
app.include_router(health_score_router)
app.include_router(audit_router)
app.include_router(diagnostics_router)
app.include_router(monitor_router)
app.include_router(changes_router)

app.include_router(assistant_thread_router)
app.include_router(sim_v2_router)
app.include_router(businesses_router)
