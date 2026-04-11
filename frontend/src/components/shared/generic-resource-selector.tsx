"use client";

import { useMemo, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { Search, X, Loader2 } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useDebounce } from "@/hooks/useDebounce";

type IdOf = string | number;

export interface GenericResourceSelectorProps<T> {
  items: T[];
  /** Stable identifier extractor. Defaults to `item.id`. */
  getItemId?: (item: T) => IdOf;
  /** Render a single row. The wrapper handles click + selected styling. */
  renderItem: (item: T, isSelected: boolean) => ReactNode;

  /** Selected ids. For single-mode pass `[]` or `[id]`. */
  selectedIds: IdOf[];
  onSelectionChange: (ids: IdOf[]) => void;
  multiple?: boolean;
  /** In single mode, whether the user may click a selected row to clear it. */
  allowDeselect?: boolean;

  /** Enable built-in search box. Provide a predicate to filter items by query. */
  searchable?: boolean;
  searchPlaceholder?: string;
  filterItem?: (item: T, query: string) => boolean;
  /** Override the internal debounced search state (controlled mode). */
  searchQuery?: string;
  onSearchChange?: (query: string) => void;

  isLoading?: boolean;
  emptyMessage?: ReactNode;
  loadingMessage?: ReactNode;

  /** Optional slots rendered above/below the scroll list. */
  header?: ReactNode;
  footer?: ReactNode;

  /** Scroll area height. Defaults to 400px. */
  height?: number | string;
  /** Extra classes on the outer wrapper. */
  className?: string;
  /** Extra classes on each row wrapper. */
  itemClassName?: string;
  /** Disable the hover/tap motion wrapper (useful for dense virtual lists). */
  disableMotion?: boolean;
}

/**
 * Generic list-picker primitive.
 *
 * Owns: optional search input (with debounce), scrollable list, empty/loading
 * states, and selection toggling for single or multi mode. Does NOT own data
 * fetching — callers pass `items` directly.
 */
export function GenericResourceSelector<T>({
  items,
  getItemId = (item) => (item as { id: IdOf }).id,
  renderItem,
  selectedIds,
  onSelectionChange,
  multiple = false,
  allowDeselect = true,
  searchable = false,
  searchPlaceholder = "Search...",
  filterItem,
  searchQuery,
  onSearchChange,
  isLoading = false,
  emptyMessage = "No results",
  loadingMessage = "Loading...",
  header,
  footer,
  height = 400,
  className,
  itemClassName,
  disableMotion = false,
}: GenericResourceSelectorProps<T>) {
  const [internalSearch, setInternalSearch] = useState("");
  const isSearchControlled = searchQuery !== undefined;
  const rawSearch = isSearchControlled ? (searchQuery ?? "") : internalSearch;
  const debouncedSearch = useDebounce(rawSearch, 250);

  const filteredItems = useMemo(() => {
    if (!searchable || !debouncedSearch.trim() || !filterItem) return items;
    const q = debouncedSearch.toLowerCase();
    return items.filter((item) => filterItem(item, q));
  }, [items, searchable, debouncedSearch, filterItem]);

  const selectedSet = useMemo(
    () => new Set(selectedIds.map(String)),
    [selectedIds]
  );

  const handleSelect = (item: T) => {
    const id = getItemId(item);
    const key = String(id);
    if (multiple) {
      if (selectedSet.has(key)) {
        onSelectionChange(selectedIds.filter((sid) => String(sid) !== key));
      } else {
        onSelectionChange([...selectedIds, id]);
      }
      return;
    }
    if (selectedSet.has(key)) {
      if (allowDeselect) onSelectionChange([]);
      return;
    }
    onSelectionChange([id]);
  };

  const updateSearch = (value: string) => {
    if (!isSearchControlled) setInternalSearch(value);
    onSearchChange?.(value);
  };

  const showEmpty = !isLoading && filteredItems.length === 0;

  return (
    <div className={className ? `space-y-4 ${className}` : "space-y-4"}>
      {header}

      {searchable && (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder={searchPlaceholder}
            value={rawSearch}
            onChange={(e) => updateSearch(e.target.value)}
            className="pl-10"
          />
          {rawSearch && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-1 top-1/2 -translate-y-1/2 size-7"
              onClick={() => updateSearch("")}
              aria-label="Clear search"
            >
              <X className="size-4" />
            </Button>
          )}
        </div>
      )}

      <ScrollArea style={{ height }}>
        <div className="space-y-2 pr-4">
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="size-6 mb-2 animate-spin" />
              <p className="text-sm">{loadingMessage}</p>
            </div>
          )}

          {!isLoading &&
            filteredItems.map((item) => {
              const id = getItemId(item);
              const isSelected = selectedSet.has(String(id));
              const rowClass = itemClassName ?? "cursor-pointer";
              if (disableMotion) {
                return (
                  <div
                    key={String(id)}
                    onClick={() => handleSelect(item)}
                    className={rowClass}
                  >
                    {renderItem(item, isSelected)}
                  </div>
                );
              }
              return (
                <motion.div
                  key={String(id)}
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.99 }}
                  onClick={() => handleSelect(item)}
                  className={rowClass}
                >
                  {renderItem(item, isSelected)}
                </motion.div>
              );
            })}

          {showEmpty && (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              {typeof emptyMessage === "string" ? <p>{emptyMessage}</p> : emptyMessage}
            </div>
          )}
        </div>
      </ScrollArea>

      {footer}
    </div>
  );
}
