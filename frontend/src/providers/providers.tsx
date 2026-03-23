"use client";

import * as React from "react";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
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
    <ThemeProvider attribute="class" defaultTheme="dark" disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <WorkspaceProvider>
            <PageErrorBoundary>
              {children}
            </PageErrorBoundary>
            <Toaster
              position="bottom-right"
              toastOptions={{
                classNames: {
                  toast: "!bg-card/90 !backdrop-blur-md !border !border-border !shadow-lg !shadow-black/10",
                  title: "!text-foreground !font-semibold",
                  description: "!text-muted-foreground",
                  success: "!border-l-4 !border-l-success",
                  error: "!border-l-4 !border-l-destructive",
                  warning: "!border-l-4 !border-l-warning",
                  info: "!border-l-4 !border-l-primary",
                },
              }}
            />
          </WorkspaceProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
