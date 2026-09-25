"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Inbox, PanelRight } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ConversationFeed } from "@/components/conversation/conversation-feed";
import { ConversationContextPanel } from "@/components/conversations/conversation-context-panel";
import {
  ConversationList,
  type BuiltInView as InboxFilter,
  type SavedView as SavedInboxView,
} from "@/components/conversations/conversation-list";
import { Button } from "@/components/ui/button";
import { PageEmptyState, PageErrorState } from "@/components/ui/page-state";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounce } from "@/hooks/useDebounce";
import { useIsMobile } from "@/hooks/useMobile";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { contactsApi } from "@/lib/api/contacts";
import { conversationsApi, type InboxConversation } from "@/lib/api/conversations";
import { queryKeys } from "@/lib/query-keys";
import { REALTIME } from "@/lib/query-options";
import { cn } from "@/lib/utils";

const VIEWS_STORAGE_PREFIX = "inbox:saved-views:";
const ACTIVE_VIEW_PREFIX = "tribunal:inbox-active-view:";
const isInboxFilter = (value: unknown): value is InboxFilter =>
  value === "all" || value === "waiting" || value === "hot";
const isUuid = (value: string) =>
  /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(value);

function readSavedViews(workspaceId: string): SavedInboxView[] {
  try {
    const raw: unknown = JSON.parse(
      localStorage.getItem(`${VIEWS_STORAGE_PREFIX}${workspaceId}`) ?? "[]",
    );
    if (!Array.isArray(raw)) return [];
    return raw
      .filter(
        (v): v is SavedInboxView =>
          !!v &&
          typeof v === "object" &&
          typeof v.id === "string" &&
          typeof v.name === "string" &&
          typeof v.search === "string" &&
          v.search.length <= 200 &&
          isInboxFilter(v.view),
      )
      .slice(0, 30);
  } catch {
    return [];
  }
}

export function ConversationsPage() {
  const workspaceId = useWorkspaceId();
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const isDesktop = !useIsMobile();
  const [localView, setLocalView] = useState<InboxFilter>("all");
  const viewParam = params.get("view");
  const filter = isInboxFilter(viewParam) ? viewParam : localView;
  const selectedId = params.get("conversation");
  const invalidSelection = !!selectedId && !isUuid(selectedId);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search.trim(), 300);
  const listIdentity = `${workspaceId}:${filter}:${debouncedSearch}`;
  const [pagination, setPagination] = useState({ identity: "", page: 1 });
  const page = pagination.identity === listIdentity ? pagination.page : 1;
  const [savedViews, setSavedViews] = useState<SavedInboxView[]>([]);
  const [activeSavedId, setActiveSavedId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const previousWorkspace = useRef(workspaceId);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const acknowledgeRef = useRef("");
  const [readError, setReadError] = useState<string | null>(null);

  const navigate = useCallback(
    (view: InboxFilter, id: string | null, replace = false) => {
      const next = new URLSearchParams({ view });
      if (id) next.set("conversation", id);
      const href = `/conversations?${next}`;
      if (replace) router.replace(href, { scroll: false });
      else router.push(href, { scroll: false });
    },
    [router],
  );

  useEffect(() => {
    if (!workspaceId) return;
    const changed = !!previousWorkspace.current && previousWorkspace.current !== workspaceId;
    previousWorkspace.current = workspaceId;
    const timer = window.setTimeout(() => {
      setSavedViews(readSavedViews(workspaceId));
      setSearch("");
      try {
        const saved: unknown = JSON.parse(
          localStorage.getItem(`${ACTIVE_VIEW_PREFIX}${workspaceId}`) ?? "null",
        );
        const restored = isInboxFilter(saved) ? saved : "all";
        setLocalView(restored);
        if (changed) navigate(restored, null, true);
      } catch {
        setLocalView("all");
        if (changed) navigate("all", null, true);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [workspaceId, navigate]);

  useEffect(() => {
    if (!Object.keys(drafts).length) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const leave = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("a[href]");
      if (
        !(link instanceof HTMLAnchorElement) ||
        link.target === "_blank" ||
        event.metaKey ||
        event.ctrlKey
      )
        return;
      if (new URL(link.href).pathname === "/conversations") return;
      if (!window.confirm("Leave the inbox and discard your unsent drafts?")) {
        event.preventDefault();
        event.stopPropagation();
      } else setDrafts({});
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", leave, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", leave, true);
    };
  }, [drafts]);

  const inbox = useQuery({
    queryKey: queryKeys.conversations.inbox(workspaceId ?? "", {
      view: filter,
      q: debouncedSearch,
      page,
      page_size: 50,
    }),
    queryFn: ({ signal }) =>
      conversationsApi.inbox(
        workspaceId!,
        { view: filter, q: debouncedSearch, page, page_size: 50 },
        signal,
      ),
    enabled: !!workspaceId,
    retry: 1,
    throwOnError: false,
    ...REALTIME,
    refetchIntervalInBackground: false,
  });
  const detail = useQuery({
    queryKey: queryKeys.conversations.inboxDetail(workspaceId ?? "", selectedId ?? ""),
    queryFn: ({ signal }) => conversationsApi.inboxDetail(workspaceId!, selectedId!, signal),
    enabled: !!workspaceId && !!selectedId && !invalidSelection,
    ...REALTIME,
    retry: false,
    throwOnError: false,
    refetchIntervalInBackground: false,
  });
  const selected = invalidSelection || detail.isError ? undefined : detail.data;
  const contact = useQuery({
    queryKey: queryKeys.contacts.detail(workspaceId ?? "", String(selected?.contact_id ?? "")),
    queryFn: () => contactsApi.get(workspaceId!, selected!.contact_id!),
    enabled: !!workspaceId && selected?.contact != null,
    retry: 1,
    throwOnError: false,
  });
  const rows = useMemo(
    () =>
      (inbox.data?.items ?? []).map((conversation) => ({
        conversation,
        contact: conversation.contact ?? undefined,
      })),
    [inbox.data],
  );

  const visibleNext = rows.find(
    (row) => row.conversation.needs_human_reply && row.conversation.id !== selectedId,
  )?.conversation;
  const nextReply = useQuery({
    queryKey: queryKeys.conversations.inbox(workspaceId ?? "", {
      view: "waiting",
      q: "",
      page: 1,
      page_size: 1,
    }),
    queryFn: ({ signal }) =>
      conversationsApi.inbox(
        workspaceId!,
        { view: "waiting", q: "", page: 1, page_size: 1 },
        signal,
      ),
    enabled:
      !!workspaceId &&
      filter === "waiting" &&
      !!selected &&
      !selected.needs_human_reply &&
      !visibleNext,
    retry: 1,
    throwOnError: false,
  });
  const nextWaiting = visibleNext ?? nextReply.data?.items.find((item) => item.id !== selectedId);

  useEffect(() => {
    if (isDesktop && !selectedId && rows.length) navigate(filter, rows[0].conversation.id, true);
  }, [isDesktop, selectedId, rows, filter, navigate]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => headingRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [selectedId, selected?.id]);

  const changeFilter = (next: InboxFilter) => {
    setLocalView(next);
    setActiveSavedId(null);
    navigate(next, selectedId);
    try {
      localStorage.setItem(`${ACTIVE_VIEW_PREFIX}${workspaceId}`, JSON.stringify(next));
    } catch {
      /* optional preference */
    }
  };
  const saveView = (name: string) => {
    if (!workspaceId) return;
    const next = [...savedViews, { id: crypto.randomUUID(), name, search, view: filter }].slice(
      -30,
    );
    setSavedViews(next);
    try {
      localStorage.setItem(`${VIEWS_STORAGE_PREFIX}${workspaceId}`, JSON.stringify(next));
    } catch {
      toast.error("This browser couldn't save the view.");
    }
  };
  const deleteView = (id: string) => {
    const next = savedViews.filter((v) => v.id !== id);
    setSavedViews(next);
    try {
      localStorage.setItem(`${VIEWS_STORAGE_PREFIX}${workspaceId}`, JSON.stringify(next));
    } catch {
      toast.error("This browser couldn't update saved views.");
    }
  };

  const acknowledge = useCallback(
    async (snapshot: InboxConversation) => {
      if (!workspaceId || !snapshot.unread_count || document.visibilityState === "hidden") return;
      const key = `${workspaceId}:${snapshot.id}:${snapshot.last_message_at}:${snapshot.unread_count}`;
      if (acknowledgeRef.current === key) return;
      acknowledgeRef.current = key;
      setReadError(null);
      try {
        await conversationsApi.markRead(workspaceId, snapshot);
        void queryClient.invalidateQueries({ queryKey: queryKeys.conversations.all(workspaceId) });
      } catch {
        setReadError(`${workspaceId}:${snapshot.id}`);
      }
    },
    [workspaceId, queryClient, setReadError],
  );

  if (!workspaceId)
    return (
      <div className="p-4 sm:p-6">
        <PageEmptyState
          title="Select a workspace"
          description="Choose a workspace to view conversations."
        />
      </div>
    );

  const selectedName = selected?.contact
    ? [selected.contact.first_name, selected.contact.last_name].filter(Boolean).join(" ")
    : (selected?.contact_phone ?? "Conversation");
  const draftKey = `${workspaceId}:${selectedId}`;
  const updateDraft = (value: string) => {
    if (value && !drafts[draftKey] && Object.keys(drafts).length >= 30) {
      toast.error("Send or discard an existing draft before starting another.");
      return;
    }
    setDrafts((current) => {
      const next = { ...current };
      if (value) next[draftKey] = value;
      else delete next[draftKey];
      return next;
    });
  };
  const missing = invalidSelection || detail.isError;
  const outsideView =
    selected &&
    !inbox.isPending &&
    !inbox.isError &&
    debouncedSearch === search.trim() &&
    !rows.some((r) => r.conversation.id === selected.id);
  const showThreadOnMobile = !!selectedId;
  const activeSaved = savedViews.find(
    (view) => view.id === activeSavedId && view.view === filter && view.search === search,
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <h1 className="sr-only">Conversations</h1>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex min-h-0 flex-1">
          <aside
            aria-label="Conversation list"
            className={cn(
              "flex min-h-0 w-full shrink-0 flex-col border-r md:w-80 lg:w-[22rem]",
              showThreadOnMobile && "hidden md:flex",
            )}
          >
            <ConversationList
              rows={rows}
              selectedId={selectedId}
              onSelect={(conversation) => navigate(filter, conversation.id)}
              search={search}
              onSearchChange={setSearch}
              activeViewId={activeSaved ? `saved:${activeSaved.id}` : filter}
              onViewChange={(view) => {
                if (isInboxFilter(view)) changeFilter(view);
              }}
              savedViews={savedViews}
              canSaveViews={!!workspaceId}
              onSaveView={saveView}
              onApplySavedView={(view) => {
                setSearch(view.search);
                changeFilter(view.view);
                setActiveSavedId(view.id);
              }}
              onDeleteSavedView={deleteView}
              counts={inbox.data?.counts ?? { all: 0, waiting: 0, hot: 0 }}
              countsLoading={inbox.isPending || inbox.isError || debouncedSearch !== search.trim()}
              isPending={inbox.isPending || debouncedSearch !== search.trim()}
              isError={inbox.isError}
              onRetry={() => void inbox.refetch()}
              page={page}
              pages={inbox.data?.pages ?? 0}
              total={inbox.data?.total ?? 0}
              onPageChange={(next) => setPagination({ identity: listIdentity, page: next })}
            />
          </aside>
          <section
            aria-label="Selected conversation"
            className={cn(
              "flex min-h-0 min-w-0 flex-1 flex-col",
              !showThreadOnMobile && "hidden md:flex",
            )}
          >
            {selectedId ? (
              <>
                <div className="flex shrink-0 items-center justify-between gap-2 border-b px-3 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="md:hidden"
                      onClick={() => navigate(filter, null)}
                      aria-label="Back to inbox"
                    >
                      <ArrowLeft className="size-4" />
                    </Button>
                    <h2 ref={headingRef} tabIndex={-1} className="truncate text-sm font-medium">
                      {selectedName}
                    </h2>
                  </div>
                  {filter === "waiting" ? (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!nextWaiting}
                      onClick={() => {
                        if (nextWaiting) {
                          setSearch("");
                          navigate("waiting", nextWaiting.id);
                        }
                      }}
                    >
                      Next waiting reply
                    </Button>
                  ) : null}
                  {selected?.contact_id ? (
                    <Sheet>
                      <SheetTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="xl:hidden"
                          aria-label="Open contact details"
                        >
                          <PanelRight className="size-4" />
                        </Button>
                      </SheetTrigger>
                      <SheetContent side="right" className="flex w-[min(100vw,24rem)] flex-col p-0">
                        <SheetHeader className="border-b px-4 py-3">
                          <SheetTitle>Contact details</SheetTitle>
                        </SheetHeader>
                        {contact.isError ? (
                          <PageErrorState
                            message="Couldn't load contact details."
                            onRetry={() => void contact.refetch()}
                          />
                        ) : (
                          <ConversationContextPanel
                            workspaceId={workspaceId}
                            contact={contact.data ?? null}
                            conversation={selected}
                            className="min-h-0 flex-1"
                          />
                        )}
                      </SheetContent>
                    </Sheet>
                  ) : null}
                </div>
                {outsideView ? (
                  <div role="status" className="border-b px-4 py-2 text-sm text-muted-foreground">
                    This conversation is outside the current results. Your selection is kept.
                  </div>
                ) : null}
                {readError === draftKey ? (
                  <div
                    role="alert"
                    className="flex items-center justify-between gap-2 border-b px-4 py-2 text-sm"
                  >
                    Couldn&apos;t mark this thread read.
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        acknowledgeRef.current = "";
                        if (selected) void acknowledge(selected);
                      }}
                    >
                      Retry
                    </Button>
                  </div>
                ) : null}
                {missing ? (
                  <PageErrorState
                    message="This conversation couldn't be opened. It may have been removed or be unavailable in this workspace."
                    onRetry={() => void detail.refetch()}
                  />
                ) : !selected ? (
                  <div className="space-y-4 p-4" aria-label="Loading conversation">
                    <Skeleton className="h-16 w-2/3" />
                    <Skeleton className="h-16 w-1/2" />
                  </div>
                ) : (
                  <ConversationFeed
                    key={draftKey}
                    workspaceId={workspaceId}
                    conversation={selected}
                    draft={drafts[draftKey] ?? ""}
                    draftLimitReached={!drafts[draftKey] && Object.keys(drafts).length >= 30}
                    onDraftChange={updateDraft}
                    onViewed={acknowledge}
                    className="flex-1"
                  />
                )}
              </>
            ) : (
              <PageEmptyState
                className="flex-1"
                title="Select a conversation"
                description="Choose a thread from the inbox to read and reply."
                icon={<Inbox className="size-5" />}
              />
            )}
          </section>
          {selected?.contact_id ? (
            <aside aria-label="Contact details" className="hidden w-80 shrink-0 border-l xl:flex">
              {contact.isError ? (
                <PageErrorState
                  message="Couldn't load contact details."
                  onRetry={() => void contact.refetch()}
                />
              ) : (
                <ConversationContextPanel
                  workspaceId={workspaceId}
                  contact={contact.data ?? null}
                  conversation={selected}
                  className="min-h-0 flex-1"
                />
              )}
            </aside>
          ) : null}
        </div>
      </div>
    </div>
  );
}
