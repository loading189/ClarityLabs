import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { assertBusinessId } from "../../utils/businessId";
import {
  GenerateOut,
  InterventionTemplate,
  ScenarioCatalog,
  generateSimHistory,
  getInterventionLibrary,
  getScenarioCatalog,
  getSimTruth,
} from "../../api/simulator";
import { useBusinessStatus } from "../../hooks/useBusinessStatus";
import { useSimPlan } from "../../hooks/useSimPlan";
import { useSimInterventions } from "../../hooks/useSimInterventions";
import styles from "./AdminSimulatorPage.module.css";

function todayISO() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function daysAgoISO(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function isMissingError(err: string | null) {
  if (!err) return false;
  const msg = err.toLowerCase();
  return msg.includes("not found") || msg.includes("404");
}

function parseJson(value: string) {
  try {
    return { ok: true as const, value: JSON.parse(value) };
  } catch (e: any) {
    return { ok: false as const, error: e?.message ?? "Invalid JSON" };
  }
}

function parseOptionalNumber(value: string) {
  if (!value) return undefined;
  const num = Number(value);
  return Number.isFinite(num) ? num : undefined;
}

function parseNullableNumber(value: string) {
  if (!value) return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function buildScenarioOptions(catalog: ScenarioCatalog | null) {
  const scenarios = catalog?.scenarios ?? [];
  if (Array.isArray(scenarios) && scenarios.length > 0) return scenarios;
  return [{ id: "restaurant_v1", name: "Restaurant (v1)" }];
}

function extractPlanDefaults(catalog: ScenarioCatalog | null, scenarioId: string) {
  const scenario = catalog?.scenarios?.find((item) => item.id === scenarioId);
  const defaults = scenario?.defaults;
  if (defaults && typeof defaults === "object") {
    const planDefaults = (defaults as Record<string, any>).plan;
    if (planDefaults && typeof planDefaults === "object") return planDefaults;
    return defaults;
  }
  return {};
}

export default function AdminSimulatorPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "AdminSimulatorPage");

  const {
    data: status,
    loading: statusLoading,
    err: statusErr,
    refresh: refreshStatus,
  } = useBusinessStatus(businessId);
  const {
    data: plan,
    loading: planLoading,
    err: planErr,
    refresh: refreshPlan,
    updatePlan,
  } = useSimPlan(businessId);
  const {
    data: interventions,
    loading: interventionsLoading,
    err: interventionsErr,
    create: createIntervention,
    update: updateIntervention,
    remove: removeIntervention,
  } = useSimInterventions(businessId);

  const [catalog, setCatalog] = useState<ScenarioCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogErr, setCatalogErr] = useState<string | null>(null);

  const [truth, setTruth] = useState<{ truth_events: any[] } | null>(null);
  const [truthErr, setTruthErr] = useState<string | null>(null);

  const [library, setLibrary] = useState<InterventionTemplate[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryErr, setLibraryErr] = useState<string | null>(null);

  const [planScenarioId, setPlanScenarioId] = useState("restaurant_v1");
  const [planStoryVersion, setPlanStoryVersion] = useState(1);
  const [planJson, setPlanJson] = useState("{}");
  const [planSaveErr, setPlanSaveErr] = useState<string | null>(null);
  const [planSaving, setPlanSaving] = useState(false);

  const [newKind, setNewKind] = useState("");
  const [newName, setNewName] = useState("");
  const [newStartDate, setNewStartDate] = useState(todayISO());
  const [newDuration, setNewDuration] = useState<string>("");
  const [newParams, setNewParams] = useState<Record<string, any>>({});
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [createLoading, setCreateLoading] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<{
    name: string;
    start_date: string;
    duration_days: string;
    paramsText: string;
  } | null>(null);
  const [editErr, setEditErr] = useState<string | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  const [generateStartDate, setGenerateStartDate] = useState(daysAgoISO(120));
  const [generateDays, setGenerateDays] = useState(120);
  const [generateSeed, setGenerateSeed] = useState(1337);
  const [generateEventsPerDay, setGenerateEventsPerDay] = useState<string>("");
  const [generateEnableShocks, setGenerateEnableShocks] = useState(true);
  const [generateShockDays, setGenerateShockDays] = useState(10);
  const [generateRevenueDropPct, setGenerateRevenueDropPct] = useState(0.3);
  const [generateExpenseSpikePct, setGenerateExpenseSpikePct] = useState(0.5);
  const [generateMode, setGenerateMode] = useState<"append" | "replace_from_start">(
    "replace_from_start"
  );
  const [generateResult, setGenerateResult] = useState<GenerateOut | null>(null);
  const [generateErr, setGenerateErr] = useState<string | null>(null);
  const [generateLoading, setGenerateLoading] = useState(false);

  const scenarioOptions = useMemo(() => buildScenarioOptions(catalog), [catalog]);
  const planMissing = isMissingError(planErr);

  useEffect(() => {
    if (!businessId) return undefined;
    const controller = new AbortController();
    setCatalogLoading(true);
    setCatalogErr(null);
    getScenarioCatalog({ signal: controller.signal })
      .then((res) => setCatalog(res))
      .catch((e: any) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setCatalogErr(e?.message ?? "Failed to load scenario catalog");
      })
      .finally(() => setCatalogLoading(false));
    return () => controller.abort();
  }, [businessId]);

  useEffect(() => {
    if (!businessId) return undefined;
    const controller = new AbortController();
    setLibraryLoading(true);
    setLibraryErr(null);
    getInterventionLibrary({ signal: controller.signal })
      .then((res) => setLibrary(res ?? []))
      .catch((e: any) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setLibraryErr(e?.message ?? "Failed to load intervention library");
      })
      .finally(() => setLibraryLoading(false));
    return () => controller.abort();
  }, [businessId]);

  useEffect(() => {
    if (!businessId) return undefined;
    const controller = new AbortController();
    setTruthErr(null);
    getSimTruth(businessId, { signal: controller.signal })
      .then((res) => setTruth(res))
      .catch((e: any) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setTruthErr(e?.message ?? "Failed to load simulator truth");
      });
    return () => controller.abort();
  }, [businessId]);

  useEffect(() => {
    if (!plan) return;
    setPlanScenarioId(plan.scenario_id || "restaurant_v1");
    setPlanStoryVersion(plan.story_version || 1);
    setPlanJson(JSON.stringify(plan.plan ?? {}, null, 2));
  }, [plan]);

  useEffect(() => {
    if (!planMissing) return;
    const defaults = extractPlanDefaults(catalog, planScenarioId);
    setPlanJson(JSON.stringify(defaults ?? {}, null, 2));
  }, [catalog, planMissing, planScenarioId]);

  useEffect(() => {
    if (!newKind && library.length > 0) {
      setNewKind(library[0].kind);
    }
  }, [library, newKind]);

  const selectedTemplate = useMemo(
    () => library.find((item) => item.kind === newKind) ?? null,
    [library, newKind]
  );

  useEffect(() => {
    if (!selectedTemplate) return;
    const base = { ...selectedTemplate.defaults };
    selectedTemplate.fields.forEach((field) => {
      if (base[field.key] === undefined && field.default !== undefined) {
        base[field.key] = field.default;
      }
    });
    setNewParams(base);
    if (!newName) {
      setNewName(selectedTemplate.label || selectedTemplate.kind);
    }
  }, [selectedTemplate]);

  if (!businessId) {
    return (
      <div className={styles.page}>
        <ErrorState label="Missing or invalid business id." />
      </div>
    );
  }

  const handleSavePlan = async () => {
    setPlanSaveErr(null);
    const parsed = parseJson(planJson);
    if (!parsed.ok) {
      setPlanSaveErr(parsed.error);
      return;
    }

    try {
      setPlanSaving(true);
      await updatePlan({
        scenario_id: planScenarioId || "restaurant_v1",
        story_version: planStoryVersion || 1,
        plan: parsed.value ?? {},
      });
      await refreshPlan();
    } catch (e: any) {
      setPlanSaveErr(e?.message ?? "Failed to save plan");
    } finally {
      setPlanSaving(false);
    }
  };

  const handleCreatePlan = async () => {
    const defaults = extractPlanDefaults(catalog, planScenarioId);
    const nextPlan = defaults ?? {};
    setPlanJson(JSON.stringify(nextPlan, null, 2));
    setPlanSaveErr(null);
    try {
      setPlanSaving(true);
      await updatePlan({
        scenario_id: planScenarioId || "restaurant_v1",
        story_version: planStoryVersion || 1,
        plan: nextPlan,
      });
      await refreshPlan();
    } catch (e: any) {
      setPlanSaveErr(e?.message ?? "Failed to create plan");
    } finally {
      setPlanSaving(false);
    }
  };

  const handleCreateIntervention = async () => {
    if (!newKind) return;
    setCreateErr(null);
    try {
      setCreateLoading(true);
      const durationValue = parseOptionalNumber(newDuration);
      await createIntervention({
        kind: newKind,
        name: newName || newKind,
        start_date: newStartDate,
        duration_days: durationValue,
        params: newParams,
        enabled: true,
      });
      setNewName("");
      setNewDuration("");
      setCreateErr(null);
    } catch (e: any) {
      setCreateErr(e?.message ?? "Failed to create intervention");
    } finally {
      setCreateLoading(false);
    }
  };

  const handleEditStart = (id: string) => {
    const match = interventions?.find((item) => item.id === id);
    if (!match) return;
    setEditingId(id);
    setEditDraft({
      name: match.name,
      start_date: match.start_date,
      duration_days: match.duration_days === null ? "" : String(match.duration_days),
      paramsText: JSON.stringify(match.params ?? {}, null, 2),
    });
  };

  const handleEditSave = async () => {
    if (!editingId || !editDraft) return;
    setEditErr(null);
    const parsed = parseJson(editDraft.paramsText);
    if (!parsed.ok) {
      setEditErr(parsed.error);
      return;
    }
    try {
      setEditLoading(true);
      const durationValue = parseNullableNumber(editDraft.duration_days);
      await updateIntervention(editingId, {
        name: editDraft.name,
        start_date: editDraft.start_date,
        duration_days: durationValue,
        params: parsed.value,
      });
      setEditingId(null);
      setEditDraft(null);
    } catch (e: any) {
      setEditErr(e?.message ?? "Failed to update intervention");
    } finally {
      setEditLoading(false);
    }
  };

  const handleGenerate = async () => {
    setGenerateErr(null);
    try {
      setGenerateLoading(true);
      const payload = {
        start_date: generateStartDate,
        days: generateDays,
        seed: generateSeed,
        mode: generateMode,
        enable_shocks: generateEnableShocks,
        shock_days: generateShockDays,
        revenue_drop_pct: generateRevenueDropPct,
        expense_spike_pct: generateExpenseSpikePct,
        events_per_day: parseOptionalNumber(generateEventsPerDay),
      };
      const result = await generateSimHistory(businessId, payload);
      setGenerateResult(result);
      window.dispatchEvent(new Event("clarity:data-updated"));
      refreshStatus();
    } catch (e: any) {
      setGenerateErr(e?.message ?? "Failed to generate history");
    } finally {
      setGenerateLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title="Simulator Control Center"
        subtitle="Manage scenario plans, interventions, and history generation for the active business."
      />

      <section className={styles.section}>
        <h3>Business Status</h3>
        {statusLoading && <LoadingState label="Loading business status…" />}
        {statusErr && <ErrorState label={statusErr} />}
        {status && (
          <div className={styles.statusCard}>
            <div>
              <div className={styles.statusLabel}>Accounts</div>
              <div className={styles.statusValue}>{status.accounts_count}</div>
            </div>
            <div>
              <div className={styles.statusLabel}>Events</div>
              <div className={styles.statusValue}>{status.events_count}</div>
            </div>
            <div>
              <div className={styles.statusLabel}>Simulator Enabled</div>
              <div className={styles.statusValue}>{status.sim_enabled ? "Yes" : "No"}</div>
            </div>
            <div>
              <div className={styles.statusLabel}>Ready</div>
              <div className={styles.statusValue}>{status.ready ? "Ready" : "Not ready"}</div>
            </div>
            <div>
              <div className={styles.statusLabel}>Truth Events</div>
              <div className={styles.statusValue}>{truth?.truth_events?.length ?? 0}</div>
            </div>
          </div>
        )}
        {truthErr && <div className={styles.inlineError}>Truth: {truthErr}</div>}
      </section>

      <section className={styles.section}>
        <h3>Scenario + Plan Editor</h3>
        {catalogLoading && <LoadingState label="Loading scenario catalog…" />}
        {catalogErr && <ErrorState label={catalogErr} />}
        {planLoading && <LoadingState label="Loading simulator plan…" />}
        {planErr && !planMissing && <ErrorState label={planErr} />}
        {planMissing && (
          <div className={styles.notice}>
            No plan found yet. Create a plan to enable simulator history generation.
          </div>
        )}

        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>Scenario</span>
            <select
              value={planScenarioId}
              onChange={(e) => setPlanScenarioId(e.target.value)}
              className={styles.input}
            >
              {scenarioOptions.map((scenario) => (
                <option key={scenario.id} value={scenario.id}>
                  {scenario.name ?? scenario.id}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span>Story version</span>
            <input
              type="number"
              min={1}
              value={planStoryVersion}
              onChange={(e) => setPlanStoryVersion(Number(e.target.value))}
              className={styles.input}
            />
          </label>
        </div>

        <label className={styles.field}>
          <span>Plan JSON</span>
          <textarea
            rows={12}
            value={planJson}
            onChange={(e) => setPlanJson(e.target.value)}
            className={styles.textarea}
          />
        </label>

        {planSaveErr && <div className={styles.inlineError}>{planSaveErr}</div>}
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={planMissing ? handleCreatePlan : handleSavePlan}
            disabled={planSaving}
          >
            {planSaving ? "Saving…" : planMissing ? "Create Plan" : "Save Plan"}
          </button>
          <button type="button" className={styles.ghostButton} onClick={() => void refreshPlan()}>
            Refresh
          </button>
        </div>
      </section>

      <section className={styles.section}>
        <h3>Intervention Library + Add Intervention</h3>
        {libraryLoading && <LoadingState label="Loading intervention library…" />}
        {libraryErr && <ErrorState label={libraryErr} />}
        {library.length > 0 && (
          <div className={styles.libraryGrid}>
            {library.map((template) => (
              <div key={template.kind} className={styles.libraryCard}>
                <div className={styles.libraryTitle}>{template.label}</div>
                <div className={styles.libraryKind}>{template.kind}</div>
                <p className={styles.libraryDescription}>{template.description}</p>
              </div>
            ))}
          </div>
        )}

        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>Template</span>
            <select
              value={newKind}
              onChange={(e) => setNewKind(e.target.value)}
              className={styles.input}
            >
              {library.map((template) => (
                <option key={template.kind} value={template.kind}>
                  {template.label} ({template.kind})
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span>Name</span>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span>Start date</span>
            <input
              type="date"
              value={newStartDate}
              onChange={(e) => setNewStartDate(e.target.value)}
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span>Duration (days)</span>
            <input
              type="number"
              min={1}
              value={newDuration}
              onChange={(e) => setNewDuration(e.target.value)}
              className={styles.input}
            />
          </label>
        </div>

        {selectedTemplate && selectedTemplate.fields.length > 0 && (
          <div className={styles.formGrid}>
            {selectedTemplate.fields.map((field) => (
              <label key={field.key} className={styles.field}>
                <span>{field.label}</span>
                <input
                  type={field.type === "text" ? "text" : "number"}
                  min={field.min}
                  max={field.max}
                  step={field.step}
                  value={newParams[field.key] ?? ""}
                  onChange={(e) =>
                    setNewParams((prev) => ({
                      ...prev,
                      [field.key]:
                        field.type === "text" ? e.target.value : Number(e.target.value),
                    }))
                  }
                  className={styles.input}
                />
              </label>
            ))}
          </div>
        )}

        {createErr && <div className={styles.inlineError}>{createErr}</div>}
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={handleCreateIntervention}
            disabled={createLoading || !newKind}
          >
            {createLoading ? "Creating…" : "Create Intervention"}
          </button>
        </div>
      </section>

      <section className={styles.section}>
        <h3>Current Interventions</h3>
        {interventionsLoading && <LoadingState label="Loading interventions…" />}
        {interventionsErr && <ErrorState label={interventionsErr} />}
        {interventions && interventions.length === 0 && (
          <div className={styles.notice}>No interventions yet. Add one above.</div>
        )}
        {interventions && interventions.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Kind</th>
                  <th>Start</th>
                  <th>Duration</th>
                  <th>Enabled</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {interventions.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {editingId === item.id && editDraft ? (
                        <input
                          className={styles.input}
                          value={editDraft.name}
                          onChange={(e) =>
                            setEditDraft({ ...editDraft, name: e.target.value })
                          }
                        />
                      ) : (
                        item.name
                      )}
                    </td>
                    <td>{item.kind}</td>
                    <td>
                      {editingId === item.id && editDraft ? (
                        <input
                          type="date"
                          className={styles.input}
                          value={editDraft.start_date}
                          onChange={(e) =>
                            setEditDraft({ ...editDraft, start_date: e.target.value })
                          }
                        />
                      ) : (
                        item.start_date
                      )}
                    </td>
                    <td>
                      {editingId === item.id && editDraft ? (
                        <input
                          type="number"
                          min={1}
                          className={styles.input}
                          value={editDraft.duration_days}
                          onChange={(e) =>
                            setEditDraft({
                              ...editDraft,
                              duration_days: e.target.value,
                            })
                          }
                        />
                      ) : item.duration_days !== null ? (
                        item.duration_days
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className={styles.toggleButton}
                        onClick={() =>
                          void updateIntervention(item.id, { enabled: !item.enabled })
                        }
                      >
                        {item.enabled ? "On" : "Off"}
                      </button>
                    </td>
                    <td>
                      {editingId === item.id ? (
                        <div className={styles.rowActions}>
                          <button
                            type="button"
                            className={styles.primaryButton}
                            onClick={handleEditSave}
                            disabled={editLoading}
                          >
                            {editLoading ? "Saving…" : "Save"}
                          </button>
                          <button
                            type="button"
                            className={styles.ghostButton}
                            onClick={() => {
                              setEditingId(null);
                              setEditDraft(null);
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className={styles.rowActions}>
                          <button
                            type="button"
                            className={styles.ghostButton}
                            onClick={() => handleEditStart(item.id)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className={styles.dangerButton}
                            onClick={() => void removeIntervention(item.id)}
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {editingId && editDraft && (
          <div className={styles.editorPanel}>
            <div className={styles.editorTitle}>Edit params JSON</div>
            <textarea
              rows={6}
              value={editDraft.paramsText}
              onChange={(e) =>
                setEditDraft({ ...editDraft, paramsText: e.target.value })
              }
              className={styles.textarea}
            />
            {editErr && <div className={styles.inlineError}>{editErr}</div>}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <h3>Generate History</h3>
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>Start date</span>
            <input
              type="date"
              value={generateStartDate}
              onChange={(e) => setGenerateStartDate(e.target.value)}
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span>Days</span>
            <input
              type="number"
              min={1}
              value={generateDays}
              onChange={(e) => setGenerateDays(Number(e.target.value))}
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span>Seed</span>
            <input
              type="number"
              value={generateSeed}
              onChange={(e) => setGenerateSeed(Number(e.target.value))}
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span>Events per day (optional)</span>
            <input
              type="number"
              min={1}
              value={generateEventsPerDay}
              onChange={(e) => setGenerateEventsPerDay(e.target.value)}
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span>Mode</span>
            <select
              value={generateMode}
              onChange={(e) =>
                setGenerateMode(e.target.value as "append" | "replace_from_start")
              }
              className={styles.input}
            >
              <option value="replace_from_start">Replace from start</option>
              <option value="append">Append</option>
            </select>
          </label>
        </div>

        <div className={styles.formGrid}>
          <label className={styles.fieldInline}>
            <input
              type="checkbox"
              checked={generateEnableShocks}
              onChange={(e) => setGenerateEnableShocks(e.target.checked)}
            />
            <span>Enable shocks</span>
          </label>
          <label className={styles.field}>
            <span>Shock days</span>
            <input
              type="number"
              min={1}
              value={generateShockDays}
              onChange={(e) => setGenerateShockDays(Number(e.target.value))}
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span>Revenue drop %</span>
            <input
              type="number"
              step={0.01}
              min={0}
              max={1}
              value={generateRevenueDropPct}
              onChange={(e) => setGenerateRevenueDropPct(Number(e.target.value))}
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span>Expense spike %</span>
            <input
              type="number"
              step={0.01}
              min={0}
              max={5}
              value={generateExpenseSpikePct}
              onChange={(e) => setGenerateExpenseSpikePct(Number(e.target.value))}
              className={styles.input}
            />
          </label>
        </div>

        {generateErr && <div className={styles.inlineError}>{generateErr}</div>}
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={handleGenerate}
            disabled={generateLoading}
          >
            {generateLoading ? "Generating…" : "Generate History"}
          </button>
        </div>

        {generateResult && (
          <div className={styles.resultCard}>
            <div>
              <strong>Status:</strong> {generateResult.status}
            </div>
            <div>
              <strong>Inserted:</strong> {generateResult.inserted}
            </div>
            <div>
              <strong>Deleted:</strong> {generateResult.deleted}
            </div>
            {generateResult.shock_window && (
              <div>
                <strong>Shock window:</strong> {generateResult.shock_window.start} →{" "}
                {generateResult.shock_window.end}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
