import { useEffect, useState } from "react";
import {
  type Account,
  type AccountCreate,
  type AccountType,
  listAccounts,
  createAccount,
  updateAccount,
  deactivateAccount,
} from "../../api/coa";

const TYPES: AccountType[] = ["asset", "liability", "equity", "revenue", "expense"];

export default function CoaTab({ businessId }: { businessId: string }) {
  const [rows, setRows] = useState<Account[]>([]);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [draft, setDraft] = useState<AccountCreate>({
    code: "",
    name: "",
    type: "expense",
    subtype: "",
    active: true,
  });

  async function load() {
    setLoading(true);
    setErr(null);
    setMsg(null);
    try {
      const a = await listAccounts(businessId, includeInactive);
      setRows(a);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load accounts");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId, includeInactive]);

  return (
    <div style={{ paddingTop: 8 }}>
      <h3 style={{ marginTop: 0 }}>Chart of Accounts</h3>

      {msg && <div style={{ marginBottom: 10 }}>{msg}</div>}
      {err && <div style={{ marginBottom: 10, color: "#b91c1c" }}>Error: {err}</div>}

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button className="closeBtn" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Reload"}
        </button>

        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, opacity: 0.8 }}>
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
          />
          show inactive
        </label>
      </div>

      {/* Create new */}
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, marginTop: 12 }}>
        <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 8 }}>Add account</div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr 1fr 2fr", gap: 10 }}>
          <input
            value={draft.code ?? ""}
            placeholder="code (optional)"
            onChange={(e) => setDraft({ ...draft, code: e.target.value })}
            style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
          />
          <input
            value={draft.name}
            placeholder="name"
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
          />
          <select
            value={draft.type}
            onChange={(e) => setDraft({ ...draft, type: e.target.value as AccountType })}
            style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            value={draft.subtype ?? ""}
            placeholder="subtype (optional)"
            onChange={(e) => setDraft({ ...draft, subtype: e.target.value })}
            style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
          />
        </div>

        <button
          className="closeBtn"
          style={{ marginTop: 10 }}
          onClick={async () => {
            setErr(null);
            setMsg(null);
            try {
              if (!draft.name.trim()) {
                setErr("Name is required");
                return;
              }
              await createAccount(businessId, {
                code: draft.code?.trim() ? draft.code.trim() : undefined,
                name: draft.name.trim(),
                type: draft.type,
                subtype: draft.subtype?.trim() ? draft.subtype.trim() : undefined,
                active: true,
              });
              setDraft({ code: "", name: "", type: "expense", subtype: "", active: true });
              setMsg("Account created.");
              await load();
            } catch (e: any) {
              setErr(e?.message ?? "Create failed");
            }
          }}
        >
          Add
        </button>
      </div>

      {/* List */}
      <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
        {rows.map((a) => (
          <AccountRow
            key={a.id}
            a={a}
            onSave={async (patch) => {
              setErr(null);
              setMsg(null);
              try {
                await updateAccount(businessId, a.id, patch);
                setMsg("Saved.");
                await load();
              } catch (e: any) {
                setErr(e?.message ?? "Save failed");
              }
            }}
            onDeactivate={async () => {
              setErr(null);
              setMsg(null);
              try {
                await deactivateAccount(businessId, a.id);
                setMsg("Deactivated.");
                await load();
              } catch (e: any) {
                setErr(e?.message ?? "Deactivate failed");
              }
            }}
          />
        ))}
      </div>
    </div>
  );
}

function AccountRow({
  a,
  onSave,
  onDeactivate,
}: {
  a: Account;
  onSave: (patch: any) => Promise<void>;
  onDeactivate: () => Promise<void>;
}) {
  const [code, setCode] = useState(a.code ?? "");
  const [name, setName] = useState(a.name);
  const [type, setType] = useState<AccountType>(a.type);
  const [subtype, setSubtype] = useState(a.subtype ?? "");
  const [active, setActive] = useState(a.active);

  useEffect(() => {
    setCode(a.code ?? "");
    setName(a.name);
    setType(a.type);
    setSubtype(a.subtype ?? "");
    setActive(a.active);
  }, [a.id, a.code, a.name, a.type, a.subtype, a.active]);

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, opacity: active ? 1 : 0.6 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr 1fr 2fr", gap: 10 }}>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="code"
          style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="name"
          style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
        />
        <select
          value={type}
          onChange={(e) => setType(e.target.value as AccountType)}
          style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
        >
          {["asset", "liability", "equity", "revenue", "expense"].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          value={subtype}
          onChange={(e) => setSubtype(e.target.value)}
          placeholder="subtype"
          style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
        />
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap", alignItems: "center" }}>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, opacity: 0.8 }}>
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          active
        </label>

        <button
          className="closeBtn"
          onClick={() =>
            onSave({
              code: code.trim() ? code.trim() : null,
              name: name.trim(),
              type,
              subtype: subtype.trim() ? subtype.trim() : null,
              active,
            })
          }
        >
          Save
        </button>

        {active && (
          <button className="closeBtn" onClick={onDeactivate} style={{ opacity: 0.8 }}>
            Deactivate
          </button>
        )}
      </div>
    </div>
  );
}
