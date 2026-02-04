# Fluency + Redundancy Audit

## Domain Map

### Monitoring
- **Canonical routes**
  - `GET /monitor/status/{business_id}`
  - `POST /sim/pulse/{business_id}` (runtime alias for monitoring pulse)
- **Canonical service entry points**
  - `monitoring_service.get_monitor_status`
  - `monitoring_service.pulse`
- **Canonical models/tables**
  - `MonitorRuntime`
  - `HealthSignalState`
  - `RawEvent`, `TxnCategorization`, `Category`, `Account` (inputs for detector feed)
- **Redundant routes/services/files**
  - `/sim/pulse/{business_id}` duplicates monitoring pulse semantics, via `sim_service.pulse`.
  - Frontend monitoring widget (`frontend/src/features/monitoring/MonitoringWidget.tsx`) calls both `/monitor/status` and `/api/signals` to rehydrate state (two endpoints for one widget).
- **Recommended action**: **Wrap**
  - Keep `/sim/pulse` as a thin wrapper for simulator flows, but position `/monitor/status` and `/monitor/pulse` (if added later) as canonical.
  - Document `/api/signals` as the canonical state list used by Monitoring UI.

### Signals
- **Canonical routes**
  - `GET /api/signals` (signal state list)
  - `GET /api/signals/types`
  - `GET /api/signals/{business_id}/{signal_id}` (detail)
  - `POST /api/signals/{business_id}/{signal_id}/status` (status update)
  - Demo parallels: `POST /demo/health/{business_id}/signals/{signal_id}/status`
- **Canonical service entry points**
  - `signals_service.list_signal_states`
  - `signals_service.get_signal_state_detail`
  - `signals_service.update_signal_status` (delegates to `health_signal_service`)
  - `health_signal_service.update_signal_status` (canonical write path)
  - `signals.v2.run_v2_detectors` (monitoring signal detection)
- **Canonical models/tables**
  - `HealthSignalState`
- **Redundant routes/services/files**
  - `signals.core` + `signals_service.fetch_signals` provide v1 “analytics signals” that overlap with v2 monitoring signals.
  - Demo health endpoints (`/demo/health`, `/demo/health/{business_id}`) overlap with real health/signal semantics.
  - Frontend uses both `frontend/src/api/signals.ts` (real) and `frontend/src/api/demo.ts` (demo) for signal status updates depending on page.
- **Recommended action**: **Deprecate**
  - Deprecate v1 `signals.core` in favor of v2 detectors as the canonical signal generator.
  - Keep demo endpoints as wrappers that delegate to canonical services, and avoid new logic in demo routes.

### Audit
- **Canonical routes**
  - `GET /audit/{business_id}`
- **Canonical service entry points**
  - `audit_service.list_audit_events`
  - `audit_service.log_audit_event`
- **Canonical models/tables**
  - `AuditLog`
- **Redundant routes/services/files**
  - None observed.
- **Recommended action**: **Keep**

### Categorize
- **Canonical routes**
  - `/categorize/business/{business_id}/txns`
  - `/categorize/business/{business_id}/categories`
  - `/categorize/business/{business_id}/rules`
  - `/categorize/business/{business_id}/categorize` (single)
  - `/categorize/business/{business_id}/categorize/bulk_apply`
  - Brain vendor routes under `/categorize/business/{business_id}/brain/*`
- **Canonical service entry points**
  - `categorize_service` (categorization, rules, metrics)
  - `category_seed.seed_coa_and_categories_and_mappings` (setup)
- **Canonical models/tables**
  - `Category`, `CategoryRule`, `TxnCategorization`
  - `SystemCategory`, `BusinessCategoryMap`
- **Redundant routes/services/files**
  - `POST /brain/label` in core routes overlaps with categorize “brain vendor” endpoints.
  - Demo endpoints surface categorize metrics and drilldowns through `/demo` instead of canonical categorize routes.
- **Recommended action**: **Wrap**
  - Keep core `/brain/label` as a legacy shim but prefer `/categorize/.../brain/*` routes as canonical.
  - Keep demo routes as wrappers.

### COA
- **Canonical routes**
  - `/coa/business/{business_id}/accounts` (list, create)
  - `/coa/business/{business_id}/accounts/{account_id}` (update, deactivate)
  - `/onboarding/businesses/{business_id}/coa/apply_template` (template application)
- **Canonical service entry points**
  - Route module `backend/app/api/routes/coa.py` (no service layer)
  - `category_seed.seed_coa_and_categories_and_mappings` (for templates)
- **Canonical models/tables**
  - `Account`
  - `Category` (COA linkage)
- **Redundant routes/services/files**
  - Onboarding template application overlaps with future desire for a dedicated COA service.
- **Recommended action**: **Keep** (but consider adding a `coa_service` and consolidating template logic).

### Onboarding
- **Canonical routes**
  - `/onboarding/orgs`
  - `/onboarding/businesses/bootstrap`
  - `/onboarding/businesses/{business_id}/coa/apply_template`
  - `/onboarding/businesses/{business_id}/status`
- **Canonical service entry points**
  - `backend/app/api/routes/onboarding.py`
  - `category_seed.seed_coa_and_categories_and_mappings` (template setup)
- **Canonical models/tables**
  - `Organization`, `Business`, `BusinessIntegrationProfile`
- **Redundant routes/services/files**
  - None observed (demo only depends indirectly through dashboard health).
- **Recommended action**: **Keep**

### Demo
- **Canonical routes**
  - `/demo/health`
  - `/demo/health/{business_id}`
  - `/demo/dashboard` and `/demo/dashboard/{business_id}`
  - `/demo/drilldown/*`
  - `/demo/transactions/{business_id}`
  - `/demo/health/{business_id}/signals/{signal_id}/status`
- **Canonical service entry points**
  - `analytics_service` (monthly trends, dashboard payload)
  - `categorize_service` (metrics)
  - `health_signal_service` (signal status updates)
- **Canonical models/tables**
  - `HealthSignalState`, `AuditLog`
  - `RawEvent`, `TxnCategorization`, `Category`, `Account`
- **Redundant routes/services/files**
  - Demo routes largely overlap with real APIs (signals, categorize, transactions).
  - Frontend pages rely on demo endpoints for primary navigation (dashboard, health, transactions).
- **Recommended action**: **Wrap**
  - Keep demo endpoints as thin wrappers that delegate to canonical services.
  - Long-term: migrate frontend to canonical `/api` routes and mark `/demo` for deprecation.

## Dependency Diagram (monitor → signals → audit)

```
RawEvent/TxnCategorization
        │
        ▼
monitoring_service.pulse
        │
        ▼
signals.v2.run_v2_detectors
        │
        ▼
HealthSignalState upsert
        │
        ▼
audit_service.log_audit_event
```

## Canonical Architecture Proposal

- **Monitoring** is the sole orchestrator for v2 signal detection (`monitoring_service.pulse` → `signals.v2.run_v2_detectors`).
- **Signals** are stored as durable state in `HealthSignalState`; the canonical write path is `health_signal_service.update_signal_status`.
- **Audit** is a sidecar domain fed by signal detection and categorization workflows (`audit_service.log_audit_event`).
- **Demo** acts as a compatibility layer that delegates to the same services; it should never own new business logic.
- **Frontend** should progressively migrate to canonical `/api` routes (signals, categorize, monitoring) and limit `/demo` usage to demo-only data bootstrapping.
