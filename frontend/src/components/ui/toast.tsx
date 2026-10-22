import { CheckCircle2, AlertTriangle, X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "info";
interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
}

interface ToastApi {
  toast: (t: Omit<ToastItem, "id">) => void;
}

const ToastContext = React.createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const nextId = React.useRef(1);

  const dismiss = React.useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const toast = React.useCallback(
    (t: Omit<ToastItem, "id">) => {
      const id = nextId.current++;
      setItems((xs) => [...xs.slice(-3), { ...t, id }]);
      window.setTimeout(() => dismiss(id), t.tone === "error" ? 7000 : 3500);
    },
    [dismiss],
  );
  const api = React.useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[90] flex w-[min(380px,92vw)] flex-col gap-2" aria-live="polite" role="status">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex animate-card-in items-start gap-2.5 rounded-lg border bg-panel px-3.5 py-3 text-sm shadow-xl",
              t.tone === "error" ? "border-bad/50" : t.tone === "success" ? "border-ok/40" : "border-line-strong",
            )}
          >
            {t.tone === "error" ? (
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" aria-hidden />
            ) : (
              <CheckCircle2 className={cn("mt-0.5 size-4 shrink-0", t.tone === "success" ? "text-ok" : "text-accent")} aria-hidden />
            )}
            <div className="min-w-0 flex-1">
              <p className="font-medium">{t.title}</p>
              {t.description && <p className="mt-0.5 text-muted">{t.description}</p>}
            </div>
            <button className="rounded p-0.5 text-faint hover:text-fg" onClick={() => dismiss(t.id)} aria-label="Dismiss notification">
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
