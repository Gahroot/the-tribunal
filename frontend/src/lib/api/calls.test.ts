import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
}));

import { apiPost } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/utils/errors";

import { callsApi } from "./calls";

const request = {
  to_number: "+15551230000",
  from_phone_number: "+15550001111",
};

describe("manual call initiation (contact sidebar and agent test call)", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each(["failed", "queued", "unknown"])(
    "rejects an HTTP-success response with status %s without exposing provider data",
    async (status) => {
      vi.mocked(apiPost).mockResolvedValue({
        id: "call-1",
        status,
        error_message: "raw provider dump with credentials",
      });
      const result = callsApi.initiate("workspace-1", request);
      await expect(result).rejects.toThrow("Call was not accepted");
      await result.catch((error) => {
        const message = getApiErrorMessage(error, "fallback");
        expect(message).toContain("try again");
        expect(message).not.toContain("credentials");
      });
      expect(apiPost).toHaveBeenCalledOnce();
    },
  );

  it.each(["initiated", "ringing", "answered", "completed"])(
    "preserves accepted initiation (%s)",
    async (status) => {
      const call = { id: "call-1", status };
      vi.mocked(apiPost).mockResolvedValue(call);
      await expect(callsApi.initiate("workspace-1", request)).resolves.toBe(call);
      expect(apiPost).toHaveBeenCalledWith(
        "/api/v1/workspaces/workspace-1/calls",
        request,
      );
    },
  );

  it("preserves missing-configuration errors", async () => {
    const error = new Error("Telnyx not configured");
    vi.mocked(apiPost).mockRejectedValue(error);
    await expect(callsApi.initiate("workspace-1", request)).rejects.toBe(error);
  });
});
