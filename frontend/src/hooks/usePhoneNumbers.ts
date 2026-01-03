import { useQuery } from "@tanstack/react-query";
import { phoneNumbersApi, type PhoneNumbersListParams } from "@/lib/api/phone-numbers";

/**
 * Fetch and manage a list of phone numbers for a workspace
 */
export function usePhoneNumbers(workspaceId: string, params: PhoneNumbersListParams = {}) {
  return useQuery({
    queryKey: ["phone-numbers", workspaceId, params],
    queryFn: () => phoneNumbersApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single phone number by ID
 */
export function usePhoneNumber(workspaceId: string, phoneNumberId: string) {
  return useQuery({
    queryKey: ["phoneNumber", workspaceId, phoneNumberId],
    queryFn: () => phoneNumbersApi.get(workspaceId, phoneNumberId),
    enabled: !!workspaceId && !!phoneNumberId,
  });
}
