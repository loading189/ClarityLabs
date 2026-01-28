import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getCategories,
  getTxnsToCategorize,
  saveCategorization,
  labelVendor,
  type CategoryOut,
  type NormalizedTxn,
} from "../../api/categorize";

export default function CategorizeTab({ businessId }: { businessId: string }) {
  const [txns, setTxns] = useState<NormalizedTxn[]>([]);
  const [cats, setCats] = useState<CategoryOut[]>([]);
  const [selectedTxn, setSelectedTxn] = useState<NormalizedTxn | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>("");

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // Prevent stale-load races when businessId changes quickly
  const loadSeq = useRef(0);

  const catsById = useMemo(() => {
    const m = new Map<string, CategoryOut>();
    for (const c of cats) m.set(c.id, c);
    return m;
  }, [cats]);

  const pickBestCategoryId = useCallback(
    (txn: NormalizedTxn | null, categories: CategoryOut[]): string => {
      if (!categories.length) return "";
      const suggested = (txn?.suggested_category_id ?? "") as string;
      if (suggested && categories.some((c) => c.id === suggested)) return suggested;
      return categories[0].id;
    },
    []
  );

  // Suggestion-derived UI fields (guarded)
  const suggestedCategoryId = useMemo(
    () => (selectedTxn?.suggested_category_id ?? "") as string,
    [selectedTxn]
  );

  const suggestedName = useMemo(() => {
    return (
      selectedTxn?.suggested_category_name ??
      selectedTxn?.suggested_system_key ??
      "uncategorized"
    );
  }, [selectedTxn]);

  const suggestedPct = useMemo(() => {
    const c = Number(selectedTxn?.confidence ?? 0);
    return Math.max(0, Math.min(100, Math.round(c * 100)));
  }, [selectedTxn]);

  const suggestedIdIsValid = useMemo(() => {
    return !!suggestedCategoryId && catsById.has(suggestedCategoryId);
  }, [suggestedCategoryId, catsById]);

  const load = useCallback(async () => {
    if (!businessId) return;

    const seq = ++loadSeq.current;

    setLoading(true);
    setErr(null);
    setMsg(null);

    try {
      const [t, c] = await Promise.all([
        getTxnsToCategorize(businessId, 50),
        getCategories(businessId),
      ]);

      // If a newer load started, ignore this result
      if (seq !== loadSeq.current) return;

      setTxns(t);
      setCats(c);

      const firstTxn = t[0] ?? null;
      setSelectedTxn(firstTxn);
      setSelectedCategoryId(pickBestCategoryId(firstTxn, c));
    } catch (e: any) {
      if (seq !== loadSeq.current) return;
      setErr(e?.message ?? "Failed to load categorization");
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [businessId, pickBestCategoryId]);

  const pickTxn = useCallback(
    (t: NormalizedTxn) => {
      setSelectedTxn(t);
      setSelectedCategoryId(pickBestCategoryId(t, cats));
      setMsg(null);
      setErr(null);
    },
    [cats, pickBestCategoryId]
  );

  const doSave = useCallback(
    async (categoryId: string, source: "manual" | "rule" | "ml") => {
      if (!selectedTxn) return;

      setErr(null);
      setMsg(null);

      try {
        const res: any = await saveCategorization(businessId, {
          source_event_id: selectedTxn.source_event_id,
          category_id: categoryId,
          source,
          confidence: source === "manual" ? 1.0 : Number(selectedTxn.confidence ?? 0.75),
        });

        setMsg(
          res?.learned
            ? `Saved. Learned vendor → ${res.learned_system_key ?? ""}. Reloading…`
            : "Saved. Reloading…"
        );

        await load(); // ✅ ensures next txn shows updated suggestions
      } catch (e: any) {
        setErr(e?.message ?? "Save failed");
      }
    },
    [businessId, selectedTxn, load]
  );

  const doAlwaysVendor = useCallback(
  async (systemKey?: string | null) => {
    if (!selectedTxn) return;

    const sk = (systemKey ?? "").trim().toLowerCase();
    if (!sk || sk === "uncategorized") {
      setErr("No usable system category to learn for this vendor.");
      return;
    }

    setErr(null);
    setMsg(null);

    try {
      await labelVendor(businessId, {
        source_event_id: selectedTxn.source_event_id,
        system_key: sk,
        canonical_name: selectedTxn.description,
        confidence: Number(selectedTxn.confidence ?? 0.92),
      });

      setMsg(`Learned vendor → ${sk}. Reloading suggestions…`);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "Failed to label vendor");
    }
  },
  [businessId, selectedTxn, load]
);


  // When categories arrive/refresh, ensure selection is valid.
  useEffect(() => {
    if (!cats.length) {
      setSelectedCategoryId("");
      return;
    }

    if (!selectedCategoryId || !catsById.has(selectedCategoryId)) {
      setSelectedCategoryId(pickBestCategoryId(selectedTxn, cats));
    }
  }, [cats, catsById, pickBestCategoryId, selectedCategoryId, selectedTxn]);

  // On business change, reload
  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <div style={{ paddingTop: 8 }}>Loading…</div>;
  if (err) return <div style={{ paddingTop: 8, color: "#b91c1c" }}>Error: {err}</div>;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: 12 }}>
      {/* LEFT: txns */}
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>To categorize</h3>
          <button className="closeBtn" onClick={load}>
            Reload
          </button>
        </div>

        {txns.length === 0 ? (
          <div style={{ marginTop: 10, opacity: 0.7 }}>No uncategorized transactions.</div>
        ) : (
          <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
            {txns.map((t) => (
              <button
                key={t.source_event_id}
                className="closeBtn"
                onClick={() => pickTxn(t)}
                style={{
                  textAlign: "left",
                  opacity: selectedTxn?.source_event_id === t.source_event_id ? 1 : 0.75,
                  border: "1px solid #e5e7eb",
                  borderRadius: 12,
                  padding: 10,
                }}
              >
                <div style={{ fontSize: 13 }}>{t.description}</div>
                <div style={{ fontSize: 12, opacity: 0.7 }}>
                  {new Date(t.occurred_at).toLocaleString()} • {t.account} • {t.direction} •{" "}
                  {t.amount}
                </div>

                {!!t.suggested_system_key && (
                  <div style={{ fontSize: 12, opacity: 0.7, marginTop: 6 }}>
                    Suggestion:{" "}
                    <strong>{t.suggested_category_name ?? t.suggested_system_key}</strong> •{" "}
                    {Math.round(Number(t.confidence ?? 0) * 100)}%
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* RIGHT: assign */}
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12 }}>
        <h3 style={{ marginTop: 0 }}>Assign category</h3>

        {msg && <div style={{ marginBottom: 10, fontSize: 12, opacity: 0.9 }}>{msg}</div>}
        {err && <div style={{ marginBottom: 10, color: "#b91c1c" }}>Error: {err}</div>}

        {!selectedTxn ? (
          <div style={{ opacity: 0.7 }}>Select a transaction.</div>
        ) : (
          <>
            <div style={{ fontSize: 13, marginBottom: 6 }}>{selectedTxn.description}</div>
            <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 12 }}>
              {selectedTxn.direction} • {selectedTxn.amount} • hint: {selectedTxn.category_hint}
            </div>

            {/* Suggestion box */}
            <div
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 12,
                padding: 10,
                marginBottom: 12,
              }}
            >
              <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>Suggestion</div>

              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <strong style={{ fontSize: 13 }}>{suggestedName}</strong>
                <span style={{ fontSize: 12, opacity: 0.7 }}>
                  {suggestedPct}% • {selectedTxn.suggestion_source ?? "rule"}
                </span>
              </div>

              <div style={{ fontSize: 12, opacity: 0.7, marginTop: 6 }}>
                {selectedTxn.reason ?? "—"}
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                <button
                  className="closeBtn"
                  disabled={!suggestedIdIsValid}
                  onClick={() => {
                    if (!suggestedIdIsValid) return;
                    setSelectedCategoryId(suggestedCategoryId);
                    setMsg("Suggestion applied (selected).");
                  }}
                >
                  Apply suggestion
                </button>

                <button
                  className="closeBtn"
                  disabled={
                    !selectedTxn.suggested_system_key ||
                    selectedTxn.suggested_system_key === "uncategorized"
                  }
                  onClick={() => doAlwaysVendor(selectedTxn.suggested_system_key)}
                >
                  Always use this for this vendor
                </button>
              </div>
            </div>

            {/* Manual selection */}
            <div style={{ display: "grid", gap: 8 }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span style={{ fontSize: 12, opacity: 0.8 }}>Category</span>

                <select
                  value={selectedCategoryId}
                  onChange={(e) => setSelectedCategoryId(e.target.value)}
                  disabled={!cats.length}
                  style={{ padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}
                >
                  {!cats.length ? (
                    <option value="">No categories</option>
                  ) : (
                    cats.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} — {c.account_code ? `${c.account_code} ` : ""}
                        {c.account_name}
                      </option>
                    ))
                  )}
                </select>
              </label>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  className="closeBtn"
                  disabled={!selectedCategoryId}
                  onClick={() => doSave(selectedCategoryId, "manual")}
                >
                  Save categorization
                </button>

                <button
                  className="closeBtn"
                  disabled={!suggestedIdIsValid}
                  onClick={() => doSave(suggestedCategoryId, "rule")}
                  style={{ opacity: suggestedIdIsValid ? 1 : 0.6 }}
                >
                  Save using suggestion
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
