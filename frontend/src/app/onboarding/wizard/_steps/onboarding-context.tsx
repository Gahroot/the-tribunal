"use client";

import { useQuery } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  getFubConnection,
  type ImportFubContactsResponse,
} from "@/lib/api/realtor";
import { queryKeys } from "@/lib/query-keys";

/**
 * Saved Follow Up Boss connection for the targeted workspace, read from the
 * server so "connected" survives a reload and only ever reflects a persisted
 * connection. A failed refetch keeps the last good value (React Query keeps
 * `data` on error), so a transient blip never flips a valid connection off.
 */
export function useFubConnection(workspaceId: string | null) {
  const query = useQuery({
    queryKey: queryKeys.realtor.fubConnection(workspaceId ?? ""),
    queryFn: () => getFubConnection(workspaceId as string),
    enabled: !!workspaceId,
  });
  return {
    connected: query.data?.connected === true,
    accountName: query.data?.account_name ?? null,
    /** First load still in flight (no known state yet). */
    isChecking: !!workspaceId && query.isPending,
    /** Couldn't read status and have no previous value to fall back on. */
    checkFailed: query.isError && query.data === undefined,
    refetch: query.refetch,
  };
}

/**
 * Extras the onboarding flow tracks outside the form:
 *  - uploaded CSV file + parsed row count (File can't go in form values)
 *  - verified-connection metadata returned by the API (Cal.com; Follow Up
 *    Boss readiness comes from the server via useFubConnection)
 *  - result of the Follow Up Boss import
 *  - leads-step validation error (since "have leads" isn't a form field)
 */
interface OnboardingExtras {
  csvFile: File | null;
  csvRowCount: number | null;
  setCsvFile: (file: File | null, rows: number | null) => void;

  fubImportResult: ImportFubContactsResponse | null;
  setFubImportResult: (result: ImportFubContactsResponse | null) => void;

  calcomConnected: boolean;
  calcomUsername: string | null;
  markCalcomConnected: (username: string | null) => void;

  leadsError: string | null;
  setLeadsError: (msg: string | null) => void;
}

const OnboardingExtrasContext = createContext<OnboardingExtras | null>(null);

export function OnboardingExtrasProvider({ children }: { children: ReactNode }) {
  const [csvFile, setCsvFileState] = useState<File | null>(null);
  const [csvRowCount, setCsvRowCount] = useState<number | null>(null);

  const [fubImportResult, setFubImportResult] =
    useState<ImportFubContactsResponse | null>(null);

  const [calcomConnected, setCalcomConnected] = useState(false);
  const [calcomUsername, setCalcomUsername] = useState<string | null>(null);

  const [leadsError, setLeadsError] = useState<string | null>(null);

  const setCsvFile = useCallback((file: File | null, rows: number | null) => {
    setCsvFileState(file);
    setCsvRowCount(rows);
    if (file) setLeadsError(null);
  }, []);

  const markCalcomConnected = useCallback((username: string | null) => {
    setCalcomConnected(true);
    setCalcomUsername(username);
  }, []);

  const value = useMemo<OnboardingExtras>(
    () => ({
      csvFile,
      csvRowCount,
      setCsvFile,
      fubImportResult,
      setFubImportResult,
      calcomConnected,
      calcomUsername,
      markCalcomConnected,
      leadsError,
      setLeadsError,
    }),
    [
      csvFile,
      csvRowCount,
      setCsvFile,
      fubImportResult,
      calcomConnected,
      calcomUsername,
      markCalcomConnected,
      leadsError,
    ]
  );

  return (
    <OnboardingExtrasContext.Provider value={value}>
      {children}
    </OnboardingExtrasContext.Provider>
  );
}

export function useOnboardingExtras(): OnboardingExtras {
  const ctx = useContext(OnboardingExtrasContext);
  if (!ctx) {
    throw new Error(
      "useOnboardingExtras must be used inside <OnboardingExtrasProvider>"
    );
  }
  return ctx;
}
