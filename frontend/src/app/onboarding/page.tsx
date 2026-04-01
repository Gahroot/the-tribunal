"use client";

import { useState, useRef, useCallback, useId } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  KeyRound,
  Link,
  Plug,
  Upload,
  Phone,
  Users,
  Rocket,
  CheckCircle2,
  Loader2,
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
} from "@/lib/api/realtor";

// ---- Step IDs ----

const STEPS = [
  { id: "calcom", label: "Connect Cal.com", icon: Link },
  { id: "leads", label: "Upload Leads", icon: Users },
  { id: "review", label: "Review & Launch", icon: Rocket },
] as const satisfies readonly WizardStepDef<string>[];

type StepId = (typeof STEPS)[number]["id"];

// ---- Wizard Form Data ----

interface OnboardingFormData {
  calcom_api_key: string;
  calcom_booking_url: string;
  area_code: string;
  // File is stored separately — not in the plain form data object
}

const INITIAL_FORM_DATA: OnboardingFormData = {
  calcom_api_key: "",
  calcom_booking_url: "",
  area_code: "",
};

// ---- Step 1: Connect Cal.com ----

interface CalcomStepProps {
  apiKey: string;
  bookingUrl: string;
  onApiKeyChange: (v: string) => void;
  onBookingUrlChange: (v: string) => void;
  errors: Record<string, string>;
}

function CalcomStep({
  apiKey,
  bookingUrl,
  onApiKeyChange,
  onBookingUrlChange,
  errors,
}: CalcomStepProps) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"success" | "error" | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const apiKeyId = useId();
  const urlId = useId();

  const handleTest = useCallback(async () => {
    if (!apiKey.trim()) {
      toast.error("Enter your Cal.com API key first.");
      return;
    }
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const result = await verifyCalcom(apiKey.trim());
      if (result.valid) {
        setTestResult("success");
        toast.success(
          result.username
            ? `Connected as @${result.username}`
            : "Cal.com connection verified!"
        );
      } else {
        setTestResult("error");
        setTestError("Invalid API key — please check and try again.");
      }
    } catch (err) {
      setTestResult("error");
      setTestError(getApiErrorMessage(err, "Connection test failed."));
    } finally {
      setTesting(false);
    }
  }, [apiKey]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Connect Your Cal.com Calendar</h2>
        <p className="text-muted-foreground mt-1">
          We&apos;ll book appointments directly on your calendar when leads are ready.
        </p>
      </div>

      <div className="space-y-4">
        {/* API Key */}
        <div className="space-y-2">
          <Label htmlFor={apiKeyId}>Cal.com API Key</Label>
          <div className="relative">
            <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
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

        {/* Booking URL */}
        <div className="space-y-2">
          <Label htmlFor={urlId}>Cal.com Booking URL</Label>
          <div className="relative">
            <Link className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <Input
              id={urlId}
              type="url"
              placeholder="https://cal.com/yourname/30min"
              value={bookingUrl}
              onChange={(e) => onBookingUrlChange(e.target.value)}
              className="pl-9"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Paste your Cal.com booking page URL. We&apos;ll extract the event type automatically.
          </p>
          {errors.calcom_booking_url && (
            <p className="text-sm text-destructive">{errors.calcom_booking_url}</p>
          )}
        </div>

        {/* Test Connection */}
        <div className="flex items-center gap-3 pt-1">
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

          {testResult === "success" && (
            <Badge
              variant="outline"
              className="text-green-600 border-green-500 gap-1"
            >
              <CheckCircle2 className="size-3.5" />
              Connected
            </Badge>
          )}

          {testResult === "error" && testError && (
            <p className="text-sm text-destructive">{testError}</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- Step 2: Upload Leads ----

interface LeadsStepProps {
  file: File | null;
  rowCount: number | null;
  areaCode: string;
  onFileChange: (file: File | null, rows: number | null) => void;
  onAreaCodeChange: (v: string) => void;
  errors: Record<string, string>;
}

function LeadsStep({
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
        // Estimate rows: count newlines, subtract 1 for header
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
        <h2 className="text-2xl font-bold">Upload Your Lead List</h2>
        <p className="text-muted-foreground mt-1">
          We&apos;ll text your leads, qualify them, and book appointments — all automatically.
        </p>
      </div>

      <div className="space-y-4">
        {/* Dropzone */}
        <div
          role="button"
          tabIndex={0}
          aria-label="Upload CSV file"
          className={`border-2 border-dashed rounded-lg p-10 flex flex-col items-center justify-center gap-3 cursor-pointer transition-colors ${
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

        {/* File info after selection */}
        {file && (
          <Card className="bg-muted/30">
            <CardContent className="py-3 px-4 flex items-center gap-3">
              <CheckCircle2 className="size-4 text-green-500 shrink-0" />
              <div className="min-w-0">
                <p className="font-medium truncate text-sm">{file.name}</p>
                {rowCount !== null && (
                  <p className="text-xs text-muted-foreground">
                    ~{rowCount.toLocaleString()} lead{rowCount !== 1 ? "s" : ""} detected
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {errors.csv_file && (
          <p className="text-sm text-destructive">{errors.csv_file}</p>
        )}

        {/* Column hint */}
        <p className="text-xs text-muted-foreground">
          Your CSV needs at least:{" "}
          <span className="font-mono font-medium">first_name</span> (or{" "}
          <span className="font-mono font-medium">name</span>),{" "}
          <span className="font-mono font-medium">phone</span>. Email is optional.
        </p>

        {/* Area code */}
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
            Preferred area code for your texting number (e.g. 212). Leave blank for any
            US number.
          </p>
        </div>
      </div>
    </div>
  );
}

// ---- Step 3: Review & Launch ----

interface ReviewStepProps {
  bookingUrl: string;
  file: File | null;
  rowCount: number | null;
  areaCode: string;
}

function ReviewStep({ bookingUrl, file, rowCount, areaCode }: ReviewStepProps) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Ready to Launch 🚀</h2>
        <p className="text-muted-foreground mt-1">
          Review your setup and launch your lead reactivation campaign.
        </p>
      </div>

      <Card>
        <CardContent className="pt-4 pb-4 divide-y divide-border">
          {/* Cal.com */}
          <div className="flex items-center gap-3 py-3">
            <CheckCircle2 className="size-5 text-green-500 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium">Cal.com connected</p>
              {bookingUrl && (
                <p className="text-xs text-muted-foreground truncate">{bookingUrl}</p>
              )}
            </div>
          </div>

          {/* CSV */}
          <div className="flex items-center gap-3 py-3">
            <Users className="size-5 text-muted-foreground shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {file ? file.name : "No file selected"}
              </p>
              {rowCount !== null && (
                <p className="text-xs text-muted-foreground">
                  ~{rowCount.toLocaleString()} lead{rowCount !== 1 ? "s" : ""} to contact
                </p>
              )}
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

  // CSV file state (separate from form data — File objects can't live in plain state easily)
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvRowCount, setCsvRowCount] = useState<number | null>(null);

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
        if (!csvFile) {
          errs.csv_file = "Please upload a CSV file with your leads.";
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
      // Clear file error when a file is picked
      if (file) {
        setErrors((prev) => {
          const next = { ...prev };
          delete next.csv_file;
          return next;
        });
      }
    },
    [setErrors]
  );

  const handleLaunch = useCallback(async () => {
    if (!csvFile) {
      toast.error("Please upload a CSV file first.");
      return;
    }
    if (!currentWorkspaceId) {
      toast.error("No workspace found. Please log in again.");
      return;
    }

    setIsSubmitting(true);
    try {
      // 1. Parse the Cal.com booking URL to extract event type ID
      const { event_type_id } = await parseCalcomUrl(formData.calcom_booking_url);

      // 2. Run onboarding: creates agent + phone number
      await onboard({
        calcom_api_key: formData.calcom_api_key,
        calcom_event_type_id: event_type_id,
      });

      // 3. Create campaign from CSV
      await createCampaignFromCsv(currentWorkspaceId, csvFile, {
        skipDuplicates: true,
        areaCode: formData.area_code || undefined,
      });

      toast.success("Campaign launched! Your leads are being contacted.");
      router.push("/realtor-dashboard");
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Launch failed. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  }, [csvFile, currentWorkspaceId, formData, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-2xl border rounded-xl overflow-hidden shadow-xl bg-card h-[640px] flex flex-col">
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
          {currentStepId === "calcom" && (
            <CalcomStep
              apiKey={formData.calcom_api_key}
              bookingUrl={formData.calcom_booking_url}
              onApiKeyChange={(v) => updateField("calcom_api_key", v)}
              onBookingUrlChange={(v) => updateField("calcom_booking_url", v)}
              errors={errors}
            />
          )}

          {currentStepId === "leads" && (
            <LeadsStep
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
              bookingUrl={formData.calcom_booking_url}
              file={csvFile}
              rowCount={csvRowCount}
              areaCode={formData.area_code}
            />
          )}
        </WizardContainer>
      </div>
    </div>
  );
}
