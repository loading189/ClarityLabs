import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { bootstrapBusiness, createOrg } from "../../api/onboarding";
import { generateSimHistory } from "../../api/simulator";
import { useAppState } from "../state/appState";

type OrgOut = {
  id: string;
  name: string;
};

type BusinessOut = {
  id: string;
  name: string;
  org_id: string;
};

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

export default function OnboardingWizardPage() {
  const navigate = useNavigate();
  const { setActiveBusinessId, bumpDataVersion } = useAppState();

  const [orgName, setOrgName] = useState("Clarity Demo Org");
  const [bizName, setBizName] = useState("Demo Business");
  const [industry, setIndustry] = useState("Service");

  const [org, setOrg] = useState<OrgOut | null>(null);
  const [biz, setBiz] = useState<BusinessOut | null>(null);

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const canCreateOrg = !busy && !org;
  const canBootstrap = !busy && !!org && !biz;
  const canGenerate = !busy && !!biz;

  const stepStatus = useMemo(
    () => ({
      org: org ? "Complete" : "Pending",
      business: biz ? "Complete" : "Pending",
      history: done ? "Complete" : "Pending",
    }),
    [biz, done, org]
  );

  const handleCreateOrg = async () => {
    setErr(null);
    setDone(null);
    setBusy(true);
    try {
      const created = await createOrg({ name: orgName });
      setOrg({ id: created.id, name: created.name });
    } catch (e: any) {
      setErr(e?.message ?? "Failed to create org");
    } finally {
      setBusy(false);
    }
  };

  const handleBootstrapBusiness = async () => {
    if (!org) return;
    setErr(null);
    setDone(null);
    setBusy(true);
    try {
      const result = await bootstrapBusiness({
        org_id: org.id,
        name: bizName,
        industry,
      });
      setBiz({ id: result.business.id, name: result.business.name, org_id: result.business.org_id });
      setActiveBusinessId(result.business.id);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to bootstrap business");
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateHistory = async () => {
    if (!biz) return;
    setErr(null);
    setDone(null);
    setBusy(true);
    try {
      await generateSimHistory(biz.id, {
        start_date: daysAgoISO(120),
        days: 120,
        seed: 1337,
        mode: "replace_from_start",
      });
      window.dispatchEvent(new Event("clarity:data-updated"));
      bumpDataVersion();
      setDone("History generated. Redirecting to dashboard...");
      navigate(`/app/${biz.id}/dashboard`, { replace: true });
    } catch (e: any) {
      setErr(e?.message ?? "Failed to generate history");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 880, margin: "0 auto" }}>
      <h1 style={{ marginTop: 0 }}>Onboarding Wizard</h1>
      <p style={{ opacity: 0.75 }}>
        Create an org, bootstrap a business, and generate history to populate the dashboard.
      </p>

      {err && <div style={{ color: "crimson", marginBottom: 12 }}>Error: {err}</div>}
      {done && <div style={{ color: "seagreen", marginBottom: 12 }}>{done}</div>}

      <div style={{ display: "grid", gap: 16 }}>
        <section style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Step A: Create Org</h2>
          <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 8 }}>
            Status: {stepStatus.org}
          </div>
          <label style={{ display: "block", fontSize: 12, opacity: 0.8 }}>Org name</label>
          <input
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #d1d5db" }}
          />
          <button
            type="button"
            disabled={!canCreateOrg}
            onClick={handleCreateOrg}
            style={{ marginTop: 12 }}
          >
            {busy && !org ? "Working…" : "Create org"}
          </button>
          {org && (
            <div style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>
              Created org {org.name} ({org.id})
            </div>
          )}
        </section>

        <section style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Step B: Bootstrap Business</h2>
          <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 8 }}>
            Status: {stepStatus.business}
          </div>
          <label style={{ display: "block", fontSize: 12, opacity: 0.8 }}>Business name</label>
          <input
            value={bizName}
            onChange={(e) => setBizName(e.target.value)}
            style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #d1d5db" }}
          />
          <label style={{ display: "block", fontSize: 12, opacity: 0.8, marginTop: 8 }}>
            Industry
          </label>
          <input
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #d1d5db" }}
          />
          <button
            type="button"
            disabled={!canBootstrap}
            onClick={handleBootstrapBusiness}
            style={{ marginTop: 12 }}
          >
            {busy && !biz ? "Working…" : "Bootstrap business"}
          </button>
          {biz && (
            <div style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>
              Created business {biz.name} ({biz.id})
            </div>
          )}
        </section>

        <section style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Step C: Generate History</h2>
          <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 8 }}>
            Status: {stepStatus.history}
          </div>
          <p style={{ fontSize: 13, opacity: 0.75, marginTop: 0 }}>
            This will generate ~120 days of simulated ledger history for the new business.
          </p>
          <button type="button" disabled={!canGenerate} onClick={handleGenerateHistory}>
            {busy && !done ? "Working…" : "Generate history"}
          </button>
          {biz && (
            <div style={{ marginTop: 8, fontSize: 12, opacity: 0.7 }}>
              Target business: {biz.name} ({biz.id})
            </div>
          )}
        </section>
      </div>

      <div style={{ marginTop: 16, fontSize: 12, opacity: 0.7 }}>
        Default date range: {daysAgoISO(30)} → {todayISO()}
      </div>
    </div>
  );
}
