"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, FileSpreadsheet, Loader2, Phone, Users } from "lucide-react";
import { useCallback, useId, useState } from "react";
import { useFormContext } from "react-hook-form";
import { toast } from "sonner";

import { FileDropzone } from "@/components/shared/file-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { importFubContacts } from "@/lib/api/realtor";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { formatNumber } from "@/lib/utils/number";

import type { OnboardingFormValues } from "../_state";

import { useFubConnection, useOnboardingExtras } from "./onboarding-context";

const FAILURE_LABELS: Record<string, string> = {
  missing_phone: "no phone number",
  invalid_phone: "phone number couldn't be read",
  save_failed: "couldn't be saved",
};

export interface LeadsStepProps {
  /** The workspace this guided setup targets; never re-resolved here. */
  workspaceId: string | null;
}

export function LeadsStep({ workspaceId }: LeadsStepProps) {
  const form = useFormContext<OnboardingFormValues>();
  const {
    csvFile,
    csvRowCount,
    setCsvFile,
    fubImportResult,
    setFubImportResult,
    leadsError,
    setLeadsError,
  } = useOnboardingExtras();
  const queryClient = useQueryClient();
  const connection = useFubConnection(workspaceId);
  const fubConnected = connection.connected;

  const [fubImporting, setFubImporting] = useState(false);
  const [fubImportError, setFubImportError] = useState<string | null>(null);
  const areaCodeId = useId();

  const processFile = useCallback(
    (selected: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        const lines = text.split("\n").filter((l) => l.trim().length > 0);
        const rows = Math.max(0, lines.length - 1);
        setCsvFile(selected, rows);
      };
      reader.readAsText(selected);
    },
    [setCsvFile],
  );

  const handleFubImport = useCallback(async () => {
    if (!workspaceId) {
      toast.error("No workspace found. Please log in again.");
      return;
    }
    setFubImporting(true);
    setFubImportError(null);
    try {
      // Uses the connection already saved on this workspace. Re-running is
      // safe: leads already in the workspace are skipped, not duplicated.
      const result = await importFubContacts(workspaceId, true, undefined, undefined, false);
      setFubImportResult(result);
      setLeadsError(null);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.contacts.all(workspaceId),
      });
      toast.success(`Imported ${formatNumber(result.imported)} leads from Follow Up Boss`);
    } catch (err) {
      const message = getApiErrorMessage(err, "Failed to import leads.");
      setFubImportError(message);
      toast.error(message);
    } finally {
      setFubImporting(false);
    }
  }, [workspaceId, queryClient, setFubImportResult, setLeadsError]);

  const areaCode = form.watch("area_code");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Import Your Dead Leads</h2>
        <p className="text-muted-foreground mt-1">
          Choose how to import the leads you want to reactivate
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card className={`relative overflow-hidden ${!fubConnected ? "opacity-50" : ""}`}>
          <CardContent className="p-5 flex flex-col items-center text-center gap-3">
            <div className="flex items-center justify-center w-12 h-12 rounded-full text-muted-foreground">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <p className="font-semibold text-sm">Pull from Follow Up Boss</p>
              {fubImportResult !== null && (
                <div className="text-xs mt-1 space-y-0.5" role="status">
                  <p className="text-success">
                    {formatNumber(fubImportResult.imported)} lead
                    {fubImportResult.imported !== 1 ? "s" : ""} imported
                  </p>
                  {fubImportResult.skipped > 0 && (
                    <p className="text-muted-foreground">
                      {formatNumber(fubImportResult.skipped)} already in this workspace
                    </p>
                  )}
                  {fubImportResult.failed > 0 && (
                    <p className="text-destructive">
                      {formatNumber(fubImportResult.failed)} couldn&apos;t be imported
                    </p>
                  )}
                </div>
              )}
              {fubImportError && <p className="text-xs text-destructive mt-1">{fubImportError}</p>}
              {connection.isChecking && (
                <p className="text-xs text-muted-foreground mt-1">
                  Checking Follow Up Boss connection...
                </p>
              )}
              {!fubConnected && !connection.isChecking && (
                <p className="text-xs text-muted-foreground mt-1">
                  {connection.checkFailed
                    ? "Couldn't check the Follow Up Boss connection. Go back to Step 1 to retry."
                    : "Connect Follow Up Boss in Step 1 first"}
                </p>
              )}
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!fubConnected || !workspaceId || fubImporting}
              onClick={handleFubImport}
            >
              {fubImporting ? (
                <Loader2 className="size-4 mr-2 animate-spin" />
              ) : (
                <Users className="size-4 mr-2" />
              )}
              {fubImporting
                ? "Importing..."
                : fubImportResult !== null || fubImportError
                  ? "Import Again"
                  : "Import All Leads"}
            </Button>
            {fubImportResult && (fubImportResult.failures?.length ?? 0) > 0 && (
              <ul className="text-xs text-muted-foreground text-left w-full space-y-0.5">
                {fubImportResult.failures?.slice(0, 5).map((f, i) => (
                  <li key={`${f.fub_id ?? "x"}-${i}`}>
                    Follow Up Boss lead {f.fub_id ?? "(unknown)"}:{" "}
                    {FAILURE_LABELS[f.reason] ?? f.reason}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="relative overflow-hidden">
          <CardContent className="p-5 flex flex-col items-center text-center gap-3">
            <div className="flex items-center justify-center w-12 h-12 rounded-full text-muted-foreground">
              <FileSpreadsheet className="w-6 h-6" />
            </div>
            <div>
              <p className="font-semibold text-sm">Upload CSV</p>
              <p className="text-xs text-muted-foreground mt-1">Drag and drop or click to browse</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <FileDropzone
        accept=".csv"
        onFile={processFile}
        onReject={(reason) => toast.error(reason)}
        placeholder="Drop your CSV here or click to browse"
        subtext="Accepts .csv files"
        ariaLabel="Upload CSV file"
      />

      {csvFile && (
        <Card className="bg-muted/30">
          <CardContent className="py-3 px-4 flex items-center gap-3">
            <CheckCircle2 className="size-4 text-success shrink-0" />
            <div className="min-w-0">
              <p className="font-medium truncate text-sm">{csvFile.name}</p>
              {csvRowCount !== null && (
                <p className="text-xs text-muted-foreground">
                  ~{formatNumber(csvRowCount)} lead
                  {csvRowCount !== 1 ? "s" : ""} detected
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {leadsError && <p className="text-sm text-destructive">{leadsError}</p>}

      <p className="text-xs text-muted-foreground">
        CSV needs at least: <span className="font-mono font-medium">first_name</span> (or{" "}
        <span className="font-mono font-medium">name</span>),{" "}
        <span className="font-mono font-medium">phone</span>. Email is optional.
      </p>

      <div className="space-y-2">
        <Label htmlFor={areaCodeId}>Preferred Area Code (optional)</Label>
        <div className="relative max-w-xs">
          <Phone className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            id={areaCodeId}
            type="text"
            placeholder="e.g. 212"
            maxLength={3}
            className="pl-9"
            value={areaCode}
            onChange={(e) =>
              form.setValue("area_code", e.target.value.replace(/\D/g, ""), {
                shouldDirty: true,
              })
            }
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Preferred area code for your texting number. Leave blank for any US number.
        </p>
      </div>
    </div>
  );
}
