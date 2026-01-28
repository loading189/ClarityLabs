import type { Risk } from "../types";

export function riskClass(risk?: string) {
  if (risk === "red") return "risk risk--red";
  if (risk === "yellow") return "risk risk--yellow";
  return "risk risk--green";
}

export default function RiskPill({ risk }: { risk: Risk }) {
  return <span className={riskClass(risk)}>{risk.toUpperCase()}</span>;
}
