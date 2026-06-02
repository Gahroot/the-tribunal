import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ResourceListError } from "./resource-list-error";
import { ResourceListLoading } from "./resource-list-loading";

describe("ResourceListLoading", () => {
  it("renders the canonical page-state loading wrapper", () => {
    const { container } = render(<ResourceListLoading />);
    expect(
      container.querySelector('[data-slot="page-state"]'),
    ).toBeInTheDocument();
  });
});

describe("ResourceListError", () => {
  it("renders a resource-specific message and triggers retry", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();

    render(<ResourceListError resourceName="agents" onRetry={onRetry} />);

    expect(screen.getByText("Failed to load agents")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
