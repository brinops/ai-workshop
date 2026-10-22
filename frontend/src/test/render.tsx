import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";

export function renderWithProviders(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}
