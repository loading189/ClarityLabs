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
import styles from "./CoaTab.module.css";

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
    <div className={styles.container}>
      <h3 className={styles.title}>Chart of Accounts</h3>

      {msg && <div className={styles.message}>{msg}</div>}
      {err && <div className={styles.error}>Error: {err}</div>}

      <div className={styles.controls}>
        <button className={styles.button} onClick={load} disabled={loading} type="button">
          {loading ? "Loading…" : "Reload"}
        </button>

        <label className={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
          />
          show inactive
        </label>
      </div>

      {/* Create new */}
      <div className={styles.panel}>
        <div className={styles.panelTitle}>Add account</div>

        <div className={styles.formGrid}>
          <input
            value={draft.code ?? ""}
            placeholder="code (optional)"
            onChange={(e) => setDraft({ ...draft, code: e.target.value })}
            className={styles.input}
          />
          <input
            value={draft.name}
            placeholder="name"
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            className={styles.input}
          />
          <select
            value={draft.type}
            onChange={(e) => setDraft({ ...draft, type: e.target.value as AccountType })}
            className={styles.select}
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
            className={styles.input}
          />
        </div>

        <button
          className={styles.button}
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
          type="button"
        >
          Add
        </button>
      </div>

      {/* List */}
      <div className={styles.list}>
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
    <div className={`${styles.accountRow} ${active ? "" : styles.accountRowInactive}`}>
      <div className={styles.formGrid}>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="code"
          className={styles.input}
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="name"
          className={styles.input}
        />
        <select
          value={type}
          onChange={(e) => setType(e.target.value as AccountType)}
          className={styles.select}
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
          className={styles.input}
        />
      </div>

      <div className={styles.rowActions}>
        <label className={styles.checkboxLabel}>
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          active
        </label>

        <button
          className={styles.button}
          onClick={() =>
            onSave({
              code: code.trim() ? code.trim() : null,
              name: name.trim(),
              type,
              subtype: subtype.trim() ? subtype.trim() : null,
              active,
            })
          }
          type="button"
        >
          Save
        </button>

        {active && (
          <button className={`${styles.button} ${styles.deactivateButton}`} onClick={onDeactivate} type="button">
            Deactivate
          </button>
        )}
      </div>
    </div>
  );
}
