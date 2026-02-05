/**
 * Generic API client factory that generates CRUD methods for workspace-scoped resources.
 * Eliminates duplicate boilerplate across API clients.
 */

import api from "@/lib/api";
import type { PaginatedResponse, ResourceId } from "@/types/api";

// Re-export ResourceId for convenience
export type { ResourceId };

/**
 * Options for creating a generic API client.
 */
export interface CreateApiClientOptions<T, CreateData, UpdateData> {
  /**
   * The resource path (e.g., "tags", "segments").
   * Will be appended to `/api/v1/workspaces/{workspaceId}/` for workspace-scoped resources.
   */
  resourcePath: string;

  /**
   * Whether this resource is workspace-scoped (default: true).
   * When false, uses `/api/v1/{resourcePath}` instead.
   */
  workspaceScoped?: boolean;

  /**
   * Optional transform function to convert raw API responses to domain types.
   * Useful for handling backend response formats that differ from frontend types.
   */
  transform?: (raw: unknown) => T;

  /**
   * Optional transform function for list responses.
   * If not provided, uses the default `transform` if available.
   */
  transformList?: (raw: unknown) => PaginatedResponse<T>;

  /**
   * Whether to include get operation. Default: true.
   */
  includeGet?: boolean;

  /**
   * Whether to include create operation. Default: true.
   */
  includeCreate?: boolean;

  /**
   * Whether to include update operation. Default: true.
   */
  includeUpdate?: boolean;

  /**
   * Whether to include delete operation. Default: true.
   */
  includeDelete?: boolean;
}

/**
 * Standard CRUD API client interface.
 */
export interface ApiClient<T, CreateData, UpdateData> {
  list: (workspaceId: string, params?: Record<string, unknown>) => Promise<PaginatedResponse<T>>;
  get?: (workspaceId: string, id: ResourceId) => Promise<T>;
  create?: (workspaceId: string, data: CreateData) => Promise<T>;
  update?: (workspaceId: string, id: ResourceId, data: UpdateData) => Promise<T>;
  delete?: (workspaceId: string, id: ResourceId) => Promise<void>;
}

/**
 * Full CRUD API client with all methods required (non-optional).
 * Returned when all CRUD operations are included.
 */
export interface FullApiClient<T, CreateData, UpdateData> {
  list: (workspaceId: string, params?: Record<string, unknown>) => Promise<PaginatedResponse<T>>;
  get: (workspaceId: string, id: ResourceId) => Promise<T>;
  create: (workspaceId: string, data: CreateData) => Promise<T>;
  update: (workspaceId: string, id: ResourceId, data: UpdateData) => Promise<T>;
  delete: (workspaceId: string, id: ResourceId) => Promise<void>;
}

/**
 * Creates a generic API client with standard CRUD operations for a workspace-scoped resource.
 *
 * @example
 * ```ts
 * const baseApi = createApiClient<Tag, CreateTagRequest, UpdateTagRequest>({
 *   resourcePath: "tags"
 * });
 *
 * export const tagsApi = {
 *   ...baseApi,
 *   bulkTag: async (workspaceId, data) => { ... }
 * };
 * ```
 */
export function createApiClient<T, CreateData = Partial<T>, UpdateData = Partial<T>>(
  options: CreateApiClientOptions<T, CreateData, UpdateData>
): ApiClient<T, CreateData, UpdateData>;
export function createApiClient<T, CreateData = Partial<T>, UpdateData = Partial<T>>(
  options: Omit<CreateApiClientOptions<T, CreateData, UpdateData>, "includeGet" | "includeCreate" | "includeUpdate" | "includeDelete">
): FullApiClient<T, CreateData, UpdateData>;
export function createApiClient<T, CreateData = Partial<T>, UpdateData = Partial<T>>(
  options: CreateApiClientOptions<T, CreateData, UpdateData>
): ApiClient<T, CreateData, UpdateData> | FullApiClient<T, CreateData, UpdateData> {
  const {
    resourcePath,
    workspaceScoped = true,
    transform,
    transformList,
    includeGet = true,
    includeCreate = true,
    includeUpdate = true,
    includeDelete = true,
  } = options;

  // Build the base URL path
  const buildPath = (suffix?: string): string => {
    if (workspaceScoped) {
      return `/api/v1/workspaces/:workspaceId/${resourcePath}${suffix ?? ""}`;
    }
    return `/api/v1/${resourcePath}${suffix ?? ""}`;
  };

  // Apply transform if available
  const applyTransform = (data: unknown): T => {
    if (transform) {
      return transform(data);
    }
    return data as T;
  };

  const applyListTransform = (data: unknown): PaginatedResponse<T> => {
    if (transformList) {
      return transformList(data);
    }
    if (transform) {
      const response = data as PaginatedResponse<unknown>;
      return {
        ...response,
        items: response.items.map(applyTransform),
      };
    }
    return data as PaginatedResponse<T>;
  };

  const client: ApiClient<T, CreateData, UpdateData> = {
    list: async (workspaceId: string, params: Record<string, unknown> = {}): Promise<PaginatedResponse<T>> => {
      const path = buildPath().replace(":workspaceId", workspaceId);
      const response = await api.get(path, { params });
      return applyListTransform(response.data);
    },

    ...(includeGet
      ? {
          get: async (workspaceId: string, id: ResourceId): Promise<T> => {
            const path = buildPath(`/:id`).replace(":workspaceId", workspaceId).replace(":id", String(id));
            const response = await api.get(path);
            return applyTransform(response.data);
          },
        }
      : {}),

    ...(includeCreate
      ? {
          create: async (workspaceId: string, data: CreateData): Promise<T> => {
            const path = buildPath().replace(":workspaceId", workspaceId);
            const response = await api.post(path, data);
            return applyTransform(response.data);
          },
        }
      : {}),

    ...(includeUpdate
      ? {
          update: async (workspaceId: string, id: ResourceId, data: UpdateData): Promise<T> => {
            const path = buildPath(`/:id`).replace(":workspaceId", workspaceId).replace(":id", String(id));
            const response = await api.put(path, data);
            return applyTransform(response.data);
          },
        }
      : {}),

    ...(includeDelete
      ? {
          delete: async (workspaceId: string, id: ResourceId): Promise<void> => {
            const path = buildPath(`/:id`).replace(":workspaceId", workspaceId).replace(":id", String(id));
            await api.delete(path);
          },
        }
      : {}),
  };

  return client;
}

/**
 * Creates a generic API client for non-workspace-scoped resources.
 *
 * @example
 * ```ts
 * const baseApi = createNonWorkspaceApiClient<User, CreateUserRequest, UpdateUserRequest>({
 *   resourcePath: "users"
 * });
 * ```
 */
export function createNonWorkspaceApiClient<T, CreateData = Partial<T>, UpdateData = Partial<T>>(
  options: Omit<CreateApiClientOptions<T, CreateData, UpdateData>, "workspaceScoped">
): ApiClient<T, CreateData, UpdateData> {
  return createApiClient<T, CreateData, UpdateData>({
    ...options,
    workspaceScoped: false,
  });
}

/**
 * Type for a list function that takes workspaceId and optional params.
 */
export type ListFunction<T> = (
  workspaceId: string,
  params?: Record<string, unknown>
) => Promise<PaginatedResponse<T>>;

/**
 * Type for a get function that takes workspaceId and id.
 */
export type GetFunction<T> = (workspaceId: string, id: ResourceId) => Promise<T>;

/**
 * Type for a create function that takes workspaceId and data.
 */
export type CreateFunction<T, CreateData> = (workspaceId: string, data: CreateData) => Promise<T>;

/**
 * Type for an update function that takes workspaceId, id, and data.
 */
export type UpdateFunction<T, UpdateData> = (
  workspaceId: string,
  id: ResourceId,
  data: UpdateData
) => Promise<T>;

/**
 * Type for a delete function that takes workspaceId and id.
 */
export type DeleteFunction = (workspaceId: string, id: ResourceId) => Promise<void>;
