import { createResourceHooks } from "@/lib/api/create-resource-hooks";
import { appointmentsApi, type UpdateAppointmentRequest } from "@/lib/api/appointments";
import type { Appointment } from "@/types";
import type { ApiClient } from "@/lib/api/create-api-client";

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

export { appointmentQueryKeys, useAppointments, useAppointment, useUpdateAppointment, useDeleteAppointment };
