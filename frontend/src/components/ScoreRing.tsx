import styles from "./ScoreRing.module.css";

export default function ScoreRing({
  value,
  label,
  size = 90,
  stroke = 10,
}: {
  value: number;
  label?: string;
  size?: number;
  stroke?: number;
}) {
  const normalized = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - normalized / 100);

  return (
    <div className={styles.container} style={{ width: size }}>
      <svg className={styles.svg} width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          className={styles.track}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          className={styles.progress}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          fill="none"
        />
      </svg>
      <div className={styles.value}>{Math.round(normalized)}</div>
      {label ? <div className={styles.label}>{label}</div> : null}
    </div>
  );
}
