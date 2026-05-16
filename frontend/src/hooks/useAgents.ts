import { agentsApi, type Agent, type CreateAgentRequest, type UpdateAgentRequest } from "@/lib/api/agents";
import type { ApiClient } from "@/lib/api/create-api-client";
import { createResourceHooks } from "@/lib/api/create-resource-hooks";

const {
  queryKeys: agentQueryKeys,
  useList: useAgents,
  useGet: useAgent,
  useCreate: useCreateAgent,
  useUpdate: useUpdateAgent,
  useDelete: useDeleteAgent,
} = createResourceHooks({
  resourceKey: "agents",
  apiClient: agentsApi as ApiClient<Agent, CreateAgentRequest, UpdateAgentRequest>,
});

export { agentQueryKeys, useAgents, useAgent, useCreateAgent, useUpdateAgent, useDeleteAgent };
