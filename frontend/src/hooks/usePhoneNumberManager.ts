"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import {
  phoneNumbersApi,
  type PhoneNumberSearchResult,
  type PhoneNumberTelephonyStatus,
} from "@/lib/api/phone-numbers";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorCode, getApiErrorMessage } from "@/lib/utils/errors";
import type { PhoneNumber } from "@/types";

export interface UsePhoneNumberManagerResult {
  phoneNumbers: PhoneNumber[];
  isLoadingNumbers: boolean;
  numbersError: unknown;
  telephonyStatus: PhoneNumberTelephonyStatus | null;
  isLoadingTelephonyStatus: boolean;
  telephonyStatusError: unknown;
  isTelephonyUnavailable: boolean;
  country: string;
  setCountry: (country: string) => void;
  areaCode: string;
  setAreaCode: (areaCode: string) => void;
  searchResults: PhoneNumberSearchResult[];
  hasSearched: boolean;
  isSearching: boolean;
  isPurchasing: boolean;
  isSyncing: boolean;
  handleSearch: (event: React.FormEvent) => void;
  purchase: (phoneNumber: string) => void;
  release: (phoneNumberId: string) => void;
  sync: () => void;
}

type ApiErrorWithDetails = {
  response?: {
    data?: {
      details?: {
        action_label?: unknown;
        action_href?: unknown;
      };
    };
  };
};

function telephonyStatusFromUnavailableError(error: unknown): PhoneNumberTelephonyStatus | null {
  if (getApiErrorCode(error) !== "telephony_unavailable") {
    return null;
  }

  const details = (error as ApiErrorWithDetails).response?.data?.details;
  return {
    enabled: false,
    provider: "telnyx",
    message: getApiErrorMessage(error, "Telephony is not enabled for this workspace."),
    action_label: typeof details?.action_label === "string" ? details.action_label : null,
    action_href: typeof details?.action_href === "string" ? details.action_href : null,
  };
}

/**
 * Container hook for {@link PhoneNumbersTable}: owns the owned-numbers query and
 * the search / purchase / release / sync mutations plus the search form state,
 * so the table itself can stay presentational across its `section`/`page`
 * variants.
 */
export function usePhoneNumberManager(): UsePhoneNumberManagerResult {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  const [country, setCountry] = useState("US");
  const [areaCode, setAreaCode] = useState("");
  const [searchResults, setSearchResults] = useState<PhoneNumberSearchResult[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [telephonyUnavailableOverride, setTelephonyUnavailableOverride] =
    useState<PhoneNumberTelephonyStatus | null>(null);

  const invalidatePhoneNumbers = () =>
    queryClient.invalidateQueries({
      queryKey: queryKeys.phoneNumbers.all(workspaceId ?? ""),
    });

  const {
    data: phoneNumbersData,
    isPending: isLoadingNumbers,
    error: numbersError,
  } = useQuery({
    queryKey: queryKeys.phoneNumbers.activeOnlyFalse(workspaceId ?? ""),
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return phoneNumbersApi.list(workspaceId, { active_only: false });
    },
    enabled: !!workspaceId,
  });

  const {
    data: queriedTelephonyStatus,
    isPending: isLoadingTelephonyStatus,
    error: telephonyStatusError,
  } = useQuery({
    queryKey: queryKeys.phoneNumbers.telephonyStatus(workspaceId ?? ""),
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return phoneNumbersApi.getTelephonyStatus(workspaceId);
    },
    enabled: !!workspaceId,
  });

  const telephonyStatus = telephonyUnavailableOverride ?? queriedTelephonyStatus ?? null;
  const isTelephonyUnavailable = telephonyStatus?.enabled === false;

  const handleTelephonyMutationError = (error: unknown, fallback: string) => {
    const unavailableStatus = telephonyStatusFromUnavailableError(error);
    if (unavailableStatus) {
      setTelephonyUnavailableOverride(unavailableStatus);
    }
    toast.error(getApiErrorMessage(error, fallback));
  };

  const searchMutation = useMutation({
    mutationFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      if (isTelephonyUnavailable) {
        throw new Error(telephonyStatus?.message ?? "Telephony is not enabled for this workspace.");
      }
      return phoneNumbersApi.search(workspaceId, {
        country,
        area_code: areaCode || undefined,
        limit: 10,
      });
    },
    onSuccess: (data) => {
      setSearchResults(data);
      setHasSearched(true);
      if (data.length === 0) {
        toast.info("No numbers found matching your criteria");
      }
    },
    onError: (error: unknown) => {
      handleTelephonyMutationError(error, "Failed to search for numbers");
      setSearchResults([]);
      setHasSearched(true);
    },
  });

  const purchaseMutation = useMutation({
    mutationFn: (phoneNumber: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      if (isTelephonyUnavailable) {
        throw new Error(telephonyStatus?.message ?? "Telephony is not enabled for this workspace.");
      }
      return phoneNumbersApi.purchase(workspaceId, {
        phone_number: phoneNumber,
      });
    },
    onSuccess: (data) => {
      toast.success(`Successfully purchased ${data.phone_number}`);
      void invalidatePhoneNumbers();
      setSearchResults((prev) => prev.filter((r) => r.phone_number !== data.phone_number));
    },
    onError: (error: unknown) => {
      handleTelephonyMutationError(error, "Failed to purchase number");
    },
  });

  const releaseMutation = useMutation({
    mutationFn: (phoneNumberId: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return phoneNumbersApi.release(workspaceId, phoneNumberId);
    },
    onSuccess: () => {
      toast.success("Phone number released successfully");
      void invalidatePhoneNumbers();
    },
    onError: (error: unknown) => {
      handleTelephonyMutationError(error, "Failed to release number");
    },
  });

  const syncMutation = useMutation({
    mutationFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      if (isTelephonyUnavailable) {
        throw new Error(telephonyStatus?.message ?? "Telephony is not enabled for this workspace.");
      }
      return phoneNumbersApi.sync(workspaceId);
    },
    onSuccess: (data) => {
      if (data.synced > 0) {
        toast.success(`Synced ${data.synced} phone number(s) from Telnyx`);
      } else {
        toast.info("No new phone numbers to sync");
      }
      void invalidatePhoneNumbers();
    },
    onError: (error: unknown) => {
      handleTelephonyMutationError(error, "Failed to sync phone numbers");
    },
  });

  const phoneNumbers = Array.isArray(phoneNumbersData?.items) ? phoneNumbersData.items : [];

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    if (isTelephonyUnavailable) {
      return;
    }
    searchMutation.mutate();
  };

  return {
    phoneNumbers,
    isLoadingNumbers,
    numbersError,
    telephonyStatus,
    isLoadingTelephonyStatus,
    telephonyStatusError,
    isTelephonyUnavailable,
    country,
    setCountry,
    areaCode,
    setAreaCode,
    searchResults,
    hasSearched,
    isSearching: searchMutation.isPending,
    isPurchasing: purchaseMutation.isPending,
    isSyncing: syncMutation.isPending,
    handleSearch,
    purchase: (phoneNumber) => {
      if (!isTelephonyUnavailable) purchaseMutation.mutate(phoneNumber);
    },
    release: (phoneNumberId) => releaseMutation.mutate(phoneNumberId),
    sync: () => {
      if (!isTelephonyUnavailable) syncMutation.mutate();
    },
  };
}
