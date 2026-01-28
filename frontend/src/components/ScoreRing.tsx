import styles from "./ScoreRing.module.css";

type Props = {
  value: number;          // 0..100
  label?: string;         // e.g. "Stable"
  size?: number;          // px
  stroke?: number;        // px
};

function clamp(n: number, lo = 0, hi = 100) {
  return Math.max(lo, Math.min(hi, n));
}

export default function ScoreRing({
  value,
  label = "Health",
  size = 120,
  stroke = 12,
}: Props) {
  const v = clamp(value);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (v / 100) * c;

  // Optional: simple label mapping
  const status =
    v >= 80 ? "Strong" : v >= 60 ? "Stable" : v >= 40 ? "Watch" : "Critical";

  return (
    <div className={styles.wrap} style={{ width: size }}>
      <svg width={size} height={size} className={styles.svg}>
        <circle
          className={styles.track}
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
        />
        <circle
          className={styles.progress}
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          strokeDasharray={`${dash} ${c - dash}`}
        />
      </svg>

      <div className={styles.center}>
        <div className={styles.value}>{v}</div>
        <div className={styles.outOf}>/ 100</div>
        <div className={styles.status}>{status}</div>
      </div>

      <div className={styles.caption}>{label}</div>
    </div>
  );
}
