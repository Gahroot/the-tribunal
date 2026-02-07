import { createResourceHooks } from "@/lib/api/create-resource-hooks";
import { agentsApi, type AgentResponse, type CreateAgentRequest, type UpdateAgentRequest } from "@/lib/api/agents";
import type { ApiClient } from "@/lib/api/create-api-client";

const {
  queryKeys: agentQueryKeys,
  useList: useAgents,
  useGet: useAgent,
  useCreate: useCreateAgent,
  useUpdate: useUpdateAgent,
  useDelete: useDeleteAgent,
} = createResourceHooks({
  resourceKey: "agents",
  apiClient: agentsApi as ApiClient<AgentResponse, CreateAgentRequest, UpdateAgentRequest>,
});

export { agentQueryKeys, useAgents, useAgent, useCreateAgent, useUpdateAgent, useDeleteAgent };
