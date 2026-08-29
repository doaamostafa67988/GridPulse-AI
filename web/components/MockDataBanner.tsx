import { AlertTriangle } from "lucide-react";

export function MockDataBanner() {
  return (
    <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
      <p>
        Showing synthetic demo data — the backend hasn&apos;t run the real data pipeline yet (no{" "}
        <code className="rounded bg-amber-100 px-1 py-0.5">tx_risk_table.csv</code> found). Numbers and
        geometry below are for demonstration only.
      </p>
    </div>
  );
}
