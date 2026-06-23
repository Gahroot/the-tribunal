import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useResourceList } from "./useResourceList";

type Filters = {
  status: string;
};

describe("useResourceList", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("composes search, pagination, filters and selection", () => {
    const { result } = renderHook(() =>
      useResourceList<Filters, number>({
        search: { delay: 200 },
        pagination: { initialPageSize: 25, total: 100 },
        initialFilters: { status: "all" },
        rowIds: [1, 2, 3],
      }),
    );

    expect(result.current.search.debouncedValue).toBe("");
    expect(result.current.pagination.page).toBe(1);
    expect(result.current.filters.activeCount).toBe(0);
    expect(result.current.selection.selectedCount).toBe(0);
  });

  it("resets pagination to page 1 when the debounced search changes", () => {
    const { result } = renderHook(() =>
      useResourceList<Filters, number>({
        search: { delay: 200 },
        pagination: { initialPageSize: 10, total: 100 },
        initialFilters: { status: "all" },
        rowIds: [1, 2, 3],
      }),
    );

    act(() => result.current.pagination.setPage(4));
    expect(result.current.pagination.page).toBe(4);

    act(() => result.current.search.setValue("acme"));
    act(() => {
      vi.advanceTimersByTime(200);
    });

    expect(result.current.search.debouncedValue).toBe("acme");
    expect(result.current.pagination.page).toBe(1);
  });

  it("does not reset the page until the search debounce actually fires", () => {
    const { result } = renderHook(() =>
      useResourceList<Filters, number>({
        search: { delay: 300 },
        pagination: { initialPageSize: 10, total: 100 },
        initialFilters: { status: "all" },
        rowIds: [1, 2, 3],
      }),
    );

    act(() => result.current.pagination.setPage(5));
    act(() => result.current.search.setValue("ac"));

    // Before the debounce window elapses the page is untouched.
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.pagination.page).toBe(5);

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.pagination.page).toBe(1);
  });

  it("wires row selection against the supplied visible row ids", () => {
    const { result } = renderHook(() =>
      useResourceList<Filters, number>({
        pagination: { initialPageSize: 10, total: 100 },
        initialFilters: { status: "all" },
        rowIds: [10, 20, 30],
      }),
    );

    act(() => result.current.selection.toggleAllVisible());
    expect(result.current.selection.selectedCount).toBe(3);
    expect(result.current.selection.allVisibleSelected).toBe(true);
    expect(result.current.selection.isSelected(20)).toBe(true);

    act(() => result.current.selection.toggle(20));
    expect(result.current.selection.selectedCount).toBe(2);
    expect(result.current.selection.isSelected(20)).toBe(false);
  });

  it("resets pagination to page 1 when a filter changes", () => {
    const { result } = renderHook(() =>
      useResourceList<Filters, number>({
        pagination: { initialPageSize: 10, total: 100 },
        initialFilters: { status: "all" },
        rowIds: [1, 2, 3],
      }),
    );

    act(() => result.current.pagination.setPage(3));
    expect(result.current.pagination.page).toBe(3);

    act(() => result.current.filters.setFilter("status", "won"));
    expect(result.current.pagination.page).toBe(1);
    expect(result.current.filters.activeCount).toBe(1);
  });
});
