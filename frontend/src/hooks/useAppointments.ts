import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  appointmentsApi,
  type CancelAppointmentRequest,
  type UpdateAppointmentRequest,
} from "@/lib/api/appointments";
import type { ApiClient } from "@/lib/api/create-api-client";
import { createResourceHooks } from "@/lib/api/create-resource-hooks";
import { getResourceInvalidationKeys } from "@/lib/query-keys";
import type { Appointment } from "@/types";

const {
  queryKeys: appointmentQueryKeys,
  useList: useAppointments,
  useGet: useAppointment,
  useUpdate: useUpdateAppointment,
  useDelete: useDeleteAppointment,
} = createResourceHooks({
  resourceKey: "appointments",
  apiClient: appointmentsApi as unknown as ApiClient<Appointment, never, UpdateAppointmentRequest>,
  includeCreate: false,
});

/** Provider-first cancel; invalidates appointment queries even on failure. */
function useCancelAppointment(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { id: number; data: CancelAppointmentRequest }) =>
      appointmentsApi.cancel(workspaceId, variables.id, variables.data),
    onSettled: () => {
      for (const key of getResourceInvalidationKeys("appointments", workspaceId)) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}

export {
  appointmentQueryKeys,
  useAppointments,
  useAppointment,
  useUpdateAppointment,
  useCancelAppointment,
  useDeleteAppointment,
};
