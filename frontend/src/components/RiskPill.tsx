import type { Risk } from "../types";
import styles from "./RiskPill.module.css";

export function riskClass(risk?: string) {
  if (risk === "red") return `${styles.risk} ${styles.riskRed}`;
  if (risk === "yellow") return `${styles.risk} ${styles.riskYellow}`;
  return `${styles.risk} ${styles.riskGreen}`;
}

export default function RiskPill({ risk }: { risk: Risk }) {
  return <span className={riskClass(risk)}>{risk.toUpperCase()}</span>;
}
