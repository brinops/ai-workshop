import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as React from "react";
import { Button } from "./button";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = "Keep going",
  onConfirm,
  destructive = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  destructive?: boolean;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[60] bg-black/60" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-[61] w-[min(440px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-line-strong bg-panel p-5 shadow-2xl focus-visible:outline-none">
          <DialogPrimitive.Title className="text-base font-semibold">{title}</DialogPrimitive.Title>
          <DialogPrimitive.Description className="mt-2 text-sm text-muted">{description}</DialogPrimitive.Description>
          <div className="mt-5 flex justify-end gap-2">
            <DialogPrimitive.Close asChild>
              <Button variant="ghost">{cancelLabel}</Button>
            </DialogPrimitive.Close>
            <Button
              variant={destructive ? "danger" : "primary"}
              onClick={() => {
                onConfirm();
                onOpenChange(false);
              }}
            >
              {confirmLabel}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
