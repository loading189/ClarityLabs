# Action Layer Specification

## Purpose & Scope

The Action Layer is the canonical interface between financial signals, the assistant, and human decision-makers. This spec formalizes the taxonomy, evidence contracts, lifecycle, assistant rules, determinism, and forward-compatibility requirements so the layer remains **coherent, deterministic, and accountable** in production environments. It assumes the existing system (signals v2, ledger anchors, action_items table, assistant summary, APIs) and does **not** redesign architecture.

### Assumptions

- Ledger anchors and signal metadata already exist and are queryable.
- Actions are persisted with idempotency and can be refreshed/listed/resolved/snoozed.
- Auditability and explainability are product requirements.
- Humans are the final arbiters for actions that imply judgment.

### Non-goals

- UI changes or UI-driven action design.
- New external integrations.
- Automated execution of financial operations.

---

## 1) Action Taxonomy (Domain Model)

> **Principle:** The taxonomy is **small and opinionated**. Types express intent, not UI labels. Each type has explicit evidence and human judgment expectations.

### Action Types

| Action Type | Intent | Required Evidence | Expected Human Judgment | Typical Resolution Paths |
| --- | --- | --- | --- | --- |
| **Categorization Review** | Ensure transactions are classified correctly for reporting and cash-flow analysis. | Ledger anchors to the transaction(s); proposed category and confidence; prior categorization history. | Confirm, override, or create a rule. | Mark done with chosen category; ignore with reason (e.g., already handled); snooze if missing context. |
| **Spend Variance Investigation** | Confirm if a vendor/category variance is real, expected, or error. | Baseline window + current window deltas; ledger anchors to impacted transactions; signal explanation. | Validate variance, explain cause, or flag as anomaly. | Mark done with rationale; ignore if known seasonal; snooze until more data. |
| **Cash Timing Clarification** | Resolve timing gaps in cash ledger (e.g., large inflows/outflows with unclear timing or classification). | Ledger anchors to offsetting inflow/outflow; expected cadence; signal-derived timing delta. | Decide if timing is expected vs. risk. | Mark done with note; snooze until next period; ignore if already reconciled. |
| **Integration Health Follow-up** | Maintain data freshness and completeness. | Integration status, last sync time, error codes; impacted ledger range. | Decide to reconnect or defer. | Mark done after reconnect; snooze if awaiting credentials; ignore if legacy account. |
| **Signal Confirmation** | Validate an important financial signal before it is promoted or actioned. | Signal metadata, thresholds, baseline comparisons, and ledger anchors. | Confirm/deny signal relevance. | Mark done with confirmation; ignore if irrelevant to business; snooze if waiting for more data. |

### Extensibility Rules

- Add a new Action Type **only** if:
  - It has distinct evidence requirements; and
  - It triggers a different human decision from existing types; and
  - It is not merely a UI label.
- Maintain a registry with:
  - `type_id`, `intent`, `required_evidence_schema`, `optional_evidence_schema`, `resolution_schema`.

---

## 2) Evidence Contracts

> **Principle:** Every action must be **traceable to ledger anchors** and **auditable** via persisted evidence objects.

### Evidence Schema (Canonical)

```yaml
evidence:
  anchors:
    - ledger_entry_id
    - transaction_id
    - signal_id
  signal:
    type
    window:
      start
      end
    baseline:
      window
      stats
    deltas:
      amount
      percent
    explain:
      summary
      factors
  metadata:
    created_at
    derived_from_refresh_id
    evidence_version
```

### Evidence Requirements by Action Type

**Categorization Review**
- **Minimum required**
  - Transaction ledger anchors
  - Current and proposed category
  - Categorization confidence or rationale
- **Optional**
  - Historical categorizations for same vendor
  - Rule suggestions
- **Trustworthiness**
  - Must include evidence_version and derived_from_refresh_id for reproducibility

**Spend Variance Investigation**
- **Minimum required**
  - Baseline vs. current window stats (amounts + counts)
  - Ledger anchors for top contributing transactions
  - Signal explain factors with thresholds
- **Optional**
  - Vendor-level rollups
  - Seasonality hints
- **Trustworthiness**
  - Baseline window must be explicit and consistent across refreshes

**Cash Timing Clarification**
- **Minimum required**
  - Ledger anchors for inflow/outflow pairings
  - Expected cadence window
  - Observed timing delta
- **Optional**
  - Historical cadence chart or summary
- **Trustworthiness**
  - Timing delta must be computed from stable anchors, not UI filters

**Integration Health Follow-up**
- **Minimum required**
  - Connection status, last sync timestamp
  - Error/health codes
  - Impacted ledger span
- **Optional**
  - Retry history or error trend
- **Trustworthiness**
  - Health status must be derived from deterministic sync state, not heuristics

**Signal Confirmation**
- **Minimum required**
  - Signal metadata (type, thresholds, window)
  - Ledger anchors to impacted entries
  - Explain summary with driver factors
- **Optional**
  - Sensitivity analysis (what if thresholds change)
- **Trustworthiness**
  - Signal explanation must be reproducible from persisted inputs

---

## 3) Action Lifecycle & State Machine

> **Principle:** Actions should be stable, human-respectful, and resurfaced only when materially changed.

### States

- `open`
- `done`
- `ignored` (with reason)
- `snoozed` (with snooze_until)

### Allowed Transitions

```
open  -> done
open  -> ignored (reason required)
open  -> snoozed (snooze_until required)
snoozed -> open (after snooze_until or material change)
```

### Auto-resolution Rules

Actions **may auto-resolve** if:
- The underlying evidence is no longer valid (e.g., transaction removed from ledger).
- A deterministic condition is met (e.g., categorization rule applied and all anchored transactions updated).

Actions **must be human-resolved** if:
- They involve subjective or business-context decisions (variance significance, timing acceptability).
- They require explicit acknowledgment (auditor-facing decisions).

### Resurfacing Rules

Resurface an action only if:
- Evidence changes materially (delta crosses a defined threshold), or
- Snooze has expired **and** the evidence is still valid.

Avoid resurfacing if:
- The action is ignored with a stable reason (no material change).
- The action is done and evidence is unchanged.

---

## 4) Assistant Interaction Rules

> **Principle:** The assistant is an informed facilitator, not a nag.

### Creation Rules

The assistant may create actions only when:
- Evidence meets the minimum contract for that action type.
- There is a clear human decision to be made.
- The action is not a duplicate of an existing open/snoozed action (idempotent match).

### Re-surfacing Rules

The assistant may re-surface unresolved actions only if:
- The action is `open` with new material evidence; or
- The action was `snoozed` and snooze period expired with evidence still valid.

### When to Stop Asking

The assistant must stop asking when:
- An action is marked `ignored` with a stable reason.
- The user has explicitly declined multiple times without evidence changes.
- The action is `done` and evidence unchanged.

### Tone & Trust Constraints

- Always cite evidence when referencing an action.
- Prefer summaries with options rather than repeated prompts.
- Avoid “urgent” framing unless supported by deterministic thresholds.

---

## 5) Determinism & Idempotency Rules

> **Principle:** Repeated refreshes should never create noise.

### Idempotency Key Derivation

`idempotency_key = hash(action_type + business_id + anchor_set + signal_id + window + evidence_version)`

Where:
- `anchor_set` is a sorted, stable list of ledger/transaction IDs.
- `window` is the exact time window used for the signal or evidence.
- `evidence_version` ensures schema changes do not collide with old actions.

### Refresh Semantics

On each refresh:

1. **Match existing actions** by idempotency_key.
2. If match exists:
   - Update evidence if changed.
   - Reopen only if material change threshold exceeded and state allows.
3. If no match:
   - Create new action if evidence meets minimum contract.
4. If action no longer valid:
   - Auto-resolve or mark ignored with reason `evidence_invalid`.

### Material Change Thresholds

- Set thresholds per action type (e.g., % delta for variance).
- Thresholds must be explicit and versioned.
- Minor changes should update evidence **without** reopening.

---

## 6) Forward Compatibility

> **Principle:** Future features should extend the Action Layer without breaking trust.

### Multi-user / Advisor Workflows

- Add `owner_id` and `audience` fields to actions.
- Support role-scoped visibility: `business_owner`, `advisor`, `team_member`.
- Keep action evidence immutable; only resolution metadata is mutable.

### Permissions & Ownership

- Restrict state transitions based on role.
- Preserve audit log of transitions: `who`, `when`, `from_state`, `to_state`, `reason`.

### Automation Suggestions (Not Execution)

- Add `suggested_automation` as metadata.
- No auto-execution; require human acknowledgment to convert to action or rule.

### Future Agents

- Agents may **propose** actions but must meet evidence contracts.
- All agent-proposed actions must be labeled with `created_by_agent` and version.
- Trusted agent actions require the same idempotency rules.

---

## Tradeoffs & Rationale

- **Small taxonomy vs. flexibility:** A constrained set of action types prevents fragmentation and enforces evidence discipline.
- **Strict evidence contracts vs. speed:** The upfront cost of assembling evidence pays dividends in auditability and user trust.
- **Conservative resurfacing vs. recall:** Avoids nagging; may delay resurfacing borderline issues, but preserves user trust.

---

## Summary Checklist (Implementation-Agnostic)

- [ ] Each action has a valid Action Type from the taxonomy.
- [ ] Evidence meets the minimum required schema.
- [ ] Idempotency key derived deterministically.
- [ ] State transitions obey the lifecycle rules.
- [ ] Assistant follows creation/re-surfacing/stop rules.
- [ ] Audit metadata present for every resolution.
