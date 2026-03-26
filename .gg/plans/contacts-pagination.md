# Contacts Server-Driven Pagination Plan

## Problem
`useAllContacts` fetches every contact page-by-page on load and dumps them all into Zustand. Won't scale. The API already supports `page`, `page_size`, `search`, `status`, `sort_by`, `tags`, `filters` etc.

## Scope
Fix the **contacts list page** (`/contacts/page.tsx` → `ContactsPage`). Leave `/contacts/[id]/page.tsx` alone — it uses `useAllContacts` to populate the conversation sidebar (`ContactsList` in `ActionsPanel`), which is a separate concern.

---

## Files to Change (in order)

### 1. `frontend/src/components/resource-list/resource-list-pagination.tsx`

Add optional `page`, `totalPages`, `onPageChange` props. When provided, enable buttons and wire them up. Existing usages in `campaigns-list.tsx` and `experiments-list.tsx` pass no these props → buttons stay disabled (backward compat).

```tsx
interface ResourceListPaginationProps {
  filteredCount: number;
  totalCount: number;
  resourceName: string;
  // Optional for functional pagination
  page?: number;
  totalPages?: number;
  onPageChange?: (page: number) => void;
}
```

Previous button: disabled when `!onPageChange || page <= 1`  
Next button: disabled when `!onPageChange || page >= totalPages`

---

### 2. `frontend/src/lib/contact-store.ts`

Add pagination state. When `setSearchQuery`, `setStatusFilter`, or `setFilters` is called, **automatically reset `contactsPage` to 1** to avoid stale pages after filter changes.

Add fields:
```ts
contactsPage: number          // default: 1
contactsPageSize: number      // default: 25
contactsTotal: number         // default: 0
contactsTotalPages: number    // default: 1
setContactsPage: (page: number) => void
setContactsPageSize: (size: number) => void
setPaginationMeta: (meta: { total: number; pages: number }) => void
```

Modify existing setters to reset page:
- `setSearchQuery` → also `contactsPage: 1`
- `setStatusFilter` → also `contactsPage: 1`
- `setFilters` → also `contactsPage: 1`
- `setSortBy` → also `contactsPage: 1`

---

### 3. `frontend/src/hooks/useContacts.ts`

Add a new `useContactsPaginated` hook (keep `useAllContacts` untouched for `[id]/page.tsx`):

```ts
export function useContactsPaginated(
  workspaceId: string,
  params: ContactsListParams
) {
  return useQuery({
    queryKey: ["contacts", workspaceId, params],
    queryFn: () => contactsApi.list(workspaceId, params),
    enabled: !!workspaceId,
    placeholderData: keepPreviousData, // smooth page transitions
  });
}
```

Update `useBulkDeleteContacts` and `useBulkUpdateStatus` to also invalidate `["contacts", workspaceId]` (already done) — no change needed since current invalidation covers this.

---

### 4. `frontend/src/app/contacts/page.tsx`

Replace `useAllContacts` with `useContactsPaginated`. Pull all filter state + pagination state from the Zustand store and pass as params. Sync result back to store.

```tsx
export default function Home() {
  const workspaceId = useWorkspaceId();
  const {
    setContacts, setIsLoadingContacts,
    searchQuery, statusFilter, sortBy, filters,
    contactsPage, contactsPageSize,
    setPaginationMeta,
  } = useContactStore();

  const params: ContactsListParams = {
    page: contactsPage,
    page_size: contactsPageSize,
    sort_by: sortBy,
    ...(searchQuery.trim() && { search: searchQuery.trim() }),
    ...(statusFilter && { status: statusFilter as ContactStatus }),
    ...(filters && { filters: JSON.stringify(filters) }),
  };

  const { data, isLoading } = useContactsPaginated(workspaceId ?? "", params);

  useEffect(() => { setIsLoadingContacts(isLoading); }, [isLoading]);
  useEffect(() => {
    if (data) {
      setContacts(data.items);
      setPaginationMeta({ total: data.total, pages: data.pages });
    }
  }, [data]);

  return <AppSidebar><ContactsPage /></AppSidebar>;
}
```

---

### 5. `frontend/src/components/contacts/contacts-page.tsx`

Major refactor. Changes:

**Remove:**
- `filteredContacts` memo (server does the filtering now; `contacts` from store IS the current page result)
- `filteredStatusCounts` memo (now computed simply from current page)

**Add:**
- Pull `contactsPage`, `contactsPageSize`, `contactsTotal`, `contactsTotalPages`, `setContactsPage` from store
- Status counts computed from current page contacts only (per task: "accept current-page counts")  
  - Exception: `all` count uses `contactsTotal` from store (the API's total for current filters)
- `ResourceListPagination` at bottom of scroll area, below the grid, inside the ScrollArea
- Debounce search input: local `inputValue` state, update `setSearchQuery` after 400ms debounce

**Bulk selection adjustments:**
- `handleSelectAllVisible` → use `contacts` (current page) instead of `filteredContacts`
- `allVisibleSelected`, `someVisibleSelected` → use `contacts` instead of `filteredContacts`
- `showSelectAllMatching` condition: `allVisibleSelected && !selectAllMatchingIds && contactsTotal > contacts.length`
- "Select all N contacts on this page" text in banner

**`handleBulkDelete`:** After delete, invalidate React Query cache (the mutation already does this via `onSuccess`). Remove the `setContacts(contacts.filter(...))` optimistic update — just clear selection and close dialog; React Query will refetch. OR keep the optimistic update since `contacts` is current page.

Actually keep the optimistic update since it's fine — but also the mutation's `onSuccess` invalidation will trigger a fresh fetch.

**Status counts badge in header:** Change from `contacts.length` to `contactsTotal` for the total badge.

**Pagination placement:** Add below the grid inside the scroll area's `<div className="p-6">`:
```tsx
{contactsTotalPages > 1 && (
  <div className="mt-6">
    <ResourceListPagination
      filteredCount={contacts.length}
      totalCount={contactsTotal}
      resourceName="contacts"
      page={contactsPage}
      totalPages={contactsTotalPages}
      onPageChange={setContactsPage}
    />
  </div>
)}
```

---

## Implementation Order

1. `resource-list-pagination.tsx` — no dependencies
2. `contact-store.ts` — foundational state
3. `useContacts.ts` — add hook
4. `contacts/page.tsx` — wire hook to store
5. `contacts-page.tsx` — consume store + add pagination UI

## Backward Compat

- `ResourceListPagination` — existing usages still work (optional props, buttons stay disabled)
- `useAllContacts` — kept, still used by `[id]/page.tsx`
- `contacts-list.tsx` (sidebar) — reads from `contacts` in store; when on `[id]/page.tsx` it's populated by `useAllContacts`; when navigated back to `/contacts`, it gets the current page — acceptable

## Verification

```bash
cd frontend && npm run lint && npm run build
```

Check:
- Contacts list shows page 1 on load
- Changing search/status/sort resets to page 1 and fires new API request
- Prev/Next buttons navigate pages
- "Select all matching" still works (uses `/ids` endpoint)
- Bulk delete/status-update still invalidates and refreshes
- No regressions on `[id]/page.tsx`
