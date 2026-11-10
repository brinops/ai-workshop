import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { StreamProvider } from "@/hooks/StreamProvider";
import { DashboardPage } from "@/pages/DashboardPage";
import { JiraWorkflowPage } from "@/pages/JiraWorkflowPage";
import { ApiError } from "@/services/api";

export function App() {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 2_000,
            refetchOnWindowFocus: true,
            // 4xx answers are definitive (e.g. unknown task); only retry transport/5xx failures.
            retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <StreamProvider>
        <TooltipProvider>
          <ToastProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/tasks/:taskId" element={<DashboardPage />} />
                <Route path="/jira-workflow" element={<JiraWorkflowPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
          </ToastProvider>
        </TooltipProvider>
      </StreamProvider>
    </QueryClientProvider>
  );
}
