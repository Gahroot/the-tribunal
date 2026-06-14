"use client";

import {
  AlertCircle,
  Check,
  Loader2,
  MessageSquare,
  Mic,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import Link from "next/link";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageEmptyState, PageErrorState, PageLoadingState } from "@/components/ui/page-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PhoneNumberSearchResult, PhoneNumberTelephonyStatus } from "@/lib/api/phone-numbers";
import { formatPhoneNumber } from "@/lib/utils/phone";
import type { PhoneNumber } from "@/types";

export type PhoneNumbersTableVariant = "section" | "page";

const COUNTRIES = [
  { code: "US", name: "United States" },
  { code: "CA", name: "Canada" },
  { code: "GB", name: "United Kingdom" },
  { code: "AU", name: "Australia" },
];

const DEFAULT_TELEPHONY_ACTION_LABEL = "Open integrations settings";
const DEFAULT_TELEPHONY_ACTION_HREF = "/settings?tab=integrations";

function getTelephonyAction(status: PhoneNumberTelephonyStatus | null) {
  return {
    label: status?.action_label || DEFAULT_TELEPHONY_ACTION_LABEL,
    href: status?.action_href || DEFAULT_TELEPHONY_ACTION_HREF,
  };
}

export function TelephonyUnavailableNotice({
  variant,
  status,
}: {
  variant: PhoneNumbersTableVariant;
  status: PhoneNumberTelephonyStatus | null;
}) {
  const action = getTelephonyAction(status);

  return (
    <Alert className={variant === "section" ? "text-left" : undefined}>
      <AlertCircle className="size-4" />
      <AlertTitle>Telephony is not enabled</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>
          {status?.message || "Ask an admin to connect Telnyx before adding SMS or voice numbers."}
        </p>
        <Button asChild variant="outline" size="sm">
          <Link href={action.href}>{action.label}</Link>
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export function SyncFromTelnyxButton({
  variant,
  isSyncing,
  disabled = false,
  onSync,
}: {
  variant: PhoneNumbersTableVariant;
  isSyncing: boolean;
  disabled?: boolean;
  onSync: () => void;
}) {
  return (
    <Button
      variant={variant === "section" ? "outline" : "default"}
      size={variant === "section" ? "sm" : "default"}
      onClick={onSync}
      disabled={disabled || isSyncing}
    >
      {isSyncing ? (
        <Loader2 className="mr-2 size-4 animate-spin" />
      ) : (
        <RefreshCw className="mr-2 size-4" />
      )}
      Sync from Telnyx
    </Button>
  );
}

export function ReleaseNumberDialog({
  number,
  trigger,
  onRelease,
}: {
  number: PhoneNumber;
  trigger: React.ReactNode;
  onRelease: (phoneNumberId: string) => void;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Release Phone Number</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to release {formatPhoneNumber(number.phone_number)}? This action
            cannot be undone and you may not be able to get this number back.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={() => onRelease(number.id)}
          >
            Release Number
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export function SearchNumbersForm({
  variant,
  country,
  onCountryChange,
  areaCode,
  onAreaCodeChange,
  isSearching,
  disabled = false,
  onSubmit,
}: {
  variant: PhoneNumbersTableVariant;
  country: string;
  onCountryChange: (country: string) => void;
  areaCode: string;
  onAreaCodeChange: (areaCode: string) => void;
  isSearching: boolean;
  disabled?: boolean;
  onSubmit: (event: React.FormEvent) => void;
}) {
  return (
    <form onSubmit={onSubmit} className="flex gap-3">
      <div className={variant === "section" ? "w-40" : "w-48"}>
        <Label htmlFor="country" className="sr-only">
          Country
        </Label>
        <Select value={country} onValueChange={onCountryChange} disabled={disabled}>
          <SelectTrigger id="country">
            <SelectValue placeholder="Country" />
          </SelectTrigger>
          <SelectContent>
            {COUNTRIES.map((c) => (
              <SelectItem key={c.code} value={c.code}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className={variant === "section" ? "flex-1" : "flex-1 max-w-xs"}>
        <Label htmlFor="areaCode" className="sr-only">
          Area Code
        </Label>
        <Input
          id="areaCode"
          placeholder="Area code (optional, e.g. 415)"
          value={areaCode}
          onChange={(e) => onAreaCodeChange(e.target.value)}
          maxLength={3}
          disabled={disabled || isSearching}
        />
      </div>
      <Button type="submit" disabled={disabled || isSearching}>
        {isSearching ? (
          <Loader2 className="mr-2 size-4 animate-spin" />
        ) : (
          <Search className="mr-2 size-4" />
        )}
        Search
      </Button>
    </form>
  );
}

export function OwnedNumbersContent({
  variant,
  phoneNumbers,
  isLoading,
  hasError,
  telephonyStatus,
  isTelephonyUnavailable,
  onRelease,
}: {
  variant: PhoneNumbersTableVariant;
  phoneNumbers: PhoneNumber[];
  isLoading: boolean;
  hasError: boolean;
  telephonyStatus: PhoneNumberTelephonyStatus | null;
  isTelephonyUnavailable: boolean;
  onRelease: (phoneNumberId: string) => void;
}) {
  if (isLoading) {
    return <PageLoadingState className={variant === "section" ? "min-h-0 py-8" : undefined} />;
  }

  if (hasError) {
    return (
      <PageErrorState
        message="Failed to load phone numbers"
        className={variant === "section" ? "min-h-0 py-8" : undefined}
      />
    );
  }

  if (phoneNumbers.length === 0) {
    if (isTelephonyUnavailable) {
      const action = getTelephonyAction(telephonyStatus);
      return (
        <PageEmptyState
          icon={<Phone className={variant === "section" ? "size-8" : "size-12"} />}
          title="Telephony is not enabled"
          description={
            telephonyStatus?.message ||
            "Ask an admin to connect Telnyx before adding SMS or voice numbers."
          }
          action={
            <Button asChild variant="outline" size="sm">
              <Link href={action.href}>{action.label}</Link>
            </Button>
          }
          className={
            variant === "section"
              ? "min-h-0 border rounded-lg border-dashed py-8"
              : "border rounded-lg border-dashed"
          }
        />
      );
    }

    if (variant === "section") {
      return (
        <div className="text-center py-8 border rounded-lg border-dashed">
          <Phone className="size-8 mx-auto text-muted-foreground mb-2" />
          <p className="text-sm text-muted-foreground">
            No phone numbers yet. Search and purchase one below.
          </p>
        </div>
      );
    }
    return (
      <PageEmptyState
        icon={<Phone className="size-12" />}
        title="No phone numbers yet"
        description="Search and purchase a number below, or sync existing numbers from your Telnyx account."
        className="border rounded-lg border-dashed"
      />
    );
  }

  if (variant === "section") {
    return (
      <div className="space-y-2">
        {phoneNumbers.map((number) => (
          <div key={number.id} className="flex items-center justify-between p-3 rounded-lg border">
            <div className="flex items-center gap-3">
              <div className="flex size-8 items-center justify-center rounded-full bg-green-500/10">
                <Phone className="size-4 text-green-500" />
              </div>
              <div>
                <p className="font-medium">{formatPhoneNumber(number.phone_number)}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  {number.friendly_name && (
                    <span className="text-xs text-muted-foreground">{number.friendly_name}</span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                {number.sms_enabled && (
                  <Badge
                    variant="outline"
                    className="bg-blue-500/10 text-blue-500 border-blue-500/20"
                  >
                    <MessageSquare className="size-3 mr-1" />
                    SMS
                  </Badge>
                )}
                {number.voice_enabled && (
                  <Badge
                    variant="outline"
                    className="bg-purple-500/10 text-purple-500 border-purple-500/20"
                  >
                    <Mic className="size-3 mr-1" />
                    Voice
                  </Badge>
                )}
              </div>
              {number.assigned_agent_id && <Badge variant="secondary">Assigned to Agent</Badge>}
              <ReleaseNumberDialog
                number={number}
                onRelease={onRelease}
                trigger={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                }
              />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Phone Number</TableHead>
          <TableHead>Label</TableHead>
          <TableHead>Capabilities</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {phoneNumbers.map((number) => (
          <TableRow key={number.id}>
            <TableCell className="font-medium">{formatPhoneNumber(number.phone_number)}</TableCell>
            <TableCell>
              {number.friendly_name || <span className="text-muted-foreground">-</span>}
            </TableCell>
            <TableCell>
              <div className="flex items-center gap-1.5">
                {number.sms_enabled && (
                  <Badge
                    variant="outline"
                    className="bg-blue-500/10 text-blue-600 border-blue-500/20"
                  >
                    <MessageSquare className="size-3 mr-1" />
                    SMS
                  </Badge>
                )}
                {number.voice_enabled && (
                  <Badge
                    variant="outline"
                    className="bg-purple-500/10 text-purple-600 border-purple-500/20"
                  >
                    <Mic className="size-3 mr-1" />
                    Voice
                  </Badge>
                )}
              </div>
            </TableCell>
            <TableCell>
              {number.is_active ? (
                <Badge className="bg-green-500/10 text-green-600 border-green-500/20">Active</Badge>
              ) : (
                <Badge variant="secondary">Inactive</Badge>
              )}
            </TableCell>
            <TableCell className="text-right">
              <ReleaseNumberDialog
                number={number}
                onRelease={onRelease}
                trigger={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                }
              />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function SearchResultsContent({
  variant,
  hasSearched,
  searchResults,
  isPurchasing,
  onPurchase,
}: {
  variant: PhoneNumbersTableVariant;
  hasSearched: boolean;
  searchResults: PhoneNumberSearchResult[];
  isPurchasing: boolean;
  onPurchase: (phoneNumber: string) => void;
}) {
  if (!hasSearched) return null;

  return (
    <div className={variant === "section" ? "space-y-2" : "space-y-4"}>
      {searchResults.length === 0 ? (
        <div
          className={`text-center ${variant === "section" ? "py-6" : "py-8"} border rounded-lg border-dashed`}
        >
          <p
            className={
              variant === "section" ? "text-sm text-muted-foreground" : "text-muted-foreground"
            }
          >
            No available numbers found. Try a different area code.
          </p>
        </div>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {searchResults.length} number(s) available
          </p>
          <div
            className={
              variant === "section"
                ? "space-y-2 max-h-64 overflow-y-auto"
                : "grid gap-3 md:grid-cols-2"
            }
          >
            {searchResults.map((result) => (
              <div
                key={result.id}
                className={`flex items-center justify-between ${variant === "section" ? "p-3" : "p-4"} rounded-lg border bg-muted/30`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`flex ${variant === "section" ? "size-8" : "size-10"} items-center justify-center rounded-full bg-primary/10`}
                  >
                    <Phone
                      className={`${variant === "section" ? "size-4" : "size-5"} text-primary`}
                    />
                  </div>
                  <div>
                    <p className="font-medium">{formatPhoneNumber(result.phone_number)}</p>
                    <div
                      className={`flex items-center ${variant === "section" ? "gap-1.5" : "gap-2"} mt-0.5`}
                    >
                      {result.capabilities?.sms && (
                        <span className="text-xs text-muted-foreground flex items-center gap-0.5">
                          <Check className="size-3 text-green-500" />
                          SMS
                        </span>
                      )}
                      {result.capabilities?.voice && (
                        <span className="text-xs text-muted-foreground flex items-center gap-0.5">
                          <Check className="size-3 text-green-500" />
                          Voice
                        </span>
                      )}
                      {result.capabilities?.mms && (
                        <span className="text-xs text-muted-foreground flex items-center gap-0.5">
                          <Check className="size-3 text-green-500" />
                          MMS
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <Button
                  size="sm"
                  onClick={() => onPurchase(result.phone_number)}
                  disabled={isPurchasing}
                >
                  {isPurchasing ? (
                    <Loader2 className="mr-2 size-4 animate-spin" />
                  ) : (
                    <Plus className="mr-2 size-4" />
                  )}
                  Purchase
                </Button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
