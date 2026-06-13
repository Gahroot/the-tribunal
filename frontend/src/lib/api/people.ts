/**
 * People search + buying-signals API client (Apollo-style prospecting).
 *
 * Search named individuals across missions, filter by title/seniority/location
 * and buying signals (running ads, ad-tech, …), reveal + verify their email,
 * launch a web-people crawl, and bulk-add to an outbound mission. Types come
 * from the generated OpenAPI spec so they track the backend.
 */

import { apiPost } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

import type { Schemas } from "./_client";

export type PeopleSearchRequest = Schemas["PeopleSearchRequest"];
export type PeopleSearchResponse = Schemas["PeopleSearchResponse"];
export type PersonResult = Schemas["PersonResult"];
export type ProspectSignal = Schemas["ProspectSignalResponse"];
export type RevealEmailResponse = Schemas["RevealEmailResponse"];
export type RevealPhoneResponse = Schemas["RevealPhoneResponse"];
export type PeopleDiscoveryRequest = Schemas["PeopleDiscoveryRequest"];
export type PeopleDiscoveryJob = Schemas["PeopleDiscoveryResponse"];
export type AddToMissionRequest = Schemas["AddToMissionRequest"];
export type AddToMissionResponse = Schemas["AddToMissionResponse"];

export const peopleApi = {
  search: (
    workspaceId: string,
    request: PeopleSearchRequest,
  ): Promise<PeopleSearchResponse> =>
    apiPost<PeopleSearchResponse>(
      `/api/v1/workspaces/${workspaceId}/prospects/search`,
      request,
    ),

  revealEmail: (workspaceId: string, prospectId: string): Promise<RevealEmailResponse> =>
    apiPost<RevealEmailResponse>(
      `/api/v1/workspaces/${workspaceId}/prospects/${prospectId}/reveal-email`,
      {},
    ),

  revealPhone: (workspaceId: string, prospectId: string): Promise<RevealPhoneResponse> =>
    apiPost<RevealPhoneResponse>(
      `/api/v1/workspaces/${workspaceId}/prospects/${prospectId}/reveal-phone`,
      {},
    ),

  launchDiscovery: (
    workspaceId: string,
    request: PeopleDiscoveryRequest,
  ): Promise<PeopleDiscoveryJob> =>
    apiPost<PeopleDiscoveryJob>(
      `/api/v1/workspaces/${workspaceId}/prospects/people-discovery`,
      request,
    ),

  addToMission: (
    workspaceId: string,
    request: AddToMissionRequest,
  ): Promise<AddToMissionResponse> =>
    apiPost<AddToMissionResponse>(
      `/api/v1/workspaces/${workspaceId}/prospects/add-to-mission`,
      request,
    ),
};

/** React Query option presets for people-search reads. */
export const peopleQueryOptions = {
  search: (workspaceId: string, request: PeopleSearchRequest) => ({
    queryKey: queryKeys.people.search(workspaceId, {
      ...request,
    } as Record<string, unknown>),
    queryFn: () => peopleApi.search(workspaceId, request),
  }),
};
