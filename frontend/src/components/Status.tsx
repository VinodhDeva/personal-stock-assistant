import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="status" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" /> {label}
    </div>
  );
}

export function ErrorBox({ error, title = "Something went wrong" }: { error: unknown; title?: string }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="status error" role="alert">
      <strong>{title}.</strong> {message}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="status empty">{children}</div>;
}
