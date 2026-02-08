# Advisor Workspace Pilot Auth & RBAC

This pilot uses lightweight, header-based auth so the team can demo multi-user advisor workflows without full OAuth/SOC2 auth.

## Dev / Pilot Auth

- **Header**: send `X-User-Email` with each request.
- **Auto-create**: the backend auto-creates a `users` row on first-seen email.
- **Missing header**: protected endpoints return **401**.

## Roles & Permissions

Roles are scoped to a business via `business_memberships` and applied by `require_membership`:

| Role    | Capabilities |
|---------|--------------|
| viewer  | Read-only access (ledger, signals, actions, assistant summary) |
| staff   | Resolve/snooze/assign actions |
| advisor | Resolve/snooze/assign actions; refresh actions |
| owner   | Same as advisor |

## Key Endpoints

- `GET /api/me` → current user + memberships
- `GET /api/businesses/mine` → businesses current user can access
- `POST /api/businesses` → create a business + owner membership
- `POST /api/businesses/{business_id}/join` → dev-only membership join (gated)
- `DELETE /api/businesses/{business_id}?confirm=true` → delete a business (owner + gated)
- `GET /api/actions/{business_id}/triage?status=open&assigned=me|unassigned|any`
- `POST /api/actions/{business_id}/{action_id}/assign`

## Frontend Dev Login

1. Open the app.
2. Enter an email in the **Dev Login** prompt.
3. The frontend stores this in `localStorage` and sends `X-User-Email` on every API request.

## Local Notes

- Create business memberships for new users as needed.
- Assignment and resolution changes are recorded in `action_state_events` for auditability.

## Pilot Onboarding (Create + Join + Delete)

### Create a business (owner membership)

```bash
curl -X POST http://localhost:8000/api/businesses \
  -H "Content-Type: application/json" \
  -H "X-User-Email: advisor@example.com" \
  -d '{ "name": "Acme Co" }'
```

### Join a business (dev/pilot only)

Set `PILOT_DEV_MODE=1` or `CLARITY_PILOT_MODE=1` before running:

```bash
curl -X POST http://localhost:8000/api/businesses/<business_id>/join \
  -H "Content-Type: application/json" \
  -H "X-User-Email: advisor@example.com" \
  -d '{ "role": "advisor" }'
```

### Delete a business (owner + gated)

Set `ALLOW_BUSINESS_DELETE=1` before running:

```bash
curl -X DELETE "http://localhost:8000/api/businesses/<business_id>?confirm=true" \
  -H "X-User-Email: owner@example.com"
```

### Config flags for frontend

`GET /api/config` returns:

```json
{
  "pilot_mode_enabled": true,
  "allow_business_delete": false
}
```
