import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area";
import * as React from "react";
import { cn } from "@/lib/utils";

export const ScrollArea = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.Viewport>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root> & { viewportClassName?: string }
>(({ className, viewportClassName, children, ...props }, ref) => (
  <ScrollAreaPrimitive.Root className={cn("relative overflow-hidden", className)} {...props}>
    <ScrollAreaPrimitive.Viewport ref={ref} className={cn("size-full rounded-[inherit]", viewportClassName)}>
      {children}
    </ScrollAreaPrimitive.Viewport>
    <ScrollAreaPrimitive.Scrollbar orientation="vertical" className="flex w-2 touch-none select-none p-px">
      <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-line-strong" />
    </ScrollAreaPrimitive.Scrollbar>
    <ScrollAreaPrimitive.Scrollbar orientation="horizontal" className="flex h-2 touch-none select-none flex-col p-px">
      <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-line-strong" />
    </ScrollAreaPrimitive.Scrollbar>
    <ScrollAreaPrimitive.Corner />
  </ScrollAreaPrimitive.Root>
));
ScrollArea.displayName = "ScrollArea";
