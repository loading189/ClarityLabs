import type { Signal } from "../../types";

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
  for (const [d, arr] of byDim.entries()) {
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

  return (
    <div className="signalGridWrap">
      <div className="signalGridHeader">
        <div className="signalGridTitle">Signal Dashboard</div>
        <div className="signalGridHint">Click any light to see “show your work” detail.</div>
      </div>

      <div className="signalGrid">
        {orderedDims.map((dimKey) => {
          const arr = byDim.get(dimKey) ?? [];
          if (arr.length === 0) return null;

          const c = counts(dimKey);
          const label =
            DIMENSIONS.find((d) => d.key === dimKey)?.label ?? formatDimensionLabel(dimKey);

          return (
            <div key={dimKey} className="signalGroup">
              <div className="signalGroupHeader">
                <div className="signalGroupTitle">{label}</div>
                <div className="signalGroupCounts">
                  <span className="chip chip--red">{c.red} red</span>
                  <span className="chip chip--yellow">{c.yellow} yellow</span>
                  <span className="chip chip--green">{c.green} green</span>
                </div>
              </div>

              <div className="signalLights">
                {arr.map((s) => {
                  const active = selectedKey === s.key;
                  return (
                    <button
                      key={s.key}
                      className={[
                        "signalLight",
                        `signalLight--${s.severity ?? "green"}`,
                        active ? "signalLight--active" : "",
                      ].join(" ")}
                      onClick={() => onSelect(s)}
                      title={`${s.title} — ${String(s.severity).toUpperCase()}`}
                      type="button"
                    >
                      <div className="signalLightDot" />
                      <div className="signalLightText">
                        <div className="signalLightTitle">{s.title}</div>
                        <div className="signalLightSub">{s.key}</div>
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
