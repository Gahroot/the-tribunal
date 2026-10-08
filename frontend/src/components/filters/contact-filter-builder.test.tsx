import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { FilterDefinition } from "@/types";

import { ContactFilterBuilder } from "./contact-filter-builder";

vi.mock("@/hooks/useSegments", () => ({
  useSegmentPreview: () => ({ data: { total: 0 }, isFetching: false }),
}));
vi.mock("@/components/segments/save-segment-dialog", () => ({ SaveSegmentDialog: () => null }));

function Harness({ initial }: { initial: FilterDefinition }) {
  const [filters, setFilters] = useState<FilterDefinition | null>(initial);
  return <>
    <ContactFilterBuilder workspaceId="test" filters={filters} onFiltersChange={setFilters} />
    <output data-testid="definition">{JSON.stringify(filters)}</output>
  </>;
}

function definition() {
  return JSON.parse(screen.getByTestId("definition").textContent!);
}

async function chooseOperator(label: string) {
  const triggers = screen.getAllByRole("combobox");
  fireEvent.keyDown(triggers[1], { key: "ArrowDown" });
  await userEvent.click(await screen.findByRole("option", { name: label }));
}

describe("contact membership filters", () => {
  it("changes first-run equality to a list, selects multiple statuses, and preserves equality", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ logic: "and", rules: [{ field: "status", operator: "equals", value: "new" }] }} />);
    await user.click(screen.getByRole("button", { name: "Filters (1)" }));
    await chooseOperator("is one of");
    expect(definition().rules[0].value).toEqual(["new"]);
    await user.click(screen.getByRole("button", { name: "New" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "Qualified" }));
    expect(definition().rules[0].value).toEqual(["new", "qualified"]);
    await user.keyboard("{Escape}");
    await chooseOperator("is");
    expect(definition().rules[0]).toEqual({ field: "status", operator: "equals", value: "new" });
  });

  it("loads saved lists and stores an explicit empty selection when all statuses are removed", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ logic: "or", rules: [{ field: "status", operator: "in", value: ["new", "qualified"] }] }} />);
    await user.click(screen.getByRole("button", { name: "Filters (1)" }));
    await user.click(screen.getByRole("button", { name: "New, Qualified" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "New" }));
    await user.click(screen.getByRole("menuitemcheckbox", { name: "Qualified" }));
    expect(definition()).toEqual({ logic: "or", rules: [{ field: "status", operator: "in", value: [] }] });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.getByRole("button", { name: "No values selected" })).toBeInTheDocument());
  });
});
