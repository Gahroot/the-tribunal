import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { contactsApi, type ContactsListParams } from "@/lib/api/contacts";
import type { Contact, ContactStatus } from "@/types";

const PAGE_SIZE = 50;

interface UseInfiniteContactsParams {
  workspaceId: string | null;
  search?: string;
  status?: ContactStatus | "all";
}

interface UseInfiniteContactsReturn {
  contacts: Contact[];
  total: number;
  isLoading: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  error: Error | null;
}

export function useInfiniteContacts({
  workspaceId,
  search,
  status,
}: UseInfiniteContactsParams): UseInfiniteContactsReturn {
  const query = useInfiniteQuery({
    queryKey: ["contacts-infinite", workspaceId, search, status],
    queryFn: async ({ pageParam = 1 }) => {
      if (!workspaceId) {
        return { items: [], total: 0, page: 1, page_size: PAGE_SIZE, pages: 0 };
      }

      const params: ContactsListParams = {
        page: pageParam,
        page_size: PAGE_SIZE,
      };

      if (search && search.trim()) {
        params.search = search.trim();
      }

      if (status && status !== "all") {
        params.status = status;
      }

      return contactsApi.list(workspaceId, params);
    },
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      if (lastPage.page < lastPage.pages) {
        return lastPage.page + 1;
      }
      return undefined;
    },
    enabled: !!workspaceId,
  });

  const contacts = useMemo(() => {
    return query.data?.pages.flatMap((page) => page.items) ?? [];
  }, [query.data?.pages]);

  const total = query.data?.pages[0]?.total ?? 0;

  return {
    contacts,
    total,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage ?? false,
    fetchNextPage: query.fetchNextPage,
    error: query.error,
  };
}
