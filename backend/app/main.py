from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.core import router as core_router
from backend.app.api.demo import router as demo_router
from backend.app.api.sim import router as sim_router
from backend.app.api.onboarding import router as onboarding_router
from backend.app.api.integrations import router as integrations_router
from backend.app.api.categorize import router as categorize_router
from backend.app.api.coa import router as coa_router
from backend.app.seed.run import seed_system_categories
from backend.app.api.admin import router as admin_router
from backend.app.api.ledger import router as ledger_router





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

