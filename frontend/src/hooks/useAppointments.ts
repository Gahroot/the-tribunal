import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { appointmentsApi, type AppointmentsListParams, type UpdateAppointmentRequest } from "@/lib/api/appointments";
import type { Appointment } from "@/types";

/**
 * Fetch and manage a list of appointments for a workspace
 */
export function useAppointments(workspaceId: string, params: AppointmentsListParams = {}) {
  return useQuery({
    queryKey: ["appointments", workspaceId, params],
    queryFn: () => appointmentsApi.list(workspaceId, params),
    enabled: !!workspaceId,
  });
}

/**
 * Fetch a single appointment by ID
 */
export function useAppointment(workspaceId: string, appointmentId: number) {
  return useQuery({
    queryKey: ["appointment", workspaceId, appointmentId],
    queryFn: () => appointmentsApi.get(workspaceId, appointmentId),
    enabled: !!workspaceId && !!appointmentId,
  });
}

/**
 * Update an appointment
 */
export function useUpdateAppointment(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { appointmentId: number; data: UpdateAppointmentRequest }) =>
      appointmentsApi.update(workspaceId, variables.appointmentId, variables.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["appointments", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["appointment"] });
    },
  });
}

/**
 * Delete/cancel an appointment
 */
export function useDeleteAppointment(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (appointmentId: number) =>
      appointmentsApi.delete(workspaceId, appointmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["appointments", workspaceId] });
    },
  });
}
