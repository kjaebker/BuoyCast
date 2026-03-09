import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

const TOAST_VARIANTS = {
  default: "default",
  success: "success",
  error: "error",
  warning: "warning",
  info: "info",
} as const;

type ToastVariant = (typeof TOAST_VARIANTS)[keyof typeof TOAST_VARIANTS];

interface Toast {
  id: string;
  title?: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

type ToastListener = (toasts: Toast[]) => void;

let toasts: Toast[] = [];
const listeners = new Set<ToastListener>();

function notify() {
  for (const listener of listeners) {
    listener([...toasts]);
  }
}

function toast(options: Omit<Toast, "id"> | string) {
  const t: Toast =
    typeof options === "string"
      ? { id: crypto.randomUUID(), description: options }
      : { id: crypto.randomUUID(), ...options };

  toasts = [...toasts, t];
  notify();

  const duration = t.duration ?? 4000;
  setTimeout(() => {
    dismiss(t.id);
  }, duration);

  return t.id;
}

toast.success = (message: string) =>
  toast({ description: message, variant: "success" });
toast.error = (message: string) =>
  toast({ description: message, variant: "error" });
toast.warning = (message: string) =>
  toast({ description: message, variant: "warning" });
toast.info = (message: string) =>
  toast({ description: message, variant: "info" });

function dismiss(id: string) {
  toasts = toasts.filter((t) => t.id !== id);
  notify();
}

function useToasts() {
  const [state, setState] = React.useState<Toast[]>([]);

  React.useEffect(() => {
    listeners.add(setState);
    return () => {
      listeners.delete(setState);
    };
  }, []);

  return state;
}

const variantStyles: Record<ToastVariant, string> = {
  default: "border-border bg-background text-foreground",
  success: "border-green-500/30 bg-green-50 text-green-900 dark:bg-green-950 dark:text-green-100",
  error: "border-red-500/30 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-100",
  warning: "border-yellow-500/30 bg-yellow-50 text-yellow-900 dark:bg-yellow-950 dark:text-yellow-100",
  info: "border-blue-500/30 bg-blue-50 text-blue-900 dark:bg-blue-950 dark:text-blue-100",
};

interface ToasterProps {
  className?: string;
  position?: "top-right" | "top-left" | "bottom-right" | "bottom-left" | "top-center" | "bottom-center";
}

function Toaster({ className, position = "bottom-right" }: ToasterProps) {
  const currentToasts = useToasts();

  const positionClasses: Record<string, string> = {
    "top-right": "top-4 right-4",
    "top-left": "top-4 left-4",
    "bottom-right": "bottom-4 right-4",
    "bottom-left": "bottom-4 left-4",
    "top-center": "top-4 left-1/2 -translate-x-1/2",
    "bottom-center": "bottom-4 left-1/2 -translate-x-1/2",
  };

  if (currentToasts.length === 0) return null;

  return (
    <div
      className={cn(
        "fixed z-[100] flex flex-col gap-2 w-full max-w-sm pointer-events-none",
        positionClasses[position],
        className
      )}
    >
      {currentToasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            "pointer-events-auto relative flex items-start gap-3 rounded-lg border p-4 shadow-lg transition-all animate-in fade-in slide-in-from-bottom-2",
            variantStyles[t.variant ?? "default"]
          )}
        >
          <div className="flex-1 space-y-1">
            {t.title && (
              <p className="text-sm font-semibold">{t.title}</p>
            )}
            {t.description && (
              <p className="text-sm opacity-90">{t.description}</p>
            )}
          </div>
          <button
            onClick={() => dismiss(t.id)}
            className="shrink-0 rounded-sm opacity-70 transition-opacity hover:opacity-100"
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Dismiss</span>
          </button>
        </div>
      ))}
    </div>
  );
}
Toaster.displayName = "Toaster";

export { Toaster, toast, dismiss, TOAST_VARIANTS };
export type { Toast, ToastVariant, ToasterProps };
