"use client";

import { useState, useRef, useCallback, useId } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import type { LucideIcon } from "lucide-react";
import {
  ExternalLink,
  Settings,
  Key,
  ClipboardPaste,
  Calendar,
  Plus,
  Copy,
  Upload,
  FileSpreadsheet,
  Database,
  Rocket,
  CheckCircle2,
  Loader2,
  Phone,
  Users,
  Plug,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { WizardContainer } from "@/components/wizard/wizard-container";
import { useWizard, type WizardStepDef } from "@/hooks/useWizard";
import { useWorkspace } from "@/providers/workspace-provider";
import { getApiErrorMessage } from "@/lib/utils/errors";
import {
  verifyCalcom,
  parseCalcomUrl,
  onboard,
  createCampaignFromCsv,
  verifyFub,
  importFubContacts,
} from "@/lib/api/realtor";

const STEPS = [
  { id: "fub", label: "Connect CRM", icon: Database },
  { id: "calcom", label: "Calendar", icon: Calendar },
  { id: "leads", label: "Import Leads", icon: Upload },
  { id: "review", label: "Review & Launch", icon: Rocket },
] as const satisfies readonly WizardStepDef<string>[];

type StepId = (typeof STEPS)[number]["id"];

interface OnboardingFormData {
  fub_api_key: string;
  calcom_api_key: string;
  calcom_booking_url: string;
  area_code: string;
}

const INITIAL_FORM_DATA: OnboardingFormData = {
  fub_api_key: "",
  calcom_api_key: "",
  calcom_booking_url: "",
  area_code: "",
};

// ---- Reusable Instruction Step ----

interface InstructionStepProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  link?: string;
  linkLabel?: string;
}

function InstructionStep({
  icon: Icon,
  title,
  description,
  link,
  linkLabel,
}: InstructionStepProps) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary shrink-0">
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <p className="font-medium text-sm">{title}</p>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
        {link && (
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 mt-1 text-xs text-primary hover:underline"
          >
            {linkLabel ?? "Open"} <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  );
}

// ---- Step 1: Connect Follow Up Boss ----

interface FubStepProps {
  apiKey: string;
  onApiKeyChange: (v: string) => void;
  fubConnected: boolean;
  fubName: string | null;
  onConnected: (name: string | null) => void;
  errors: Record<string, string>;
}

function FubStep({
  apiKey,
  onApiKeyChange,
  fubConnected,
  fubName,
  onConnected,
  errors,
}: FubStepProps) {
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const apiKeyId = useId();

  const handleTest = useCallback(async () => {
    if (!apiKey.trim()) {
      toast.error("Paste your Follow Up Boss API key first.");
      return;
    }
    setTesting(true);
    setTestError(null);
    try {
      const result = await verifyFub(apiKey.trim());
      if (result.valid) {
        onConnected(result.name ?? null);
        toast.success(
          result.name
            ? `Connected as ${result.name}`
            : "Follow Up Boss connected!"
        );
      } else {
        setTestError("That API key didn't work. Double-check and try again.");
      }
    } catch (err) {
      setTestError(getApiErrorMessage(err, "Connection test failed."));
    } finally {
      setTesting(false);
    }
  }, [apiKey, onConnected]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Connect Your CRM</h2>
        <p className="text-muted-foreground mt-1">
          We&apos;ll pull your leads directly from Follow Up Boss
        </p>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">
          How to find your API key:
        </p>
        <div className="space-y-2">
          <InstructionStep
            icon={ExternalLink}
            title="Log into Follow Up Boss"
            link="https://app.followupboss.com"
            linkLabel="Open Follow Up Boss"
          />
          <InstructionStep
            icon={Settings}
            title="Click Admin in the top menu, then click API"
          />
          <InstructionStep icon={Key} title="Copy your API key" />
          <InstructionStep icon={ClipboardPaste} title="Paste it below" />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor={apiKeyId}>Follow Up Boss API Key</Label>
        <div className="relative">
          <Key className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            id={apiKeyId}
            type="password"
            placeholder="fub_api_••••••••••••••••"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            className="pl-9"
          />
        </div>
        {errors.fub_api_key && (
          <p className="text-sm text-destructive">{errors.fub_api_key}</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={handleTest}
          disabled={testing}
        >
          {testing ? (
            <Loader2 className="size-4 mr-2 animate-spin" />
          ) : (
            <Plug className="size-4 mr-2" />
          )}
          Test Connection
        </Button>

        {fubConnected && (
          <Badge
            variant="outline"
            className="text-green-600 border-green-500 gap-1"
          >
            <CheckCircle2 className="size-3.5" />
            {fubName ? `Connected as ${fubName}` : "Connected"}
          </Badge>
        )}

        {testError && (
          <p className="text-sm text-destructive flex items-center gap-1">
            <AlertCircle className="size-3.5 shrink-0" />
            {testError}
          </p>
        )}
      </div>
    </div>
  );
}

// ---- Step 2: Connect Cal.com ----

interface CalcomStepProps {
  apiKey: string;
  bookingUrl: string;
  onApiKeyChange: (v: string) => void;
  onBookingUrlChange: (v: string) => void;
  calcomConnected: boolean;
  calcomUsername: string | null;
  onConnected: (username: string | null) => void;
  errors: Record<string, string>;
}

function CalcomStep({
  apiKey,
  bookingUrl,
  onApiKeyChange,
  onBookingUrlChange,
  calcomConnected,
  calcomUsername,
  onConnected,
  errors,
}: CalcomStepProps) {
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const apiKeyId = useId();
  const urlId = useId();

  const handleTest = useCallback(async () => {
    if (!apiKey.trim()) {
      toast.error("Paste your Cal.com API key first.");
      return;
    }
    setTesting(true);
    setTestError(null);
    try {
      const result = await verifyCalcom(apiKey.trim());
      if (result.valid) {
        onConnected(result.username ?? null);
        toast.success(
          result.username
            ? `Connected as @${result.username}`
            : "Cal.com connection verified!"
        );
      } else {
        setTestError("Invalid API key. Please check and try again.");
      }
    } catch (err) {
      setTestError(getApiErrorMessage(err, "Connection test failed."));
    } finally {
      setTesting(false);
    }
  }, [apiKey, onConnected]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Set Up Your Calendar</h2>
        <p className="text-muted-foreground mt-1">
          When a lead wants to meet, we&apos;ll book directly on your calendar
        </p>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">
          How to get your API key:
        </p>
        <div className="space-y-2">
          <InstructionStep
            icon={ExternalLink}
            title="Go to Cal.com"
            description="New to Cal.com? Sign up first. Already have an account? Go to API keys."
            link="https://cal.com/signup"
            linkLabel="Sign up for Cal.com"
          />
          <InstructionStep
            icon={ExternalLink}
            title="Already have an account?"
            link="https://app.cal.com/settings/developer/api-keys"
            linkLabel="Go to API keys"
          />
          <InstructionStep icon={Plus} title='Click "Create new key"' />
          <InstructionStep icon={Key} title="Copy the key" />
          <InstructionStep icon={ClipboardPaste} title="Paste it below" />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor={apiKeyId}>Cal.com API Key</Label>
        <div className="relative">
          <Key className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            id={apiKeyId}
            type="password"
            placeholder="cal_live_••••••••••••••••"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            className="pl-9"
          />
        </div>
        {errors.calcom_api_key && (
          <p className="text-sm text-destructive">{errors.calcom_api_key}</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={handleTest}
          disabled={testing}
        >
          {testing ? (
            <Loader2 className="size-4 mr-2 animate-spin" />
          ) : (
            <Plug className="size-4 mr-2" />
          )}
          Test Connection
        </Button>

        {calcomConnected && (
          <Badge
            variant="outline"
            className="text-green-600 border-green-500 gap-1"
          >
            <CheckCircle2 className="size-3.5" />
            {calcomUsername ? `Connected as @${calcomUsername}` : "Connected"}
          </Badge>
        )}

        {testError && (
          <p className="text-sm text-destructive flex items-center gap-1">
            <AlertCircle className="size-3.5 shrink-0" />
            {testError}
          </p>
        )}
      </div>

      <div className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">
          How to get your booking URL:
        </p>
        <div className="space-y-2">
          <InstructionStep
            icon={ExternalLink}
            title="Go to Event Types"
            link="https://app.cal.com/event-types"
            linkLabel="Open Event Types"
          />
          <InstructionStep
            icon={Copy}
            title="Copy the URL of the event type you want leads to book"
            description="For example: https://cal.com/yourname/30min"
          />
          <InstructionStep icon={ClipboardPaste} title="Paste it below" />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor={urlId}>Cal.com Booking URL</Label>
        <div className="relative">
          <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            id={urlId}
            type="url"
            placeholder="https://cal.com/yourname/30min"
            value={bookingUrl}
            onChange={(e) => onBookingUrlChange(e.target.value)}
            className="pl-9"
          />
        </div>
        {errors.calcom_booking_url && (
          <p className="text-sm text-destructive">
            {errors.calcom_booking_url}
          </p>
        )}
      </div>
    </div>
  );
}

// ---- Step 3: Import Leads ----

interface LeadsStepProps {
  fubConnected: boolean;
  fubImportCount: number | null;
  onFubImport: () => Promise<void>;
  fubImporting: boolean;
  file: File | null;
  rowCount: number | null;
  areaCode: string;
  onFileChange: (file: File | null, rows: number | null) => void;
  onAreaCodeChange: (v: string) => void;
  errors: Record<string, string>;
}

function LeadsStep({
  fubConnected,
  fubImportCount,
  onFubImport,
  fubImporting,
  file,
  rowCount,
  areaCode,
  onFileChange,
  onAreaCodeChange,
  errors,
}: LeadsStepProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const areaCodeId = useId();

  const processFile = useCallback(
    (selected: File | null) => {
      if (!selected) {
        onFileChange(null, null);
        return;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        const lines = text.split("\n").filter((l) => l.trim().length > 0);
        const rows = Math.max(0, lines.length - 1);
        onFileChange(selected, rows);
      };
      reader.readAsText(selected);
    },
    [onFileChange]
  );

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    processFile(e.target.files?.[0] ?? null);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped?.name.endsWith(".csv")) {
      processFile(dropped);
    } else {
      toast.error("Please drop a .csv file.");
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Import Your Dead Leads</h2>
        <p className="text-muted-foreground mt-1">
          Choose how to import the leads you want to reactivate
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* FUB Import Card */}
        <Card
          className={`relative overflow-hidden ${!fubConnected ? "opacity-50" : ""}`}
        >
          <CardContent className="p-5 flex flex-col items-center text-center gap-3">
            <div className="flex items-center justify-center w-12 h-12 rounded-full bg-primary/10 text-primary">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <p className="font-semibold text-sm">Pull from Follow Up Boss</p>
              {fubImportCount !== null && (
                <p className="text-xs text-green-600 mt-1">
                  {fubImportCount.toLocaleString()} lead
                  {fubImportCount !== 1 ? "s" : ""} imported
                </p>
              )}
              {!fubConnected && (
                <p className="text-xs text-muted-foreground mt-1">
                  Connect Follow Up Boss in Step 1 first
                </p>
              )}
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!fubConnected || fubImporting}
              onClick={onFubImport}
            >
              {fubImporting ? (
                <Loader2 className="size-4 mr-2 animate-spin" />
              ) : (
                <Users className="size-4 mr-2" />
              )}
              Import All Leads
            </Button>
          </CardContent>
        </Card>

        {/* CSV Upload Card */}
        <Card className="relative overflow-hidden">
          <CardContent className="p-5 flex flex-col items-center text-center gap-3">
            <div className="flex items-center justify-center w-12 h-12 rounded-full bg-primary/10 text-primary">
              <FileSpreadsheet className="w-6 h-6" />
            </div>
            <div>
              <p className="font-semibold text-sm">Upload CSV</p>
              <p className="text-xs text-muted-foreground mt-1">
                Drag and drop or click to browse
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Dropzone (shown below the cards) */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload CSV file"
        className={`border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center gap-3 cursor-pointer transition-colors ${
          isDragging
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50 hover:bg-muted/30"
        }`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <Upload className="size-8 text-muted-foreground" />
        <div className="text-center">
          <p className="font-medium">Drop your CSV here or click to browse</p>
          <p className="text-sm text-muted-foreground mt-1">Accepts .csv files</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileInput}
        />
      </div>

      {file && (
        <Card className="bg-muted/30">
          <CardContent className="py-3 px-4 flex items-center gap-3">
            <CheckCircle2 className="size-4 text-green-500 shrink-0" />
            <div className="min-w-0">
              <p className="font-medium truncate text-sm">{file.name}</p>
              {rowCount !== null && (
                <p className="text-xs text-muted-foreground">
                  ~{rowCount.toLocaleString()} lead
                  {rowCount !== 1 ? "s" : ""} detected
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {errors.leads && (
        <p className="text-sm text-destructive">{errors.leads}</p>
      )}

      <p className="text-xs text-muted-foreground">
        CSV needs at least:{" "}
        <span className="font-mono font-medium">first_name</span> (or{" "}
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
            value={areaCode}
            onChange={(e) => onAreaCodeChange(e.target.value.replace(/\D/g, ""))}
            className="pl-9"
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Preferred area code for your texting number. Leave blank for any US
          number.
        </p>
      </div>
    </div>
  );
}

// ---- Step 4: Review & Launch ----

interface ReviewStepProps {
  fubConnected: boolean;
  fubName: string | null;
  calcomConnected: boolean;
  calcomUsername: string | null;
  bookingUrl: string;
  file: File | null;
  rowCount: number | null;
  fubImportCount: number | null;
  areaCode: string;
}

function ReviewStep({
  fubConnected,
  fubName,
  calcomConnected,
  calcomUsername,
  bookingUrl,
  file,
  rowCount,
  fubImportCount,
  areaCode,
}: ReviewStepProps) {
  const totalLeads = (fubImportCount ?? 0) + (rowCount ?? 0);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Ready to Launch</h2>
        <p className="text-muted-foreground mt-1">
          Review your setup and launch your lead reactivation campaign.
        </p>
      </div>

      <Card>
        <CardContent className="pt-4 pb-4 divide-y divide-border">
          {/* FUB */}
          <div className="flex items-center gap-3 py-3">
            {fubConnected ? (
              <CheckCircle2 className="size-5 text-green-500 shrink-0" />
            ) : (
              <AlertCircle className="size-5 text-amber-500 shrink-0" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {fubConnected
                  ? "Follow Up Boss connected"
                  : "Follow Up Boss not connected"}
              </p>
              {fubName && (
                <p className="text-xs text-muted-foreground">{fubName}</p>
              )}
            </div>
          </div>

          {/* Cal.com */}
          <div className="flex items-center gap-3 py-3">
            {calcomConnected ? (
              <CheckCircle2 className="size-5 text-green-500 shrink-0" />
            ) : (
              <AlertCircle className="size-5 text-amber-500 shrink-0" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {calcomConnected
                  ? "Cal.com connected"
                  : "Cal.com not connected"}
              </p>
              {calcomUsername && (
                <p className="text-xs text-muted-foreground truncate">
                  @{calcomUsername}
                </p>
              )}
              {bookingUrl && (
                <p className="text-xs text-muted-foreground truncate">
                  {bookingUrl}
                </p>
              )}
            </div>
          </div>

          {/* Leads */}
          <div className="flex items-center gap-3 py-3">
            <Users className="size-5 text-muted-foreground shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {totalLeads > 0
                  ? `${totalLeads.toLocaleString()} lead${totalLeads !== 1 ? "s" : ""} to contact`
                  : "No leads imported yet"}
              </p>
              <div className="text-xs text-muted-foreground space-y-0.5">
                {fubImportCount !== null && fubImportCount > 0 && (
                  <p>
                    {fubImportCount.toLocaleString()} from Follow Up Boss
                  </p>
                )}
                {file && rowCount !== null && (
                  <p>
                    ~{rowCount.toLocaleString()} from {file.name}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Phone */}
          <div className="flex items-center gap-3 py-3">
            <Phone className="size-5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-sm font-medium">
                {areaCode ? `Area code ${areaCode}` : "Any US number"}
              </p>
              <p className="text-xs text-muted-foreground">
                Texting number preference
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---- Main Onboarding Page ----

export default function OnboardingPage() {
  const router = useRouter();
  const { currentWorkspaceId } = useWorkspace();

  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvRowCount, setCsvRowCount] = useState<number | null>(null);

  const [fubConnected, setFubConnected] = useState(false);
  const [fubName, setFubName] = useState<string | null>(null);
  const [fubImportCount, setFubImportCount] = useState<number | null>(null);
  const [fubImporting, setFubImporting] = useState(false);

  const [calcomConnected, setCalcomConnected] = useState(false);
  const [calcomUsername, setCalcomUsername] = useState<string | null>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    currentStepId,
    currentStepIndex,
    isFirstStep,
    isLastStep,
    formData,
    errors,
    setErrors,
    goToStep,
    goNext,
    goPrevious,
    updateField,
  } = useWizard<StepId, OnboardingFormData>({
    steps: STEPS,
    initialFormData: INITIAL_FORM_DATA,
    validateOnNavigate: true,
    validateStep: (stepId, data, setErrs) => {
      const errs: Record<string, string> = {};

      if (stepId === "fub") {
        if (!data.fub_api_key.trim()) {
          errs.fub_api_key = "Follow Up Boss API key is required.";
        }
      }

      if (stepId === "calcom") {
        if (!data.calcom_api_key.trim()) {
          errs.calcom_api_key = "Cal.com API key is required.";
        }
        if (!data.calcom_booking_url.trim()) {
          errs.calcom_booking_url = "Booking URL is required.";
        } else if (!data.calcom_booking_url.startsWith("https://cal.com/")) {
          errs.calcom_booking_url =
            'URL must start with "https://cal.com/".';
        }
      }

      if (stepId === "leads") {
        if (!csvFile && fubImportCount === null) {
          errs.leads =
            "Import leads from Follow Up Boss or upload a CSV file.";
        }
      }

      setErrs(errs);
      return Object.keys(errs).length === 0;
    },
  });

  const handleFileChange = useCallback(
    (file: File | null, rows: number | null) => {
      setCsvFile(file);
      setCsvRowCount(rows);
      if (file) {
        setErrors((prev) => {
          const next = { ...prev };
          delete next.leads;
          return next;
        });
      }
    },
    [setErrors]
  );

  const handleFubConnected = useCallback((name: string | null) => {
    setFubConnected(true);
    setFubName(name);
  }, []);

  const handleCalcomConnected = useCallback((username: string | null) => {
    setCalcomConnected(true);
    setCalcomUsername(username);
  }, []);

  const handleFubImport = useCallback(async () => {
    if (!currentWorkspaceId) {
      toast.error("No workspace found. Please log in again.");
      return;
    }
    setFubImporting(true);
    try {
      const result = await importFubContacts(currentWorkspaceId, true);
      setFubImportCount(result.imported);
      setErrors((prev) => {
        const next = { ...prev };
        delete next.leads;
        return next;
      });
      toast.success(
        `Imported ${result.imported.toLocaleString()} leads from Follow Up Boss`
      );
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to import leads."));
    } finally {
      setFubImporting(false);
    }
  }, [currentWorkspaceId, setErrors]);

  const handleLaunch = useCallback(async () => {
    if (!currentWorkspaceId) {
      toast.error("No workspace found. Please log in again.");
      return;
    }

    if (!csvFile && fubImportCount === null) {
      toast.error("Please import leads first.");
      return;
    }

    setIsSubmitting(true);
    try {
      const { event_type_id } = await parseCalcomUrl(
        formData.calcom_booking_url
      );

      await onboard({
        calcom_api_key: formData.calcom_api_key,
        calcom_event_type_id: event_type_id,
      });

      if (csvFile) {
        await createCampaignFromCsv(currentWorkspaceId, csvFile, {
          skipDuplicates: true,
          areaCode: formData.area_code || undefined,
        });
      }

      toast.success("Campaign launched! Your leads are being contacted.");
      router.push("/realtor-dashboard");
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Launch failed. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  }, [csvFile, currentWorkspaceId, formData, fubImportCount, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-2xl border rounded-xl overflow-hidden shadow-xl bg-card min-h-[640px] flex flex-col">
        <WizardContainer
          steps={STEPS}
          currentStepId={currentStepId}
          currentStepIndex={currentStepIndex}
          onStepClick={goToStep}
          isFirstStep={isFirstStep}
          isLastStep={isLastStep}
          onPrevious={goPrevious}
          onNext={goNext}
          onSubmit={handleLaunch}
          isSubmitting={isSubmitting}
          submitLabel="Launch Campaign"
          submittingLabel="Launching..."
          submitIcon={Rocket}
        >
          {currentStepId === "fub" && (
            <FubStep
              apiKey={formData.fub_api_key}
              onApiKeyChange={(v) => updateField("fub_api_key", v)}
              fubConnected={fubConnected}
              fubName={fubName}
              onConnected={handleFubConnected}
              errors={errors}
            />
          )}

          {currentStepId === "calcom" && (
            <CalcomStep
              apiKey={formData.calcom_api_key}
              bookingUrl={formData.calcom_booking_url}
              onApiKeyChange={(v) => updateField("calcom_api_key", v)}
              onBookingUrlChange={(v) =>
                updateField("calcom_booking_url", v)
              }
              calcomConnected={calcomConnected}
              calcomUsername={calcomUsername}
              onConnected={handleCalcomConnected}
              errors={errors}
            />
          )}

          {currentStepId === "leads" && (
            <LeadsStep
              fubConnected={fubConnected}
              fubImportCount={fubImportCount}
              onFubImport={handleFubImport}
              fubImporting={fubImporting}
              file={csvFile}
              rowCount={csvRowCount}
              areaCode={formData.area_code}
              onFileChange={handleFileChange}
              onAreaCodeChange={(v) => updateField("area_code", v)}
              errors={errors}
            />
          )}

          {currentStepId === "review" && (
            <ReviewStep
              fubConnected={fubConnected}
              fubName={fubName}
              calcomConnected={calcomConnected}
              calcomUsername={calcomUsername}
              bookingUrl={formData.calcom_booking_url}
              file={csvFile}
              rowCount={csvRowCount}
              fubImportCount={fubImportCount}
              areaCode={formData.area_code}
            />
          )}
        </WizardContainer>
      </div>
    </div>
  );
}
