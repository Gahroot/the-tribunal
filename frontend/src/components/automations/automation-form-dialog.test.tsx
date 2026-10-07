import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { AutomationFormDialog } from "./automation-form-dialog";
import {
  DEFAULT_SMS_MESSAGE,
  EMPTY_AUTOMATION_FORM,
  type AutomationFormState,
  buildCreatePayload,
  getFormIssues,
} from "./automation-logic";

function Harness({
  initial = EMPTY_AUTOMATION_FORM,
  showIssues = false,
  onSubmit,
}: {
  initial?: AutomationFormState;
  showIssues?: boolean;
  onSubmit: (form: AutomationFormState) => void;
}) {
  const [form, setForm] = useState(initial);
  return (
    <AutomationFormDialog
      open
      isEditing={false}
      form={form}
      issues={showIssues ? getFormIssues(form) : []}
      campaigns={[]}
      agents={[]}
      isSubmitting={false}
      onFormChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))}
      onOpenChange={() => {}}
      onSubmit={() => onSubmit(form)}
      onCancel={() => {}}
    />
  );
}

describe("AutomationFormDialog", () => {
  it("collects the SMS message for the default automation and submits it", () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);

    const message = screen.getByLabelText("Message");
    expect(message).toHaveValue(DEFAULT_SMS_MESSAGE);
    expect(
      screen.getByText(/Opted-out contacts are skipped/),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "No-show follow-up" },
    });
    fireEvent.change(message, { target: { value: "Hi {first_name}!" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    const submitted = onSubmit.mock.calls[0][0] as AutomationFormState;
    expect(buildCreatePayload(submitted).actions).toEqual([
      { type: "send_sms", config: { message: "Hi {first_name}!" } },
    ]);
  });

  it("shows the missing-message error inline on the field", () => {
    render(
      <Harness
        showIssues
        initial={{
          ...EMPTY_AUTOMATION_FORM,
          actions: [{ type: "send_sms", config: { message: "" } }],
        }}
        onSubmit={vi.fn()}
      />,
    );
    const message = screen.getByLabelText("Message");
    expect(message).toHaveAttribute("aria-invalid", "true");
    expect(
      screen.getByText("Step 1: write the text message to send."),
    ).toBeInTheDocument();
  });

  it("offers saving as a draft when Active is switched off", () => {
    render(<Harness onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByRole("switch", { name: "Active" }));
    expect(screen.getByRole("button", { name: "Save Draft" })).toBeInTheDocument();
  });

  it("renders every existing step when editing", () => {
    render(
      <Harness
        initial={{
          ...EMPTY_AUTOMATION_FORM,
          actions: [
            { type: "send_sms", config: { message: "Hi" } },
            { type: "apply_tag", config: { tag: "texted" } },
          ],
        }}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Tag")).toHaveValue("texted");
    expect(
      screen.getByRole("button", { name: "Remove step 2" }),
    ).toBeInTheDocument();
  });
});
