import { riskBg } from "@/lib/format";

export function RiskBadge({ score }: { score: number }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${riskBg(score)}`}>
      {score.toFixed(1)}
    </span>
  );
}
