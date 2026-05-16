/**
 * MSW Node server for Vitest (jsdom). Lifecycle is wired in `src/test/setup.ts`:
 *
 *   beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
 *   afterEach(() => server.resetHandlers());
 *   afterAll(() => server.close());
 *
 * Per-test overrides go through `server.use(...)` — do NOT mutate `handlers`.
 */
import { setupServer } from "msw/node";

import { handlers } from "@/test/msw/handlers";

export const server = setupServer(...handlers);
