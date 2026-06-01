import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { appointmentsApi, type CreateAppointmentRequest } from "@/lib/api/appointments";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";

interface UseCreateAppointmentOptions {
  workspaceId: string | null | undefined;
  onSuccess?: () => void;
}

/**
 * Shared create-appointment mutation used by the calendar "New Appointment"
 * and contact "Schedule Appointment" dialogs. Handles workspace guarding,
 * cache invalidation, and success/error toasts.
 */
export function useCreateAppointment({
  workspaceId,
  onSuccess,
}: UseCreateAppointmentOptions) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateAppointmentRequest) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return appointmentsApi.create(workspaceId, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.appointments.all(workspaceId ?? ""),
      });
      toast.success("Appointment scheduled successfully!");
      onSuccess?.();
    },
    onError: (error) => {
      toast.error(
        getApiErrorMessage(error, "Failed to schedule appointment. Please try again."),
      );
    },
  });
}
