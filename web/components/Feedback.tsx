import { Loader2 } from "lucide-react";

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-12 text-sm text-muted">
      <Loader2 size={18} className="animate-spin text-brand" />
      {label ?? "Loading..."}
    </div>
  );
}

export function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="panel border-red-200 bg-red-50 p-6 text-sm text-red-700">
      <p className="font-semibold">Couldn&apos;t reach the API</p>
      <p className="mt-1 text-red-600">{message}</p>
      <p className="mt-3 text-xs text-red-500">
        Make sure the FastAPI backend is running:{" "}
        <code className="rounded bg-red-100 px-1 py-0.5">uvicorn backend.api:app --reload --port 8000</code>
      </p>
    </div>
  );
}
