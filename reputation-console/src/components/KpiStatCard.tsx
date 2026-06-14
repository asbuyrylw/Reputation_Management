import { Card } from "./ui";

interface Props {
  label: string;
  value: string;
  delta?: number | null;
  goodDirection?: "up" | "down"; // which direction is good (contested-down is good)
  hint?: string;
}

export function KpiStatCard({ label, value, delta, goodDirection = "up", hint }: Props) {
  let arrow: React.ReactNode = null;
  if (delta != null && Math.abs(delta) >= 0.005) {
    const up = delta > 0;
    const good = goodDirection === "up" ? up : !up;
    arrow = (
      <span className={good ? "text-green-600" : "text-red-600"}>
        {up ? "▲" : "▼"} {Math.abs(delta).toFixed(2)}
      </span>
    );
  }
  return (
    <Card>
      <div className="text-sm font-medium text-gray-500">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <div className="text-3xl font-semibold text-gray-900">{value}</div>
        {arrow && <div className="text-sm font-medium">{arrow}</div>}
      </div>
      {hint && <div className="mt-2 text-xs leading-snug text-gray-400">{hint}</div>}
    </Card>
  );
}
