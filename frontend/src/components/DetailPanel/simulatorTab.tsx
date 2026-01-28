import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  getScenarioCatalog,
  getSimPlan,
  getSimTruth,
  putSimPlan,
  listSimInterventions,
  createSimIntervention,
  updateSimIntervention,
  generateSimEvents,
  getInterventionLibrary,
  // ✅ you MUST add this export in ../../api/sim
  deleteSimIntervention,
} from "../../api/sim";

/**
 * SimulatorTabV2 (DROP-IN)
 * Goals:
 * - polished control-room UI
 * - uses: scenario catalog, plan/story, baseline plan editor, intervention library + CRUD, generation controls
 * - safer UX: dirty tracking, quick add, duplicate, delete w/ confirm, bulk enable/disable, sort, search
 * - reproducibility: seed + shocks toggles
 *
 * Requires:
 * - api/sim exports:
 *   - deleteSimIntervention(businessId, interventionId)
 *   - generateSimEvents returns { inserted, deleted, ... }
 */

type SimPlanOut = {
  business_id: string;
  scenario_id: string;
  story_version: number;
  plan: any;
  story_text: string;
};

type Intervention = {
  id: string;
  business_id: string;
  kind: string;
  name: string;
  start_date: string; // YYYY-MM-DD
  duration_days: number | null;
  params: any;
  enabled: boolean;
  updated_at?: string;
};

type ScenarioCatalog = {
  version: number;
  scenarios: Array<{
    id: string;
    name: string;
    summary?: string;
    defaults?: Record<string, any>;
  }>;
};

type FieldType = "number" | "percent" | "text" | "days";

type InterventionTemplate = {
  kind: string;
  label: string;
  description: string;
  defaults: Record<string, any>;
  fields: Array<{
    key: string;
    label: string;
    type: FieldType;
    default?: any;
    min?: number;
    max?: number;
    step?: number;
  }>;
};

type Toast = { kind: "ok" | "err" | "info"; text: string } | null;

function isoToday() {
  return new Date().toISOString().slice(0, 10);
}

function safeJsonParse(text: string): { ok: true; value: any } | { ok: false; error: string } {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e: any) {
    return { ok: false, error: e?.message ?? "Invalid JSON" };
  }
}

function deepClone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

function clamp(n: number, lo?: number, hi?: number) {
  if (lo !== undefined) n = Math.max(lo, n);
  if (hi !== undefined) n = Math.min(hi, n);
  return n;
}

function numOr<T>(v: any, fallback: T): number | T {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

// percent fields stored as 0..1 in backend; UI shows 0..100.
function pctToUi(p: any): number {
  const n = Number(p);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 10000) / 100;
}
function pctToApi(uiPct: any): number {
  const n = Number(uiPct);
  if (!Number.isFinite(n)) return 0;
  return n / 100;
}

// --------------------
// Styling (inline, drop-in)
// --------------------
const styles = {
  page: {
    paddingTop: 10,
    maxWidth: 1180,
  } as React.CSSProperties,
  headerRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 14,
    alignItems: "flex-start",
    flexWrap: "wrap",
  } as React.CSSProperties,
  h3: { margin: 0, fontSize: 18, letterSpacing: -0.2 } as React.CSSProperties,
  meta: { fontSize: 12, opacity: 0.72, marginTop: 6, lineHeight: 1.35 } as React.CSSProperties,
  subtle: { fontSize: 12, opacity: 0.7 } as React.CSSProperties,
  card: {
    border: "1px solid #e5e7eb",
    borderRadius: 16,
    padding: 14,
    background: "white",
    boxShadow: "0 1px 0 rgba(17,24,39,0.02)",
  } as React.CSSProperties,
  cardTitleRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: 12,
    flexWrap: "wrap",
  } as React.CSSProperties,
  h4: { margin: 0, fontSize: 14, letterSpacing: -0.1 } as React.CSSProperties,
  btn: (disabled?: boolean, intent: "default" | "primary" | "danger" = "default"): React.CSSProperties => {
    const base: React.CSSProperties = {
      padding: "10px 12px",
      borderRadius: 12,
      border: "1px solid #e5e7eb",
      background: disabled ? "#f3f4f6" : "white",
      cursor: disabled ? "not-allowed" : "pointer",
      fontSize: 14,
      userSelect: "none",
      transition: "transform 120ms ease, box-shadow 120ms ease",
    };

    if (intent === "primary") {
      base.border = "1px solid #111827";
      base.background = disabled ? "#e5e7eb" : "#111827";
      base.color = disabled ? "#6b7280" : "white";
    } else if (intent === "danger") {
      base.border = "1px solid #ef4444";
      base.background = disabled ? "#fee2e2" : "#fff";
      base.color = "#991b1b";
    }

    return base;
  },
  pill: (bg: string, color?: string): React.CSSProperties => ({
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "6px 10px",
    borderRadius: 999,
    border: "1px solid #e5e7eb",
    background: bg,
    fontSize: 12,
    color: color ?? "#111827",
    whiteSpace: "nowrap",
  }),
  input: {
    padding: 10,
    borderRadius: 12,
    border: "1px solid #e5e7eb",
    outline: "none",
  } as React.CSSProperties,
  select: {
    width: "100%",
    padding: 10,
    borderRadius: 12,
    border: "1px solid #e5e7eb",
    outline: "none",
    background: "white",
  } as React.CSSProperties,
  dividerTop: {
    marginTop: 12,
    borderTop: "1px solid #e5e7eb",
    paddingTop: 12,
  } as React.CSSProperties,
  grid2: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
  } as React.CSSProperties,
  gridRight: {
    display: "grid",
    gap: 12,
  } as React.CSSProperties,
  tagRow: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" } as React.CSSProperties,
  storyBox: {
    border: "1px solid #e5e7eb",
    borderRadius: 14,
    background: "#f9fafb",
    padding: 12,
    lineHeight: 1.55,
    whiteSpace: "pre-wrap",
    fontSize: 13.5,
  } as React.CSSProperties,
  textarea: {
    width: "100%",
    marginTop: 10,
    minHeight: 340,
    padding: 12,
    borderRadius: 12,
    border: "1px solid #e5e7eb",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
    fontSize: 12,
    background: "#ffffff",
    outline: "none",
  } as React.CSSProperties,
};

function sortInterventionsStable(ivs: Intervention[], mode: "start_date" | "updated" | "kind" | "enabled") {
  const arr = [...ivs];
  arr.sort((a, b) => {
    const aEnabled = a.enabled ? 1 : 0;
    const bEnabled = b.enabled ? 1 : 0;

    if (mode === "enabled") {
      if (bEnabled !== aEnabled) return bEnabled - aEnabled;
      // then by start date
      return (a.start_date || "").localeCompare(b.start_date || "");
    }
    if (mode === "kind") {
      const k = (a.kind || "").localeCompare(b.kind || "");
      if (k !== 0) return k;
      return (a.start_date || "").localeCompare(b.start_date || "");
    }
    if (mode === "updated") {
      const au = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const bu = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      if (bu !== au) return bu - au;
      return (a.start_date || "").localeCompare(b.start_date || "");
    }
    // start_date
    return (a.start_date || "").localeCompare(b.start_date || "");
  });
  return arr;
}

export default function SimulatorTabV2({
  businessId,
  onAfterPulse,
  onAfterSave,
}: {
  businessId: string;
  onAfterPulse?: () => void;
  onAfterSave?: () => void;
}) {
  void onAfterPulse;
  void onAfterSave;
  const [catalog, setCatalog] = useState<ScenarioCatalog | null>(null);
  const [templates, setTemplates] = useState<InterventionTemplate[]>([]);
  const [plan, setPlan] = useState<SimPlanOut | null>(null);

  const [draftPlanObj, setDraftPlanObj] = useState<any>(null);
  const [planEditorText, setPlanEditorText] = useState<string>("{}");
  const [planEditorErr, setPlanEditorErr] = useState<string | null>(null);

  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [ivDraft, setIvDraft] = useState<Record<string, Intervention>>({});
  const [truth, setTruth] = useState<any[] | null>(null);

  const [toast, setToast] = useState<Toast>(null);
  const [busy, setBusy] = useState(false);

  // UI controls
  const [ivSearch, setIvSearch] = useState("");
  const [ivSort, setIvSort] = useState<"enabled" | "start_date" | "updated" | "kind">("enabled");
  const [showJsonPlan, setShowJsonPlan] = useState(true);

  // Generate controls (use the full feature surface)
  const [genStartDate, setGenStartDate] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() - 365);
    return d.toISOString().slice(0, 10);
  });
  const [genDays, setGenDays] = useState(365);
  const [genMode, setGenMode] = useState<"replace_from_start" | "append">("replace_from_start");
  const [genSeed, setGenSeed] = useState<number>(1337);

  // Shocks (secondary layer)
  const [enableShocks, setEnableShocks] = useState(true);
  const [shockDays, setShockDays] = useState(10);
  const [revenueDropPctUi, setRevenueDropPctUi] = useState(30); // UI percent 0..100
  const [expenseSpikePctUi, setExpenseSpikePctUi] = useState(50);

  // Toast timer
  const toastTimer = useRef<number | null>(null);
  function pushToast(t: Toast) {
    setToast(t);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 4500);
  }

  const templateByKind = useMemo(() => {
    const m = new Map<string, InterventionTemplate>();
    for (const t of templates) m.set(t.kind, t);
    return m;
  }, [templates]);

  function ensureIvDraft(ivs: Intervention[]) {
    const next: Record<string, Intervention> = {};
    for (const iv of ivs) next[iv.id] = deepClone(iv);
    setIvDraft(next);
  }

  async function loadAll() {
    if (!businessId) return;
    setBusy(true);
    setToast(null);
    setPlanEditorErr(null);

    try {
      const [cat, p, ivs, libs, truthOut] = await Promise.all([
        getScenarioCatalog(),
        getSimPlan(businessId),
        listSimInterventions(businessId),
        getInterventionLibrary(),
        getSimTruth(businessId),
      ]);

      
      setTruth(truthOut?.truth_events ?? []);
      setCatalog(cat);
      setPlan(p);
      setDraftPlanObj(p.plan);

      setPlanEditorText(JSON.stringify(p.plan ?? {}, null, 2));

      setInterventions(ivs ?? []);
      ensureIvDraft(ivs ?? []);

      setTemplates(libs ?? []);
      pushToast({ kind: "info", text: "Simulator loaded." });
    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Failed to load simulator." });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!businessId) return;
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId]);

  const scenarioName = useMemo(() => {
    const s = catalog?.scenarios?.find((x) => x.id === plan?.scenario_id);
    return s?.name ?? plan?.scenario_id ?? "—";
  }, [catalog, plan?.scenario_id]);

  const scenarioSummary = useMemo(() => {
    const s = catalog?.scenarios?.find((x) => x.id === plan?.scenario_id);
    return s?.summary ?? "";
  }, [catalog, plan?.scenario_id]);

  const interventionCounts = useMemo(() => {
    const enabled = interventions.filter((x) => x.enabled).length;
    return { total: interventions.length, enabled };
  }, [interventions]);

  const visibleInterventions = useMemo(() => {
    const q = ivSearch.trim().toLowerCase();
    const base = sortInterventionsStable(interventions, ivSort);
    if (!q) return base;

    return base.filter((iv) => {
      const blob = `${iv.name} ${iv.kind} ${iv.start_date} ${iv.duration_days ?? ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [interventions, ivSearch, ivSort]);

  function ivDirty(id: string) {
    const original = interventions.find((x) => x.id === id);
    const draft = ivDraft[id];
    if (!original || !draft) return false;
    return JSON.stringify(original) !== JSON.stringify(draft);
  }

  function updateIvField(id: string, patch: Partial<Intervention>) {
    setIvDraft((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  function updateIvParam(id: string, key: string, value: any) {
    setIvDraft((prev) => {
      const cur = prev[id];
      if (!cur) return prev;
      return {
        ...prev,
        [id]: {
          ...cur,
          params: { ...(cur.params ?? {}), [key]: value },
        },
      };
    });
  }

  async function savePlan() {
    if (!plan) return;

    const parsed = safeJsonParse(planEditorText);
    if (!parsed.ok) {
      setPlanEditorErr(parsed.error);
      pushToast({ kind: "err", text: "Fix JSON before saving." });
      return;
    }

    setPlanEditorErr(null);
    setBusy(true);
    setToast(null);

    try {
      await putSimPlan(businessId, {
        scenario_id: plan.scenario_id,
        story_version: plan.story_version,
        plan: parsed.value,
      });

      setDraftPlanObj(parsed.value);
      pushToast({ kind: "ok", text: "Saved baseline plan." });
      await loadAll();
    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Failed to save plan." });
    } finally {
      setBusy(false);
    }
  }

  async function changeScenario(nextScenarioId: string) {
    if (!plan) return;
    setBusy(true);
    setToast(null);

    try {
      await putSimPlan(businessId, {
        scenario_id: nextScenarioId,
        story_version: plan.story_version,
        plan: draftPlanObj ?? plan.plan ?? {},
      });

      pushToast({ kind: "ok", text: `Scenario set to ${nextScenarioId}.` });
      await loadAll();
    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Failed to change scenario." });
    } finally {
      setBusy(false);
    }
  }

  async function addInterventionFromTemplate(t: InterventionTemplate) {
    setBusy(true);
    setToast(null);

    try {
      const payload = {
        kind: t.kind,
        name: t.label,
        start_date: isoToday(),
        duration_days: 30,
        params: t.defaults ?? {},
        enabled: true,
      };

      await createSimIntervention(businessId, payload as any);
      pushToast({ kind: "ok", text: `Added: ${t.label}` });
      await loadAll();
    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Failed to add intervention." });
    } finally {
      setBusy(false);
    }
  }

  async function duplicateIntervention(iv: Intervention) {
    setBusy(true);
    setToast(null);

    try {
      const payload = {
        kind: iv.kind,
        name: `${iv.name} (copy)`,
        start_date: iv.start_date ?? isoToday(),
        duration_days: iv.duration_days ?? 30,
        params: iv.params ?? {},
        enabled: iv.enabled,
      };
      await createSimIntervention(businessId, payload as any);
      pushToast({ kind: "ok", text: "Duplicated intervention." });
      await loadAll();
    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Duplicate failed." });
    } finally {
      setBusy(false);
    }
  }

  async function saveIntervention(id: string) {
    const draft = ivDraft[id];
    if (!draft) return;
    setBusy(true);
    setToast(null);

    try {
      await updateSimIntervention(businessId, id, {
        name: draft.name,
        start_date: draft.start_date,
        duration_days: draft.duration_days,
        params: draft.params ?? {},
        enabled: draft.enabled,
      });

      pushToast({ kind: "ok", text: `Saved: ${draft.name}` });
      await loadAll();
    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Failed to save intervention." });
    } finally {
      setBusy(false);
    }
  }

  function revertIntervention(id: string) {
    const original = interventions.find((x) => x.id === id);
    if (!original) return;
    setIvDraft((prev) => ({ ...prev, [id]: deepClone(original) }));
    pushToast({ kind: "info", text: "Reverted changes." });
  }

  async function deleteIntervention(iv: Intervention) {
    const ok = window.confirm(`Delete intervention?\n\n${iv.name}\n(${iv.kind})`);
    if (!ok) return;

    setBusy(true);
    setToast(null);

    try {
      await deleteSimIntervention(businessId, iv.id);
      pushToast({ kind: "ok", text: "Deleted intervention." });
      await loadAll();
    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Delete failed." });
    } finally {
      setBusy(false);
    }
  }

  async function bulkSetEnabled(enabled: boolean) {
    const ok = window.confirm(`${enabled ? "Enable" : "Disable"} ALL interventions?`);
    if (!ok) return;

    setBusy(true);
    setToast(null);

    try {
      // patch each (simple MVP; later you can add a backend bulk endpoint)
      for (const iv of interventions) {
        await updateSimIntervention(businessId, iv.id, { enabled });
      }
      pushToast({ kind: "ok", text: `${enabled ? "Enabled" : "Disabled"} all interventions.` });
      await loadAll();
    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Bulk update failed." });
    } finally {
      setBusy(false);
    }
  }

  async function runGenerate() {
    setBusy(true);
    setToast(null);

    try {
      const days = clamp(Number(genDays), 1, 3650);
      const start_date = genStartDate;

      const r = await generateSimEvents(businessId, {
        start_date,
        days,
        mode: genMode,
        seed: clamp(Number(genSeed), 0, 2_000_000_000),
        enable_shocks: !!enableShocks,
        shock_days: clamp(Number(shockDays), 1, 365),
        revenue_drop_pct: clamp(Number(revenueDropPctUi) / 100, 0.05, 0.9),
        expense_spike_pct: clamp(Number(expenseSpikePctUi) / 100, 0.05, 5.0),
      });

      pushToast({ kind: "ok", text: `Generated ${r.inserted} events (deleted ${r.deleted}).` });
      await loadAll();

    } catch (e: any) {
      pushToast({ kind: "err", text: e?.message ?? "Generate failed." });
    } finally {
      setBusy(false);
    }
  }

  // Render guards
  if (!businessId) return <div style={{ paddingTop: 8 }}>Pick a business.</div>;
  if (!plan && busy) return <div style={{ paddingTop: 8 }}>Loading…</div>;
  if (!plan) return <div style={{ paddingTop: 8 }}>No simulator plan found (bootstrap should create it).</div>;

  return (
    <div style={styles.page}>
      {/* HEADER */}
      <div style={styles.headerRow}>
        <div style={{ minWidth: 320 }}>
          <h3 style={styles.h3}>Simulator Control Room</h3>
          <div style={styles.meta}>
            Scenario: <b>{scenarioName}</b>{" "}
            <span style={{ opacity: 0.6 }}>·</span>{" "}
            Interventions:{" "}
            <b>
              {interventionCounts.enabled}/{interventionCounts.total}
            </b>{" "}
            enabled{" "}
            <span style={{ opacity: 0.6 }}>·</span>{" "}
            business_id: <span style={{ fontFamily: "ui-monospace, Menlo, monospace" }}>{businessId}</span>
          </div>
          {!!scenarioSummary && <div style={{ ...styles.subtle, marginTop: 6 }}>{scenarioSummary}</div>}
          <div style={{ ...styles.subtle, marginTop: 8 }}>
            Vision: baseline = “business personality”; interventions = “plot twists”; generate = “rewrite reality.”
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <button style={styles.btn(busy)} disabled={busy} onClick={loadAll}>
            {busy ? "Working…" : "Reload"}
          </button>
          <button style={styles.btn(busy)} disabled={busy} onClick={savePlan}>
            Save baseline
          </button>
          <button style={styles.btn(busy, "primary")} disabled={busy} onClick={runGenerate}>
            Generate events
          </button>
        </div>
      </div>

      {/* TOAST */}
      {toast && (
        <div
          style={{
            ...styles.card,
            marginTop: 12,
            background: toast.kind === "err" ? "#fef2f2" : toast.kind === "ok" ? "#f0fdf4" : "#eff6ff",
            color: toast.kind === "err" ? "#991b1b" : "#111827",
            borderColor: toast.kind === "err" ? "#fecaca" : toast.kind === "ok" ? "#bbf7d0" : "#bfdbfe",
          }}
        >
          {toast.text}
        </div>
      )}

      {/* TOP ROW */}
      <div style={{ ...styles.grid2, marginTop: 12 }}>
        {/* STORY */}
        <div style={styles.card}>
          <div style={styles.cardTitleRow}>
            <h4 style={styles.h4}>The Story</h4>
            <span style={styles.pill("#f9fafb")}>Human-readable truth</span>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ ...styles.subtle, marginBottom: 8 }}>
              This is what the simulator believes is happening in the business right now.
            </div>

            <div style={styles.storyBox}>{plan.story_text || "No story text yet."}</div>

            <div style={{ ...styles.subtle, marginTop: 10 }}>
              Tip: Add an intervention at a specific date and regenerate — you should “see” it in the transaction history.
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div style={styles.gridRight}>
          {/* SCENARIO PICKER */}
          <div style={styles.card}>
            <div style={styles.cardTitleRow}>
              <h4 style={styles.h4}>Scenario</h4>
              <span style={styles.pill("#f9fafb")}>World preset</span>
            </div>
            <div style={{ ...styles.subtle, marginTop: 6 }}>Pick a starting world for the baseline plan.</div>

            <div style={{ marginTop: 10 }}>
              <select
                value={plan.scenario_id}
                disabled={busy}
                onChange={(e) => changeScenario(e.target.value)}
                style={{
                  ...styles.select,
                  background: busy ? "#f3f4f6" : "white",
                }}
              >
                {(catalog?.scenarios ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.id})
                  </option>
                ))}
                {!catalog?.scenarios?.length && <option value={plan.scenario_id}>{plan.scenario_id}</option>}
              </select>
            </div>
          </div>

          {/* GENERATE */}
          <div style={styles.card}>
            <div style={styles.cardTitleRow}>
              <h4 style={styles.h4}>Generate</h4>
              <span style={styles.pill("#f9fafb")}>Write / rewrite history</span>
            </div>
            <div style={{ ...styles.subtle, marginTop: 6 }}>
              Uses baseline + interventions (primary) + optional random shocks (secondary).
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span style={styles.subtle}>Start date</span>
                <input
                  type="date"
                  value={genStartDate}
                  disabled={busy}
                  onChange={(e) => setGenStartDate(e.target.value)}
                  style={styles.input}
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span style={styles.subtle}>Days</span>
                <input
                  type="number"
                  value={genDays}
                  disabled={busy}
                  onChange={(e) => setGenDays(Number(e.target.value))}
                  style={styles.input}
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span style={styles.subtle}>Mode</span>
                <select
                  value={genMode}
                  disabled={busy}
                  onChange={(e) => setGenMode(e.target.value as any)}
                  style={styles.select}
                >
                  <option value="replace_from_start">replace_from_start (rewrite)</option>
                  <option value="append">append (extend)</option>
                </select>
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span style={styles.subtle}>Seed (reproducible)</span>
                <input
                  type="number"
                  value={genSeed}
                  disabled={busy}
                  onChange={(e) => setGenSeed(Number(e.target.value))}
                  style={styles.input}
                />
              </label>
            </div>

            {/* Shocks */}
            <div style={{ ...styles.dividerTop, marginTop: 12 }}>
              <div style={styles.tagRow}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>Secondary random shocks</span>
                <span style={styles.pill(enableShocks ? "#f0fdf4" : "#f9fafb")}>
                  {enableShocks ? "Enabled" : "Disabled"}
                </span>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
                <label style={{ display: "grid", gap: 6 }}>
                  <span style={styles.subtle}>Enable shocks</span>
                  <button
                    style={styles.btn(busy)}
                    disabled={busy}
                    onClick={() => setEnableShocks((v) => !v)}
                  >
                    {enableShocks ? "Turn off" : "Turn on"}
                  </button>
                </label>

                <label style={{ display: "grid", gap: 6 }}>
                  <span style={styles.subtle}>Shock window (days)</span>
                  <input
                    type="number"
                    value={shockDays}
                    disabled={busy || !enableShocks}
                    onChange={(e) => setShockDays(Number(e.target.value))}
                    style={styles.input}
                  />
                </label>

                <label style={{ display: "grid", gap: 6 }}>
                  <span style={styles.subtle}>Revenue drop (%)</span>
                  <input
                    type="number"
                    value={revenueDropPctUi}
                    disabled={busy || !enableShocks}
                    min={5}
                    max={90}
                    step={1}
                    onChange={(e) => setRevenueDropPctUi(Number(e.target.value))}
                    style={styles.input}
                  />
                </label>

                <label style={{ display: "grid", gap: 6 }}>
                  <span style={styles.subtle}>Expense spike (%)</span>
                  <input
                    type="number"
                    value={expenseSpikePctUi}
                    disabled={busy || !enableShocks}
                    min={5}
                    max={500}
                    step={1}
                    onChange={(e) => setExpenseSpikePctUi(Number(e.target.value))}
                    style={styles.input}
                  />
                </label>
              </div>

              <div style={{ ...styles.subtle, marginTop: 10 }}>
                Pro move: keep shocks off while debugging interventions, then turn them on for realism.
              </div>
            </div>

            {/* Quick ranges */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
              <button
                style={styles.btn(busy)}
                disabled={busy}
                onClick={() => {
                  const d = new Date();
                  d.setDate(d.getDate() - 30);
                  setGenStartDate(d.toISOString().slice(0, 10));
                  setGenDays(30);
                }}
              >
                30d
              </button>
              <button
                style={styles.btn(busy)}
                disabled={busy}
                onClick={() => {
                  const d = new Date();
                  d.setDate(d.getDate() - 180);
                  setGenStartDate(d.toISOString().slice(0, 10));
                  setGenDays(180);
                }}
              >
                180d
              </button>
              <button
                style={styles.btn(busy)}
                disabled={busy}
                onClick={() => {
                  const d = new Date();
                  d.setDate(d.getDate() - 365);
                  setGenStartDate(d.toISOString().slice(0, 10));
                  setGenDays(365);
                }}
              >
                1y
              </button>
              <button
                style={styles.btn(busy)}
                disabled={busy}
                onClick={() => {
                  const d = new Date();
                  d.setDate(d.getDate() - 730);
                  setGenStartDate(d.toISOString().slice(0, 10));
                  setGenDays(730);
                }}
              >
                2y
              </button>
            </div>

            <div style={{ ...styles.subtle, marginTop: 10 }}>
              “replace_from_start” is your shock-testing superpower — it makes the past deterministic again.
            </div>
          </div>
        </div>
      </div>

      {/* BASELINE */}
      <div style={{ ...styles.card, marginTop: 12 }}>
        <div style={styles.cardTitleRow}>
          <div>
            <h4 style={styles.h4}>Baseline Levers</h4>
            <div style={styles.subtle}>These knobs define the business when nothing unusual is happening.</div>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <button
              style={styles.btn(busy)}
              disabled={busy}
              onClick={() => setShowJsonPlan((v) => !v)}
            >
              {showJsonPlan ? "Hide JSON" : "Show JSON"}
            </button>

            <button
              style={styles.btn(busy)}
              disabled={busy}
              onClick={() => {
                const parsed = safeJsonParse(planEditorText);
                if (!parsed.ok) {
                  setPlanEditorErr(parsed.error);
                  pushToast({ kind: "err", text: "Cannot format invalid JSON." });
                  return;
                }
                setPlanEditorErr(null);
                setPlanEditorText(JSON.stringify(parsed.value, null, 2));
                pushToast({ kind: "ok", text: "Formatted JSON." });
              }}
            >
              Format JSON
            </button>

            <button
              style={styles.btn(busy)}
              disabled={busy}
              onClick={() => {
                setPlanEditorErr(null);
                setDraftPlanObj(plan.plan);
                setPlanEditorText(JSON.stringify(plan.plan ?? {}, null, 2));
                pushToast({ kind: "info", text: "Reverted to last saved baseline." });
              }}
            >
              Revert
            </button>

            <button style={styles.btn(busy, "primary")} disabled={busy} onClick={savePlan}>
              Save
            </button>
          </div>
        </div>

        {planEditorErr && (
          <div style={{ marginTop: 10, color: "#991b1b", fontSize: 12 }}>
            JSON error: {planEditorErr}
          </div>
        )}

        {showJsonPlan ? (
          <textarea
            value={planEditorText}
            onChange={(e) => {
              const txt = e.target.value;
              setPlanEditorText(txt);

              const parsed = safeJsonParse(txt);
              if (parsed.ok) {
                setPlanEditorErr(null);
                setDraftPlanObj(parsed.value);
              } else {
                setPlanEditorErr(parsed.error);
              }
            }}
            style={styles.textarea}
          />
        ) : (
          <div style={{ marginTop: 10, ...styles.subtle }}>
            JSON editor hidden. (We can add a friendly form-based baseline editor later.)
          </div>
        )}
      </div>

      {/* INTERVENTIONS */}
      <div style={{ ...styles.card, marginTop: 12 }}>
        <div style={styles.cardTitleRow}>
          <div>
            <h4 style={styles.h4}>Interventions</h4>
            <div style={styles.subtle}>
              Plot twists that change reality: demand drops, cost spikes, deposit delays, refund waves.
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button style={styles.btn(busy)} disabled={busy} onClick={() => bulkSetEnabled(true)}>
              Enable all
            </button>
            <button style={styles.btn(busy)} disabled={busy} onClick={() => bulkSetEnabled(false)}>
              Disable all
            </button>
          </div>
        </div>


        {/* ADD FROM LIBRARY */}
        <div style={styles.dividerTop}>
          <div style={styles.cardTitleRow}>
            <div>
              <div style={{ fontWeight: 800, fontSize: 13 }}>Add intervention</div>
              <div style={styles.subtle}>Pick a template. Tune it after adding.</div>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <input
                placeholder="Search interventions…"
                value={ivSearch}
                disabled={busy}
                onChange={(e) => setIvSearch(e.target.value)}
                style={{ ...styles.input, minWidth: 240 }}
              />
              <select
                value={ivSort}
                disabled={busy}
                onChange={(e) => setIvSort(e.target.value as any)}
                style={{ ...styles.select, width: 210 }}
              >
                <option value="enabled">Sort: enabled</option>
                <option value="start_date">Sort: start date</option>
                <option value="updated">Sort: updated</option>
                <option value="kind">Sort: kind</option>
              </select>
            </div>
          </div>

          <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
            {(templates ?? []).map((t) => (
              <div key={t.kind} style={{ border: "1px solid #e5e7eb", borderRadius: 16, padding: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 13 }}>{t.label}</div>
                    <div style={{ ...styles.subtle, marginTop: 6 }}>{t.description}</div>
                  </div>
                  <div style={{ display: "flex", alignItems: "flex-start" }}>
                    <button style={styles.btn(busy, "primary")} disabled={busy} onClick={() => addInterventionFromTemplate(t)}>
                      + Add
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {!templates?.length && <div style={{ opacity: 0.7 }}>No templates loaded.</div>}
          </div>
        </div>

        {/* EXISTING LIST */}
        {visibleInterventions.length === 0 ? (
          <div style={{ marginTop: 10, opacity: 0.7 }}>
            {interventions.length === 0 ? "No interventions yet." : "No interventions match your search."}
          </div>
        ) : (
          <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
            {visibleInterventions.map((iv) => {
              const draft = ivDraft[iv.id] ?? iv;
              const t = templateByKind.get(iv.kind);
              const dirty = ivDirty(iv.id);

              return (
                <div key={iv.id} style={{ border: "1px solid #e5e7eb", borderRadius: 16, padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
                    <div style={{ minWidth: 260, flex: 1 }}>
                      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                        <input
                          value={draft.name}
                          disabled={busy}
                          onChange={(e) => updateIvField(iv.id, { name: e.target.value })}
                          style={{
                            ...styles.input,
                            fontWeight: 800,
                            fontSize: 13,
                            padding: "8px 10px",
                            minWidth: 260,
                          }}
                        />

                        <span style={styles.pill(draft.enabled ? "#f0fdf4" : "#f9fafb")}>
                          {draft.enabled ? "Enabled" : "Disabled"}
                        </span>
                        <span style={styles.pill("#f9fafb")}>kind: {iv.kind}</span>
                        {dirty && <span style={styles.pill("#fff7ed")}>Unsaved</span>}
                      </div>

                      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                        <label style={{ display: "grid", gap: 6 }}>
                          <span style={styles.subtle}>Start date</span>
                          <input
                            type="date"
                            value={draft.start_date}
                            disabled={busy}
                            onChange={(e) => updateIvField(iv.id, { start_date: e.target.value })}
                            style={styles.input}
                          />
                        </label>

                        <label style={{ display: "grid", gap: 6 }}>
                          <span style={styles.subtle}>Duration (days)</span>
                          <input
                            type="number"
                            value={draft.duration_days ?? ""}
                            disabled={busy}
                            placeholder="(ongoing)"
                            onChange={(e) => {
                              const v = e.target.value;
                              updateIvField(iv.id, { duration_days: v === "" ? null : Number(v) });
                            }}
                            style={styles.input}
                          />
                        </label>

                        <label style={{ display: "grid", gap: 6 }}>
                          <span style={styles.subtle}>Toggle</span>
                          <button
                            style={styles.btn(busy)}
                            disabled={busy}
                            onClick={() => updateIvField(iv.id, { enabled: !draft.enabled })}
                          >
                            {draft.enabled ? "Disable" : "Enable"}
                          </button>
                        </label>
                      </div>

                      {/* PARAMS */}
                      <div style={{ marginTop: 12 }}>
                        <div style={{ fontWeight: 800, fontSize: 12.5 }}>Params</div>
                        <div style={{ ...styles.subtle, marginTop: 4 }}>
                          {t?.description ?? "Tune the parameters for how this intervention behaves."}
                        </div>

                        <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                          {(t?.fields ?? []).map((f) => {
                            const raw = (draft.params ?? {})[f.key];

                            if (f.type === "text") {
                              return (
                                <label key={f.key} style={{ display: "grid", gap: 6 }}>
                                  <span style={styles.subtle}>{f.label}</span>
                                  <input
                                    value={raw ?? ""}
                                    disabled={busy}
                                    onChange={(e) => updateIvParam(iv.id, f.key, e.target.value)}
                                    style={styles.input}
                                  />
                                </label>
                              );
                            }

                            if (f.type === "percent") {
                              const uiVal = pctToUi(raw);
                              return (
                                <label key={f.key} style={{ display: "grid", gap: 6 }}>
                                  <span style={styles.subtle}>{f.label}</span>
                                  <input
                                    type="number"
                                    value={uiVal}
                                    disabled={busy}
                                    min={f.min !== undefined ? f.min * 100 : undefined}
                                    max={f.max !== undefined ? f.max * 100 : undefined}
                                    step={f.step !== undefined ? f.step * 100 : 1}
                                    onChange={(e) => {
                                      const ui = numOr(e.target.value, 0);
                                      const api = pctToApi(ui);
                                      updateIvParam(iv.id, f.key, clamp(api, f.min, f.max));
                                    }}
                                    style={styles.input}
                                  />
                                  <div style={styles.subtle}>
                                    Stored as {(draft.params?.[f.key] ?? 0).toString()} (0..1)
                                  </div>
                                </label>
                              );
                            }

                            // number / days
                            const n = numOr(raw, "");
                            return (
                              <label key={f.key} style={{ display: "grid", gap: 6 }}>
                                <span style={styles.subtle}>{f.label}</span>
                                <input
                                  type="number"
                                  value={n as any}
                                  disabled={busy}
                                  min={f.min}
                                  max={f.max}
                                  step={f.step ?? (f.type === "days" ? 1 : 0.01)}
                                  onChange={(e) => {
                                    const v = Number(e.target.value);
                                    if (!Number.isFinite(v)) return;
                                    updateIvParam(iv.id, f.key, clamp(v, f.min, f.max));
                                  }}
                                  style={styles.input}
                                />
                              </label>
                            );
                          })}
                        </div>

                        {!t?.fields?.length && (
                          <pre
                            style={{
                              marginTop: 10,
                              marginBottom: 0,
                              background: "#f9fafb",
                              padding: 10,
                              borderRadius: 12,
                              overflow: "auto",
                              border: "1px solid #e5e7eb",
                              fontSize: 12,
                            }}
                          >
                            {JSON.stringify(draft.params ?? {}, null, 2)}
                          </pre>
                        )}
                      </div>

                      {iv.updated_at && (
                        <div style={{ marginTop: 10, fontSize: 12, opacity: 0.6 }}>
                          Updated: {new Date(iv.updated_at).toLocaleString()}
                        </div>
                      )}
                    </div>

                    {/* ACTIONS */}
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                      <button style={styles.btn(busy)} disabled={busy} onClick={() => duplicateIntervention(iv)}>
                        Duplicate
                      </button>

                      <button style={styles.btn(busy)} disabled={busy || !dirty} onClick={() => saveIntervention(iv.id)}>
                        Save
                      </button>

                      <button style={styles.btn(busy)} disabled={busy || !dirty} onClick={() => revertIntervention(iv.id)}>
                        Revert
                      </button>

                      <button style={styles.btn(busy, "danger")} disabled={busy} onClick={() => deleteIntervention(iv)}>
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ ...styles.subtle, marginTop: 12 }}>
        {/* RESULTS / TRUTH */}
      <div style={{ ...styles.card, marginTop: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
          <div>
            <h4 style={{ margin: 0 }}>Results</h4>
            <div style={styles.subtle}>What the simulator actually applied (truth markers).</div>
          </div>
        </div>

        {!truth?.length ? (
          <div style={{ marginTop: 10, opacity: 0.7 }}>
            No truth events yet. Run “Generate events” to produce a timeline.
          </div>
        ) : (
          <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
            {truth.slice().reverse().slice(0, 60).map((ev: any, idx: number) => {
              if (ev.type === "shock_window") {
                return (
                  <div key={idx} style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 12, background: "#fff7ed" }}>
                    <div style={{ fontWeight: 700 }}>Shock window</div>
                    <div style={{ marginTop: 6, fontSize: 12, opacity: 0.8 }}>
                      {ev.start_at} → {ev.end_at}
                    </div>
                    {ev.note && <div style={{ marginTop: 6, fontSize: 12, opacity: 0.8 }}>{ev.note}</div>}
                  </div>
                );
              }

              if (ev.type === "interventions_active") {
                return (
                  <div key={idx} style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                      <div style={{ fontWeight: 700 }}>Interventions active</div>
                      <div style={{ fontSize: 12, opacity: 0.75 }}>{ev.date}</div>
                    </div>

                    <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {(ev.active ?? []).map((a: any) => (
                        <span key={a.id ?? a.name} style={styles.pill("#f9fafb")}>
                          {a.name} ({a.kind})
                        </span>
                      ))}
                    </div>

                    <div style={{ marginTop: 10, fontSize: 12, opacity: 0.75 }}>
                      mods: vol×{Number(ev.mods?.volume_mult ?? 1).toFixed(2)} · rev×{Number(ev.mods?.revenue_mult ?? 1).toFixed(2)} ·
                      exp×{Number(ev.mods?.expense_mult ?? 1).toFixed(2)} · delay {ev.mods?.deposit_delay_days ?? 0}d ·
                      delay% {Math.round((Number(ev.mods?.deposit_delay_pct ?? 0) * 100) * 10) / 10} ·
                      refund {ev.mods?.refund_rate == null ? "—" : Math.round(Number(ev.mods.refund_rate) * 1000) / 10 + "%"}
                    </div>
                  </div>
                );
              }

              // fallback
              return (
                <pre key={idx} style={{ margin: 0, background: "#f9fafb", padding: 10, borderRadius: 12, border: "1px solid #e5e7eb", overflow: "auto", fontSize: 12 }}>
                  {JSON.stringify(ev, null, 2)}
                </pre>
              );
            })}
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
