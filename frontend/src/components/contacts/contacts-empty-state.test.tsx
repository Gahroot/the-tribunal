import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ContactsEmptyState } from "@/components/contacts/contacts-empty-state";

describe("ContactsEmptyState", () => {
  it("offers first-run import and add-contact actions", async () => {
    const onAddContact = vi.fn();
    const onImportContacts = vi.fn();
    const user = userEvent.setup();

    render(
      <ContactsEmptyState
        hasFilters={false}
        onAddContact={onAddContact}
        onImportContacts={onImportContacts}
      />,
    );

    expect(screen.getByRole("button", { name: /add contact/i })).toBeInTheDocument();
    const importButton = screen.getByRole("button", { name: /import csv/i });
    expect(importButton).toBeInTheDocument();

    await user.click(importButton);

    expect(onImportContacts).toHaveBeenCalledTimes(1);
    expect(onAddContact).not.toHaveBeenCalled();
  });

  it("does not show first-run actions for filtered empty results", () => {
    render(<ContactsEmptyState hasFilters onAddContact={vi.fn()} onImportContacts={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /import csv/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add contact/i })).not.toBeInTheDocument();
  });
});
