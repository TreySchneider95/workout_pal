import { CloudCheck, CloudOff, LoaderCircle } from "lucide-react";

import { useSaveStatus } from "@/hooks/useSessionEditor";
import { cn } from "@/lib/utils";

export function SaveIndicator({ className }: { className?: string }) {
  const { status, pending } = useSaveStatus();
  const offline = status === "offline";
  const saving = status === "saving" || (pending && !offline);
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium", offline ? "text-warning" : "text-subtle", className)}
      role="status"
      aria-live="polite"
    >
      {offline ? (
        <>
          <CloudOff className="size-4" /> Offline · kept on device
        </>
      ) : saving ? (
        <>
          <LoaderCircle className="size-4 animate-spin" /> Saving
        </>
      ) : (
        <>
          <CloudCheck className="size-4" /> Saved
        </>
      )}
    </span>
  );
}
