from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.models import ActionItem, Business, HealthSignalState, MonitorRuntime, ProcessingEventState, RawEvent, TxnCategorization
from backend.app.scenarios.catalog import SCENARIO_CATALOG, list_specs
from backend.app.scenarios.models import ScenarioSpec, derive_seed_key, parse_anchor_date
from backend.app.services import ledger_service, monitoring_service, processing_service
from backend.app.services.actions_service import generate_actions_for_business
from backend.app.sim_v2.engine import reset as sim_v2_reset
from backend.app.sim_v2.engine import seed as sim_v2_seed
from backend.app.sim_v2.models import ScenarioInput, SimV2SeedRequest


SCENARIO_TO_SIM_INPUTS: dict[str, dict[str, object]] = {
    "baseline_stable": {"preset_id": "healthy"},
    "persistent_deterioration": {"preset_id": "revenue_decline"},
    "flickering_threshold": {
        "scenarios": [ScenarioInput(id="steady_state", intensity=1), ScenarioInput(id="timing_mismatch", intensity=1)],
    },
    "hygiene_missing_uncategorized": {"preset_id": "messy_books"},
    "plan_success_story": {"preset_id": "healthy"},
    "plan_failure_story": {"preset_id": "cash_strained"},
}


class ScenarioRunner:
    def list_scenarios(self) -> list[ScenarioSpec]:
        return list_specs()

    def seed_business(self, db: Session, business_id: str, scenario_id: str, params: dict | None = None) -> dict:
        business = db.get(Business, business_id)
        if not business:
            raise ValueError("business not found")
        if scenario_id not in SCENARIO_CATALOG:
            raise ValueError(f"unknown scenario_id: {scenario_id}")

        opts = dict(params or {})
        anchor_date: date | None = parse_anchor_date(opts)
        refresh_actions = bool(opts.get("refresh_actions", True))
        seed_key = derive_seed_key(business_id, scenario_id, opts)

        mapped = SCENARIO_TO_SIM_INPUTS[scenario_id]
        req = SimV2SeedRequest(
            business_id=business_id,
            preset_id=mapped.get("preset_id"),
            scenarios=mapped.get("scenarios"),
            anchor_date=anchor_date,
            mode="replace",
            seed=seed_key,
        )
        seed_result = sim_v2_seed(db, req)

        processing_service.process_new_events(db, business_id=business_id, limit=1000)
        monitoring_service.pulse(db, business_id, force_run=True)
        db.commit()

        actions_open_count = None
        if refresh_actions:
            generate_actions_for_business(db, business_id)
            db.commit()
            actions_open_count = int(
                db.execute(
                    select(func.count()).select_from(ActionItem).where(ActionItem.business_id == business_id, ActionItem.status == "open")
                ).scalar_one()
            )

        ledger_rows = len(ledger_service.ledger_lines(db, business_id, start_date=None, end_date=None, limit=5000))
        signals_open_count = int(
            db.execute(
                select(func.count()).select_from(HealthSignalState).where(HealthSignalState.business_id == business_id, HealthSignalState.status == "open")
            ).scalar_one()
        )

        return {
            "business_id": business_id,
            "scenario_id": scenario_id,
            "seed_key": seed_key,
            "summary": {
                "txns_created": int(seed_result["stats"]["raw_events_inserted"]),
                "ledger_rows": ledger_rows,
                "signals_open_count": signals_open_count,
                "actions_open_count": actions_open_count,
            },
        }

    def reset_business(self, db: Session, business_id: str) -> dict:
        business = db.get(Business, business_id)
        if not business:
            raise ValueError("business not found")

        sim_reset = sim_v2_reset(db, business_id)
        db.execute(delete(ProcessingEventState).where(ProcessingEventState.business_id == business_id))
        db.execute(delete(HealthSignalState).where(HealthSignalState.business_id == business_id))
        db.execute(delete(ActionItem).where(ActionItem.business_id == business_id))
        db.execute(delete(MonitorRuntime).where(MonitorRuntime.business_id == business_id))
        db.commit()

        remaining = int(
            db.execute(
                select(func.count()).select_from(RawEvent).where(RawEvent.business_id == business_id, RawEvent.source == "sim_v2")
            ).scalar_one()
        )
        cats_remaining = int(
            db.execute(
                select(func.count()).select_from(TxnCategorization).where(TxnCategorization.business_id == business_id)
            ).scalar_one()
        )
        return {
            "business_id": business_id,
            "deleted_raw_events": sim_reset["deleted_raw_events"],
            "remaining_sim_events": remaining,
            "remaining_categorizations": cats_remaining,
        }
