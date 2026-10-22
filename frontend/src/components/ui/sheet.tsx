import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Sheet = DialogPrimitive.Root;
export const SheetTitle = DialogPrimitive.Title;
export const SheetDescription = DialogPrimitive.Description;

export function SheetContent({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/55 backdrop-blur-[2px] data-[state=open]:animate-[card-in_200ms_ease-out]" />
      <DialogPrimitive.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-full max-w-[min(1100px,94vw)] flex-col border-l border-line-strong bg-bg shadow-2xl",
          "data-[state=open]:animate-[sheet-in_260ms_cubic-bezier(0.2,0.8,0.2,1)] focus-visible:outline-none",
          className,
        )}
        onOpenAutoFocus={(e) => {
          // Focus the panel itself instead of flashing a focus ring on the close button.
          e.preventDefault();
          (e.currentTarget as HTMLElement | null)?.focus();
        }}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          className="absolute right-3 top-3 rounded-md p-1.5 text-muted hover:bg-raised hover:text-fg"
          aria-label="Close task details"
        >
          <X className="size-5" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
