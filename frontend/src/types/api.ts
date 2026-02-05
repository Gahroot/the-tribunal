/**
 * Shared API types used across API clients.
 */

/**
 * Standard paginated response from the backend.
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/**
 * Resource identifier type (UUID string or numeric ID).
 */
export type ResourceId = string | number;
