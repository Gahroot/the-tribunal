import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StarRating } from "./star-rating";

describe("StarRating", () => {
  it("renders `max` stars (default 5)", () => {
    const { container } = render(<StarRating value={3} />);
    expect(container.querySelectorAll("svg")).toHaveLength(5);
  });

  it("renders custom `max`", () => {
    const { container } = render(<StarRating value={1} max={3} />);
    expect(container.querySelectorAll("svg")).toHaveLength(3);
  });

  it("is read-only without onChange (no buttons)", () => {
    render(<StarRating value={4} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("is interactive with onChange and reports the clicked star", () => {
    const onChange = vi.fn();
    render(<StarRating value={0} onChange={onChange} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(5);
    fireEvent.click(buttons[3]);
    expect(onChange).toHaveBeenCalledWith(4);
  });
});
