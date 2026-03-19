"use client";

import * as React from "react";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { AuthProvider } from "./auth-provider";
import { WorkspaceProvider } from "./workspace-provider";
import { PageErrorBoundary } from "@/components/ui/error-boundary";

interface ProvidersProps {
  children: React.ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <WorkspaceProvider>
          <PageErrorBoundary>
            {children}
          </PageErrorBoundary>
          <Toaster position="bottom-right" richColors />
        </WorkspaceProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
