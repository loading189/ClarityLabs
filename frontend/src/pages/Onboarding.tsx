import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api/client";
import { getIntegrationProfile, putIntegrationProfile } from "../api/integrations";

/**
 * Onboarding v2 (refactor goals)
 * - One flow: Create Org → Bootstrap Business (creates COA + IntegrationProfile + SimConfig)
 * - Optional tools: Apply COA template override, Pulse sim, Refresh status
 * - Integrations editor lives here (since you said “onboarding for now”), but written as a clean sub-panel
 * - Strong guardrails: disables buttons until prerequisites exist, safe defaults, predictable state
 */

type OrgOut = { id: string; name: string; created_at: string };

type BizOut = {
  id: string;
  org_id: string;
  name: string;
  industry?: string | null;
  created_at: string;
};

type ApplyCoaOut = { business_id: string; template: string; created: number; skipped: number };

type SimConfigOut = {
  business_id: string;
  enabled: boolean;
  profile: string;
  avg_events_per_day: number;
  typical_ticket_cents: number;
  payroll_every_n_days: number;
  updated_at: string;
};

type IntegrationProfile = {
  business_id: string;
  bank: boolean;
  payroll: boolean;
  card_processor: boolean;
  ecommerce: boolean;
  invoicing: boolean;
  simulation_params: {
    volume_level?: "low" | "medium" | "high";
    volatility?: "stable" | "normal" | "chaotic";
    seasonality?: boolean;
    [k: string]: any;
  };
  created_at?: string;
  updated_at?: string;
};

type IntegrationProfileOut = {
  business_id: string;
  bank: boolean;
  payroll: boolean;
  card_processor: boolean;
  ecommerce: boolean;
  invoicing: boolean;
  scenario_id: string;
  story_version: number;
  simulation_params: Record<string, any>;
  updated_at: string;
};

type BootstrapBusinessOut = {
  business: BizOut;
  sim_config: SimConfigOut;
  integration_profile: IntegrationProfileOut;
};

type BizStatusOut = {
  business_id: string;
  has_accounts: boolean;
  accounts_count: number;
  has_events: boolean;
  events_count: number;
  sim_enabled: boolean;
  ready: boolean;
};

type Toast = { kind: "ok" | "err" | "info"; text: string } | null;

const DEFAULT_INTEGRATIONS: IntegrationProfile = {
  business_id: "",
  bank: true,
  payroll: false,
  card_processor: false,
  ecommerce: false,
  invoicing: false,
  simulation_params: {
    volume_level: "medium",
    volatility: "normal",
    seasonality: false,
  },
};

function normalizeIntegrationProfile(
  prof: Partial<IntegrationProfile> | null | undefined,
  businessId: string
): IntegrationProfile {
  const merged: IntegrationProfile = {
    ...DEFAULT_INTEGRATIONS,
    ...(prof ?? {}),
    business_id: (prof as any)?.business_id ?? businessId,
    simulation_params:
      (prof as any)?.simulation_params && typeof (prof as any).simulation_params === "object"
        ? (prof as any).simulation_params
        : { ...DEFAULT_INTEGRATIONS.simulation_params },
  };

  // harden booleans
  merged.bank = (prof as any)?.bank ?? merged.bank;
  merged.payroll = (prof as any)?.payroll ?? merged.payroll;
  merged.card_processor = (prof as any)?.card_processor ?? merged.card_processor;
  merged.ecommerce = (prof as any)?.ecommerce ?? merged.ecommerce;
  merged.invoicing = (prof as any)?.invoicing ?? merged.invoicing;

  return merged;
}

function classBtn(disabled?: boolean) {
  return {
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid #e5e7eb",
    background: disabled ? "#f3f4f6" : "white",
    cursor: disabled ? "not-allowed" : "pointer",
    fontSize: 14,
  } as const;
}

function cardStyle() {
  return {
    border: "1px solid #e5e7eb",
    borderRadius: 12,
    padding: 12,
    background: "white",
  } as const;
}

export default function OnboardingPage() {
  // Inputs
  const [orgName, setOrgName] = useState("My Org");
  const [bizName, setBizName] = useState("My Business");
  const [industry, setIndustry] = useState("Service");

  // Entities created/loaded
  const [org, setOrg] = useState<OrgOut | null>(null);
  const [biz, setBiz] = useState<BizOut | null>(null);
  const [simConfig, setSimConfig] = useState<SimConfigOut | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationProfile | null>(null);
  const [status, setStatus] = useState<BizStatusOut | null>(null);

  // Optional COA override tool
  const [template, setTemplate] = useState<"service_simple" | "retail_simple">("service_simple");

  // “bootstrap knobs” you’ll actually want to control from onboarding
  const [bootSimEnabled, setBootSimEnabled] = useState(true);
  const [bootAvgEventsPerDay, setBootAvgEventsPerDay] = useState(12);
  const [bootTypicalTicketCents, setBootTypicalTicketCents] = useState(6500);
  const [bootPayrollEveryNDays, setBootPayrollEveryNDays] = useState(14);

  const [bootScenarioId, setBootScenarioId] = useState<string>("restaurant_v1");

  // We allow editing integration toggles BEFORE bootstrap; we reuse the same object
  const [draftIntegrations, setDraftIntegrations] = useState<IntegrationProfile>(
    normalizeIntegrationProfile(DEFAULT_INTEGRATIONS, "")
  );

  // UI state
  const [toast, setToast] = useState<Toast>(null);
  const [busy, setBusy] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  const businessId = biz?.id ?? "";
  const canCreateBiz = !!org?.id && !busy;
  const canDoBizOps = !!biz?.id && !busy;

  const headerMeta = useMemo(() => {
    return {
      orgId: org?.id ?? "—",
      businessId: biz?.id ?? "—",
      ready: status?.ready ?? false,
      accounts: status?.accounts_count ?? 0,
      events: status?.events_count ?? 0,
      simEnabled: status?.sim_enabled ?? (simConfig?.enabled ?? false),
    };
  }, [org?.id, biz?.id, status, simConfig]);

  function setOk(msg: string) {
    setToast({ kind: "ok", text: msg });
  }
  function setErr(msg: string) {
    setToast({ kind: "err", text: msg });
  }
  function setInfo(msg: string) {
    setToast({ kind: "info", text: msg });
  }

  // -------------------------
  // Actions
  // -------------------------

  async function createOrg() {
    setToast(null);
    setBusy(true);
    try {
      const o = await apiPost<OrgOut>("/onboarding/orgs", { name: orgName.trim() || "My Org" });
      setOrg(o);
      // Reset downstream state if you create a new org
      setBiz(null);
      setSimConfig(null);
      setIntegrations(null);
      setStatus(null);
      setOk(`Created org: ${o.name}`);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to create org");
    } finally {
      setBusy(false);
    }
  }

  async function bootstrapBusiness() {
    if (!org?.id) return setInfo("Create an org first.");

    setToast(null);
    setBusy(true);

    try {
      // Use draftIntegrations to seed initial integration toggles at bootstrap time.
      const payload = {
        org_id: org.id,
        name: bizName.trim() || "My Business",
        industry: industry.trim() || null,

        // integration mix
        bank: !!draftIntegrations.bank,
        payroll: !!draftIntegrations.payroll,
        card_processor: !!draftIntegrations.card_processor,
        ecommerce: !!draftIntegrations.ecommerce,
        invoicing: !!draftIntegrations.invoicing,

        // story knob (if backend supports it)
        scenario_id: bootScenarioId?.trim() ? bootScenarioId.trim() : undefined,

        // simulator knobs
        sim_enabled: !!bootSimEnabled,
        avg_events_per_day: Number.isFinite(bootAvgEventsPerDay) ? bootAvgEventsPerDay : 12,
        typical_ticket_cents: Number.isFinite(bootTypicalTicketCents) ? bootTypicalTicketCents : 6500,
        payroll_every_n_days: Number.isFinite(bootPayrollEveryNDays) ? bootPayrollEveryNDays : 14,
      };

      const out = await apiPost<BootstrapBusinessOut>("/onboarding/businesses/bootstrap", payload);

      setBiz(out.business);
      setSimConfig(out.sim_config);

      // Load profile from backend result, but normalize into our UI shape
      const normalized = normalizeIntegrationProfile(
        {
          business_id: out.integration_profile.business_id,
          bank: out.integration_profile.bank,
          payroll: out.integration_profile.payroll,
          card_processor: out.integration_profile.card_processor,
          ecommerce: out.integration_profile.ecommerce,
          invoicing: out.integration_profile.invoicing,
          simulation_params: out.integration_profile.simulation_params as any,
          updated_at: out.integration_profile.updated_at,
        },
        out.business.id
      );

      setIntegrations(normalized);
      setDraftIntegrations(normalized);

      setOk(`Bootstrapped business: ${out.business.name}`);
      await refreshStatus(out.business.id);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to bootstrap business");
    } finally {
      setBusy(false);
    }
  }

  async function refreshStatus(bid?: string) {
    const id = bid ?? biz?.id;
    if (!id) return setInfo("Create a business first.");

    setToast(null);
    try {
      const s = await apiGet<BizStatusOut>(`/onboarding/businesses/${id}/status`);
      setStatus(s);
      setInfo("Status refreshed.");
    } catch (e: any) {
      setErr(e?.message ?? "Failed to refresh status");
    }
  }

  async function applyCoaTemplate() {
    if (!biz?.id) return setInfo("Create a business first.");

    setToast(null);
    setBusy(true);
    try {
      const out = await apiPost<ApplyCoaOut>(`/onboarding/businesses/${biz.id}/coa/apply_template`, {
        template,
        replace_existing: false,
      });
      setOk(`Applied COA template: created ${out.created}, skipped ${out.skipped}`);
      await refreshStatus();
    } catch (e: any) {
      setErr(e?.message ?? "Failed to apply COA template");
    } finally {
      setBusy(false);
    }
  }

  async function pulseSim(n: number) {
    if (!biz?.id) return setInfo("Create a business first.");

    setToast(null);
    setBusy(true);
    try {
      const out = await apiPost<any>(`/sim/pulse/${biz.id}?n=${n}`, {});
      setOk(`Simulator inserted ${out.inserted}`);
      await refreshStatus();
    } catch (e: any) {
      setErr(e?.message ?? "Pulse failed");
    } finally {
      setBusy(false);
    }
  }

  async function loadProfile(bid?: string) {
    const id = bid ?? biz?.id;
    if (!id) return;

    setLoadingProfile(true);
    setToast(null);
    try {
      const prof = await getIntegrationProfile(id);
      const normalized = normalizeIntegrationProfile(prof as any, id);
      setIntegrations(normalized);
      setDraftIntegrations(normalized);
      setInfo("Loaded integration profile.");
    } catch (e: any) {
      // keep UI usable
      const normalized = normalizeIntegrationProfile(null, id);
      setIntegrations(normalized);
      setDraftIntegrations(normalized);
      setErr(e?.message ?? "Failed to load integration profile");
    } finally {
      setLoadingProfile(false);
    }
  }

  async function saveProfile() {
    if (!biz?.id) return setInfo("Create a business first.");

    const prof = draftIntegrations;
    setSavingProfile(true);
    setToast(null);

    try {
      const payload = {
        bank: prof.bank,
        payroll: prof.payroll,
        card_processor: prof.card_processor,
        ecommerce: prof.ecommerce,
        invoicing: prof.invoicing,
        simulation_params: prof.simulation_params ?? { ...DEFAULT_INTEGRATIONS.simulation_params },
      };

      const updated = await putIntegrationProfile(biz.id, payload);

      const normalized = normalizeIntegrationProfile(updated as any, biz.id);
      setIntegrations(normalized);
      setDraftIntegrations(normalized);

      setOk("Saved integration settings.");
    } catch (e: any) {
      setErr(e?.message ?? "Failed to save integration settings");
    } finally {
      setSavingProfile(false);
    }
  }

  // When biz changes, try loading backend profile (bootstrap already sets it, but this keeps resilience)
  useEffect(() => {
    if (!biz?.id) return;
    loadProfile(biz.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [biz?.id]);

  // -------------------------
  // Render
  // -------------------------

  return (
    <div style={{ ...cardStyle(), maxWidth: 980, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
        <div>
          <h2 style={{ margin: 0 }}>Onboarding</h2>
          <div style={{ fontSize: 12, opacity: 0.75, marginTop: 4 }}>
            Org: {headerMeta.orgId} · Business: {headerMeta.businessId} · Ready: {String(headerMeta.ready)}
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button style={classBtn(!canDoBizOps)} disabled={!canDoBizOps} onClick={() => refreshStatus()}>
            Refresh status
          </button>
          <button style={classBtn(!canDoBizOps)} disabled={!canDoBizOps} onClick={() => pulseSim(25)}>
            Pulse 25
          </button>
          <button style={classBtn(!canDoBizOps)} disabled={!canDoBizOps} onClick={() => pulseSim(100)}>
            Pulse 100
          </button>
        </div>
      </div>

      {toast && (
        <div
          style={{
            marginTop: 12,
            padding: 10,
            borderRadius: 10,
            border: "1px solid #e5e7eb",
            background:
              toast.kind === "ok" ? "#f0fdf4" : toast.kind === "err" ? "#fef2f2" : "#eff6ff",
            color: toast.kind === "err" ? "#991b1b" : "#111827",
          }}
        >
          {toast.text}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
        {/* ORG */}
        <div style={cardStyle()}>
          <h3 style={{ marginTop: 0 }}>1) Organization</h3>
          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, opacity: 0.8 }}>Org name</span>
            <input
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
            />
          </label>

          <button style={{ ...classBtn(busy), marginTop: 10 }} disabled={busy} onClick={createOrg}>
            {busy ? "Working…" : "Create org"}
          </button>

          {org && <div style={{ marginTop: 10, fontSize: 12, opacity: 0.8 }}>org_id: {org.id}</div>}
        </div>

        {/* BUSINESS + BOOTSTRAP KNOBS */}
        <div style={cardStyle()}>
          <h3 style={{ marginTop: 0 }}>2) Business (Bootstrap)</h3>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, opacity: 0.8 }}>Business name</span>
            <input
              value={bizName}
              onChange={(e) => setBizName(e.target.value)}
              style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
            />
          </label>

          <label style={{ display: "grid", gap: 6, marginTop: 8 }}>
            <span style={{ fontSize: 12, opacity: 0.8 }}>Industry</span>
            <input
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
            />
          </label>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12, opacity: 0.75 }}>Scenario</span>
              <input
                value={bootScenarioId}
                onChange={(e) => setBootScenarioId(e.target.value)}
                style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
                placeholder="restaurant_v1"
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12, opacity: 0.75 }}>Sim enabled</span>
              <select
                value={String(bootSimEnabled)}
                onChange={(e) => setBootSimEnabled(e.target.value === "true")}
                style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
              >
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12, opacity: 0.75 }}>Avg events/day</span>
              <input
                type="number"
                value={bootAvgEventsPerDay}
                onChange={(e) => setBootAvgEventsPerDay(Number(e.target.value))}
                style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12, opacity: 0.75 }}>Typical ticket (cents)</span>
              <input
                type="number"
                value={bootTypicalTicketCents}
                onChange={(e) => setBootTypicalTicketCents(Number(e.target.value))}
                style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12, opacity: 0.75 }}>Payroll every N days</span>
              <input
                type="number"
                value={bootPayrollEveryNDays}
                onChange={(e) => setBootPayrollEveryNDays(Number(e.target.value))}
                style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
              />
            </label>
          </div>

          <button
            style={{ ...classBtn(!canCreateBiz), marginTop: 10 }}
            disabled={!canCreateBiz}
            onClick={bootstrapBusiness}
          >
            {busy ? "Working…" : "Bootstrap business (COA + Integrations + Sim)"}
          </button>

          {biz && <div style={{ marginTop: 10, fontSize: 12, opacity: 0.8 }}>business_id: {biz.id}</div>}
        </div>
      </div>

      {/* Status summary */}
      <div style={{ ...cardStyle(), marginTop: 12 }}>
        <h3 style={{ marginTop: 0 }}>3) Readiness</h3>

        {!biz?.id ? (
          <div style={{ opacity: 0.7 }}>Create a business to see readiness.</div>
        ) : !status ? (
          <div style={{ opacity: 0.7 }}>No status loaded yet. Click “Refresh status”.</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
            <Kpi label="Accounts" value={String(status.accounts_count)} />
            <Kpi label="Events" value={String(status.events_count)} />
            <Kpi label="Sim enabled" value={String(status.sim_enabled)} />
            <Kpi label="Ready" value={String(status.ready)} />
          </div>
        )}

        {status && (
          <pre style={{ marginTop: 10, background: "#f9fafb", padding: 10, borderRadius: 10, overflow: "auto" }}>
            {JSON.stringify(status, null, 2)}
          </pre>
        )}
      </div>

      {/* COA override tool */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
        <div style={cardStyle()}>
          <h3 style={{ marginTop: 0 }}>4) COA Template (Optional Override)</h3>
          <div style={{ fontSize: 12, opacity: 0.75, marginBottom: 8 }}>
            Bootstrap already seeds your canonical COA/categories/mappings. This is a helper for experimenting.
          </div>

          <select
            value={template}
            onChange={(e) => setTemplate(e.target.value as any)}
            style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
          >
            <option value="service_simple">service_simple</option>
            <option value="retail_simple">retail_simple</option>
          </select>

          <button
            style={{ ...classBtn(!canDoBizOps), marginTop: 10 }}
            disabled={!canDoBizOps}
            onClick={applyCoaTemplate}
          >
            Apply template
          </button>
        </div>

        {/* SimConfig visibility (read-only here, since simulator tab will later own it) */}
        <div style={cardStyle()}>
          <h3 style={{ marginTop: 0 }}>5) Simulator Config (Created on Bootstrap)</h3>
          {!simConfig ? (
            <div style={{ opacity: 0.7 }}>Bootstrap a business to create a sim config.</div>
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <Kpi label="Enabled" value={String(simConfig.enabled)} />
                <Kpi label="Profile" value={simConfig.profile} />
                <Kpi label="Avg/day" value={String(simConfig.avg_events_per_day)} />
                <Kpi label="Ticket (¢)" value={String(simConfig.typical_ticket_cents)} />
              </div>

              <div style={{ marginTop: 10, fontSize: 12, opacity: 0.65 }}>
                Updated: {new Date(simConfig.updated_at).toLocaleString()}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Integrations panel (the main thing you wanted for onboarding right now) */}
      <div style={{ ...cardStyle(), marginTop: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>6) Integrations (Simulator Toggles)</h3>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              style={classBtn(!canDoBizOps || loadingProfile)}
              disabled={!canDoBizOps || loadingProfile}
              onClick={() => loadProfile()}
            >
              {loadingProfile ? "Loading…" : "Reload"}
            </button>
            <button
              style={classBtn(!canDoBizOps || savingProfile)}
              disabled={!canDoBizOps || savingProfile}
              onClick={saveProfile}
            >
              {savingProfile ? "Saving…" : "Save"}
            </button>
          </div>
        </div>

        {!biz?.id ? (
          <div style={{ marginTop: 10, opacity: 0.7 }}>
            Pick your integration toggles above, then bootstrap a business to persist them.
          </div>
        ) : (
          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <ToggleRow
              label="Bank (Plaid-like)"
              checked={draftIntegrations.bank}
              onChange={(v) => setDraftIntegrations((p) => ({ ...p, business_id: businessId, bank: v }))}
            />
            <ToggleRow
              label="Payroll"
              checked={draftIntegrations.payroll}
              onChange={(v) => setDraftIntegrations((p) => ({ ...p, business_id: businessId, payroll: v }))}
            />
            <ToggleRow
              label="Card processor (Stripe/Square)"
              checked={draftIntegrations.card_processor}
              onChange={(v) => setDraftIntegrations((p) => ({ ...p, business_id: businessId, card_processor: v }))}
            />
            <ToggleRow
              label="E-commerce (Shopify)"
              checked={draftIntegrations.ecommerce}
              onChange={(v) => setDraftIntegrations((p) => ({ ...p, business_id: businessId, ecommerce: v }))}
            />
            <ToggleRow
              label="Invoicing (QB/Invoicing)"
              checked={draftIntegrations.invoicing}
              onChange={(v) => setDraftIntegrations((p) => ({ ...p, business_id: businessId, invoicing: v }))}
            />

            <div style={{ gridColumn: "1 / -1" }}>
              <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>Simulation params</div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                <label style={{ display: "grid", gap: 6 }}>
                  <span style={{ fontSize: 12, opacity: 0.75 }}>Volume</span>
                  <select
                    value={draftIntegrations.simulation_params.volume_level ?? "medium"}
                    onChange={(e) =>
                      setDraftIntegrations((p) => ({
                        ...p,
                        business_id: businessId,
                        simulation_params: { ...(p.simulation_params ?? {}), volume_level: e.target.value as any },
                      }))
                    }
                    style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
                  >
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                  </select>
                </label>

                <label style={{ display: "grid", gap: 6 }}>
                  <span style={{ fontSize: 12, opacity: 0.75 }}>Volatility</span>
                  <select
                    value={draftIntegrations.simulation_params.volatility ?? "normal"}
                    onChange={(e) =>
                      setDraftIntegrations((p) => ({
                        ...p,
                        business_id: businessId,
                        simulation_params: { ...(p.simulation_params ?? {}), volatility: e.target.value as any },
                      }))
                    }
                    style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
                  >
                    <option value="stable">stable</option>
                    <option value="normal">normal</option>
                    <option value="chaotic">chaotic</option>
                  </select>
                </label>

                <label style={{ display: "grid", gap: 6 }}>
                  <span style={{ fontSize: 12, opacity: 0.75 }}>Seasonality</span>
                  <select
                    value={String(!!draftIntegrations.simulation_params.seasonality)}
                    onChange={(e) =>
                      setDraftIntegrations((p) => ({
                        ...p,
                        business_id: businessId,
                        simulation_params: { ...(p.simulation_params ?? {}), seasonality: e.target.value === "true" },
                      }))
                    }
                    style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
                  >
                    <option value="false">false</option>
                    <option value="true">true</option>
                  </select>
                </label>
              </div>

              <div style={{ marginTop: 8, fontSize: 12, opacity: 0.6 }}>
                These toggles control which raw event shapes the simulator emits for this business.
              </div>

              {!!integrations?.updated_at && (
                <div style={{ marginTop: 8, fontSize: 12, opacity: 0.6 }}>
                  Last saved: {new Date(integrations.updated_at).toLocaleString()}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 10 }}>
      <div style={{ fontSize: 12, opacity: 0.7 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600 }}>{value}</div>
    </div>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        border: "1px solid #e5e7eb",
        borderRadius: 12,
        padding: "10px 12px",
      }}
    >
      <span style={{ fontSize: 14 }}>{label}</span>
      <select
        value={String(checked)}
        onChange={(e) => onChange(e.target.value === "true")}
        style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
      >
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    </label>
  );
}
