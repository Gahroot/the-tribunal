import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";
import type {
  CreatePersonaRequest,
  CreateRehearsalRequest,
  ProspectPersona,
  RehearsalRun,
  RehearsalRunSummary,
} from "@/types/roleplay";

const base = (workspaceId: string) =>
  `/api/v1/workspaces/${workspaceId}/roleplay`;

export const roleplayApi = {
  // === Personas ===
  listPersonas: (workspaceId: string): Promise<ProspectPersona[]> =>
    apiGet<ProspectPersona[]>(`${base(workspaceId)}/personas`),

  getPersona: (workspaceId: string, personaId: string): Promise<ProspectPersona> =>
    apiGet<ProspectPersona>(`${base(workspaceId)}/personas/${personaId}`),

  createPersona: (
    workspaceId: string,
    data: CreatePersonaRequest,
  ): Promise<ProspectPersona> =>
    apiPost<ProspectPersona>(`${base(workspaceId)}/personas`, data),

  updatePersona: (
    workspaceId: string,
    personaId: string,
    data: Partial<CreatePersonaRequest>,
  ): Promise<ProspectPersona> =>
    apiPut<ProspectPersona>(`${base(workspaceId)}/personas/${personaId}`, data),

  deletePersona: (workspaceId: string, personaId: string): Promise<void> =>
    apiDelete(`${base(workspaceId)}/personas/${personaId}`),

  // === Rehearsal runs ===
  listRuns: (
    workspaceId: string,
    params?: { agent_id?: string; limit?: number },
  ): Promise<RehearsalRunSummary[]> =>
    apiGet<RehearsalRunSummary[]>(`${base(workspaceId)}/runs`, { params }),

  getRun: (workspaceId: string, runId: string): Promise<RehearsalRun> =>
    apiGet<RehearsalRun>(`${base(workspaceId)}/runs/${runId}`),

  createRun: (
    workspaceId: string,
    data: CreateRehearsalRequest,
  ): Promise<RehearsalRun> =>
    apiPost<RehearsalRun>(`${base(workspaceId)}/runs`, data),

  advanceTurn: (
    workspaceId: string,
    runId: string,
    message: string,
  ): Promise<RehearsalRun> =>
    apiPost<RehearsalRun>(`${base(workspaceId)}/runs/${runId}/turn`, { message }),

  scoreRun: (workspaceId: string, runId: string): Promise<RehearsalRun> =>
    apiPost<RehearsalRun>(`${base(workspaceId)}/runs/${runId}/score`),

  deleteRun: (workspaceId: string, runId: string): Promise<void> =>
    apiDelete(`${base(workspaceId)}/runs/${runId}`),
};
