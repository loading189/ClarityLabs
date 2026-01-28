import type { Signal } from "../../types";
import styles from "../../features/signals/HealthTab.module.css";

type Props = {
  signals: Signal[];
  selectedKey?: string | null;
  onSelect: (sig: Signal) => void;
};

const DIMENSIONS: Array<{ key: string; label: string }> = [
  { key: "liquidity", label: "Liquidity" },
  { key: "stability", label: "Stability" },
  { key: "revenue", label: "Revenue" },
  { key: "spend", label: "Spend" },
  { key: "discipline", label: "Discipline" },
  { key: "ops", label: "Ops" },
];

function sevRank(sev?: string) {
  if (sev === "red") return 3;
  if (sev === "yellow") return 2;
  return 1;
}

function formatDimensionLabel(dim?: string) {
  if (!dim) return "Other";
  return dim.charAt(0).toUpperCase() + dim.slice(1);
}

export default function SignalGrid({ signals, selectedKey, onSelect }: Props) {
  // Group by dimension, but keep unknown dimensions visible
  const byDim = new Map<string, Signal[]>();
  for (const s of signals) {
    const d = (s as any).dimension ?? "other";
    if (!byDim.has(d)) byDim.set(d, []);
    byDim.get(d)!.push(s);
  }

  // Sort signals within dimension: severity desc, priority desc, key asc
  for (const arr of byDim.values()) {
    arr.sort((a, b) => {
      const r = sevRank(b.severity) - sevRank(a.severity);
      if (r !== 0) return r;
      const p = (b.priority ?? 0) - (a.priority ?? 0);
      if (p !== 0) return p;
      return String(a.key).localeCompare(String(b.key));
    });
  }

  // Choose a display order: known dims first, then any extras
  const orderedDims = [
    ...DIMENSIONS.map((x) => x.key),
    ...Array.from(byDim.keys()).filter((k) => !DIMENSIONS.some((d) => d.key === k)),
  ];

  const counts = (dimKey: string) => {
    const arr = byDim.get(dimKey) ?? [];
    const red = arr.filter((s) => s.severity === "red").length;
    const yellow = arr.filter((s) => s.severity === "yellow").length;
    const green = arr.filter((s) => s.severity === "green").length;
    return { red, yellow, green, total: arr.length };
  };

  const severityClass = (sev?: string) => {
    if (sev === "red") return styles.signalLightRed;
    if (sev === "yellow") return styles.signalLightYellow;
    return styles.signalLightGreen;
  };

  return (
    <div className={styles.signalGridWrap}>
      <div className={styles.signalGridHeader}>
        <div className={styles.signalGridTitle}>Signals overview</div>
        <div className={styles.signalGridHint}>Click any signal to see supporting detail.</div>
      </div>

      <div className={styles.signalGrid}>
        {orderedDims.map((dimKey) => {
          const arr = byDim.get(dimKey) ?? [];
          if (arr.length === 0) return null;

          const c = counts(dimKey);
          const label =
            DIMENSIONS.find((d) => d.key === dimKey)?.label ?? formatDimensionLabel(dimKey);

          return (
            <div key={dimKey} className={styles.signalGroup}>
              <div className={styles.signalGroupHeader}>
                <div className={styles.signalGroupTitle}>{label}</div>
                <div className={styles.signalGroupCounts}>
                  <span className={`${styles.chip} ${styles.chipRed}`}>{c.red} red</span>
                  <span className={`${styles.chip} ${styles.chipYellow}`}>{c.yellow} yellow</span>
                  <span className={`${styles.chip} ${styles.chipGreen}`}>{c.green} green</span>
                </div>
              </div>

              <div className={styles.signalLights}>
                {arr.map((s) => {
                  const active = selectedKey === s.key;
                  return (
                    <button
                      key={s.key}
                      className={[
                        styles.signalLight,
                        severityClass(s.severity),
                        active ? styles.signalLightActive : "",
                      ].join(" ")}
                      onClick={() => onSelect(s)}
                      title={`${s.title} — ${String(s.severity).toUpperCase()}`}
                      type="button"
                    >
                      <div className={styles.signalLightDot} />
                      <div className={styles.signalLightText}>
                        <div className={styles.signalLightTitle}>{s.title}</div>
                        <div className={styles.signalLightSub}>{s.key}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
