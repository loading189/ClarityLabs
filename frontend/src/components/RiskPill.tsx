import styles from "./RiskPill.module.css";

type RiskLevel = "green" | "yellow" | "red" | string;

function riskLabel(risk?: RiskLevel) {
  const normalized = (risk || "").toLowerCase();
  if (normalized === "red") return "High risk";
  if (normalized === "yellow") return "Medium risk";
  if (normalized === "green") return "Low risk";
  return risk || "Unknown";
}

export default function RiskPill({ risk }: { risk?: RiskLevel }) {
  const normalized = (risk || "").toLowerCase();
  const tone =
    normalized === "red"
      ? styles.red
      : normalized === "yellow"
      ? styles.yellow
      : normalized === "green"
      ? styles.green
      : styles.neutral;

  return <span className={`${styles.pill} ${tone}`}>{riskLabel(risk)}</span>;
}
