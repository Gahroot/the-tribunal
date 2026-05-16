/**
 * Typed axios wrapper backed by the OpenAPI schema in `_generated.ts`.
 *
 * This module re-exports `Paths` / `Components` (and a few derived helpers)
 * and exposes path-aware `get/post/put/patch/del` functions whose request
 * params, request body, and response type are all inferred from the spec.
 *
 * Generated types come from `openapi-typescript`:
 *   - `paths`      → every route, keyed by URL template
 *   - `components` → schemas (request/response models)
 *
 * Re-run `npm run codegen` after backend changes so this stays in sync.
 *
 * Usage:
 *
 *   import { apiClient, type ResponseOf, type RequestBodyOf } from "./_client";
 *
 *   // Path is checked against the spec; query/path params are typed.
 *   const data = await apiClient.get(
 *     "/api/v1/workspaces/{workspace_id}/contacts",
 *     { path: { workspace_id }, query: { page: 1 } },
 *   );
 *   // `data` is `components["schemas"]["ContactListResponse"]`.
 */

import type { AxiosRequestConfig } from "axios";

import api from "@/lib/api";
import type { components, paths } from "@/lib/api/_generated";

// Re-export the canonical spec types so feature modules can pull them from one
// place rather than reaching into `_generated.ts` directly.
export type Paths = paths;
export type Components = components;
export type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Method-aware path filters.
//
// `PathsWithMethod<M>` is the subset of paths in the spec that define an
// operation for HTTP verb `M`. This makes `apiClient.get(...)` only accept
// URLs that actually expose a GET in the backend.
// ---------------------------------------------------------------------------

export type HttpMethod = "get" | "post" | "put" | "patch" | "delete";

export type PathsWithMethod<M extends HttpMethod> = {
  [P in keyof Paths]: Paths[P] extends { [K in M]: unknown } ? P : never;
}[keyof Paths];

// `Op<P, M>` resolves to the operation object for `paths[P][M]`, with the
// optional `?` stripped. Used internally to derive params/body/response.
type Op<P extends keyof Paths, M extends HttpMethod> = Paths[P] extends {
  [K in M]: infer T;
}
  ? T
  : never;

// ---------------------------------------------------------------------------
// Public type helpers — derive request/response shapes from a (path, method).
// ---------------------------------------------------------------------------

/** JSON response body type for `paths[P][M]` (200 or 201). */
export type ResponseOf<P extends keyof Paths, M extends HttpMethod> = Op<P, M> extends {
  responses: infer R;
}
  ? R extends { 200: { content: { "application/json": infer J } } }
    ? J
    : R extends { 201: { content: { "application/json": infer J } } }
      ? J
      : void
  : void;

/** Path parameter object for `paths[P][M]` (e.g. `{ workspace_id: string }`). */
export type PathParamsOf<P extends keyof Paths, M extends HttpMethod> = Op<P, M> extends {
  parameters: { path: infer T };
}
  ? T
  : never;

/** Query parameter object for `paths[P][M]`. */
export type QueryParamsOf<P extends keyof Paths, M extends HttpMethod> = Op<P, M> extends {
  parameters: { query?: infer T };
}
  ? T
  : never;

/** JSON request body for `paths[P][M]`. */
export type RequestBodyOf<P extends keyof Paths, M extends HttpMethod> = Op<P, M> extends {
  requestBody: { content: { "application/json": infer B } };
}
  ? B
  : Op<P, M> extends { requestBody?: { content: { "application/json": infer B } } }
    ? B | undefined
    : undefined;

// ---------------------------------------------------------------------------
// Path interpolation.
//
// Replaces `{name}` placeholders with values from the `path` param object.
// Throws if a placeholder is left unfilled — better to fail loudly at the
// boundary than to send a request to a malformed URL.
// ---------------------------------------------------------------------------

function buildUrl(template: string, pathParams: Record<string, unknown> | undefined): string {
  if (!pathParams) {
    if (template.includes("{")) {
      throw new Error(`Missing path params for ${template}`);
    }
    return template;
  }
  return template.replace(/\{([^}]+)\}/g, (_, key: string) => {
    const value = pathParams[key];
    if (value === undefined || value === null) {
      throw new Error(`Missing path param '${key}' for ${template}`);
    }
    return encodeURIComponent(String(value));
  });
}

// ---------------------------------------------------------------------------
// Request option shapes per verb. Each option object is conditionally typed —
// if the spec says the endpoint has no path/query/body, that field is `never`
// and callers can't pass it.
// ---------------------------------------------------------------------------

type ReadOptions<P extends keyof Paths, M extends HttpMethod> = {
  path?: PathParamsOf<P, M>;
  query?: QueryParamsOf<P, M>;
  config?: AxiosRequestConfig;
};

type WriteOptions<P extends keyof Paths, M extends HttpMethod> = {
  path?: PathParamsOf<P, M>;
  query?: QueryParamsOf<P, M>;
  body?: RequestBodyOf<P, M>;
  config?: AxiosRequestConfig;
};

async function request<P extends keyof Paths, M extends HttpMethod>(
  method: M,
  url: P,
  options: WriteOptions<P, M> = {},
): Promise<ResponseOf<P, M>> {
  const fullUrl = buildUrl(url as string, options.path as Record<string, unknown> | undefined);
  const { query, body, config } = options;
  const response = await api.request<ResponseOf<P, M>>({
    ...config,
    method,
    url: fullUrl,
    params: { ...(config?.params as object | undefined), ...(query as object | undefined) },
    // `body` (typed JSON) wins when provided; otherwise let `config.data`
    // through so callers can pass multipart/FormData payloads that the JSON
    // spec can't express.
    data: body !== undefined ? body : config?.data,
  });
  return response.data;
}

/**
 * Spec-typed axios client. Each method is constrained to paths that actually
 * expose that HTTP verb; params/body/response are inferred from the spec.
 */
export const apiClient = {
  get<P extends PathsWithMethod<"get">>(url: P, options?: ReadOptions<P, "get">) {
    return request("get", url, options);
  },
  post<P extends PathsWithMethod<"post">>(url: P, options?: WriteOptions<P, "post">) {
    return request("post", url, options);
  },
  put<P extends PathsWithMethod<"put">>(url: P, options?: WriteOptions<P, "put">) {
    return request("put", url, options);
  },
  patch<P extends PathsWithMethod<"patch">>(url: P, options?: WriteOptions<P, "patch">) {
    return request("patch", url, options);
  },
  del<P extends PathsWithMethod<"delete">>(url: P, options?: ReadOptions<P, "delete">) {
    return request("delete", url, options);
  },
};

export type ApiClient = typeof apiClient;
