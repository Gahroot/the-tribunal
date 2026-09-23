"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MessageSquare } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ConversationFeed } from "@/components/conversation/conversation-feed";
import { ContactlessThread } from "@/components/conversations/contactless-thread";
import { ConversationContextPanel } from "@/components/conversations/conversation-context-panel";
import {
  ConversationList,
  type BuiltInView,
  type InboxRow,
  type SavedView,
} from "@/components/conversations/conversation-list";
import { Button } from "@/components/ui/button";
import {
  PageEmptyState,
  PageErrorState,
  PageLoadingState,
} from "@/components/ui/page-state";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useContactsPaginated, useContactIds } from "@/hooks/useContacts";
import { useIsMobile } from "@/hooks/useMobile";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { contactsApi } from "@/lib/api/contacts";
import { conversationsApi } from "@/lib/api/conversations";
import { messages } from "@/lib/messages";
import { queryKeys } from "@/lib/query-keys";
import { POLL_30S } from "@/lib/query-options";
import { normalizePhoneForComparison } from "@/lib/utils/phone";
import { safeGetItem, safeSetItem } from "@/lib/utils/storage";
import type { Conversation } from "@/types";

const BUILT_IN_VIEW_IDS: BuiltInView[] = ["all", "waiting", "hot"];

function isBuiltInView(value: string): value is BuiltInView {
  return BUILT_IN_VIEW_IDS.includes(value as BuiltInView);
}

function isHotRow(row: InboxRow, hotContactIds: Set<number>): boolean {
  const contactId = row.conversation.contact_id;
  if (contactId == null) return false;
  return (
    hotContactIds.has(contactId) || (row.contact?.lead_score ?? 0) >= 80
  );
}

function parseSavedViews(raw: string | null): SavedView[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is SavedView => {
      if (typeof item !== "object" || item === null) return false;
      const candidate = item as SavedView;
      return (
        typeof candidate.id === "string" &&
        typeof candidate.name === "string" &&
        typeof candidate.search === "string" &&
        typeof candidate.view === "string" &&
        isBuiltInView(candidate.view)
      );
    });
  } catch {
    return [];
  }
}

/**
 * Three-column conversations inbox.
 *
 * Column 1: filterable conversation list (waiting on me / hot leads) with
 * Missive-style named saved views. Column 2: thread + composer with an
 * AI-draft control (generate → fill → human review → send). Column 3: contact
 * details, opportunity state, and agent assignment.
 *
 * Switching threads is pure client state over React Query cache — no route
 * navigation, no page reload (reflow-not-reload). Status/assignment/send
 * mutations invalidate factory keys so every pane updates in place.
 */
export function ConversationsPage() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();

  const [activeViewId, setActiveViewId] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  // Saved views are per-workspace localStorage UI state.
  const storageKey = workspaceId ? `inbox:saved-views:${workspaceId}` : null;
  useEffect(() => {
    if (!storageKey) return;
    setSavedViews(parseSavedViews(safeGetItem(storageKey)));
  }, [storageKey]);

  // Conversations: 30s poll keeps previews and unread counts fresh.
  const {
    data: conversationsData,
    isPending: isConversationsPending,
    isError: isConversationsError,
    refetch: refetchConversations,
  } = useQuery({
    queryKey: queryKeys.conversations.list(workspaceId ?? "", {
      page: 1,
      page_size: 100,
    }),
    queryFn: () =>
      conversationsApi.list(workspaceId ?? "", { page: 1, page_size: 100 }),
    enabled: !!workspaceId,
    ...POLL_30S,
  });

  // Contacts (names, statuses, lead scores) plus the authoritative hot set.
  const { data: contactsData } = useContactsPaginated(workspaceId ?? "", {
    page: 1,
    page_size: 100,
    sort_by: "last_conversation",
  });
  const { data: hotIdsData } = useContactIds(
    workspaceId ?? "",
    { lead_score_min: 80 },
    !!workspaceId,
  );
  const hotContactIds = useMemo(
    () => new Set(hotIdsData?.ids ?? []),
    [hotIdsData?.ids],
  );

  const contactById = useMemo(
    () =>
      new Map(
        (contactsData?.items ?? []).map((contact) => [
          contact.id,
          contact,
        ] as const),
      ),
    [contactsData?.items],
  );

  const rows: InboxRow[] = useMemo(
    () =>
      (conversationsData?.items ?? []).map((conversation) => ({
        conversation,
        contact:
          conversation.contact_id != null
            ? contactById.get(conversation.contact_id)
            : undefined,
      })),
    [conversationsData?.items, contactById],
  );

  const counts = useMemo(
    () => ({
      all: rows.length,
      waiting: rows.filter((row) => row.conversation.unread_count > 0).length,
      hot: rows.filter((row) => isHotRow(row, hotContactIds)).length,
    }),
    [rows, hotContactIds],
  );

  // Resolve the active saved view into a built-in filter + its search term.
  const activeSavedView = activeViewId.startsWith("saved:")
    ? savedViews.find((view) => `saved:${view.id}` === activeViewId)
    : undefined;
  const effectiveView: BuiltInView = activeSavedView
    ? activeSavedView.view
    : isBuiltInView(activeViewId)
      ? activeViewId
      : "all";

  const filteredRows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (effectiveView === "waiting" && row.conversation.unread_count <= 0) {
        return false;
      }
      if (effectiveView === "hot" && !isHotRow(row, hotContactIds)) {
        return false;
      }
      if (!term) return true;

      const { conversation, contact } = row;
      const name = contact
        ? `${contact.first_name ?? ""} ${contact.last_name ?? ""}`.toLowerCase()
        : "";
      const phone = normalizePhoneForComparison(
        conversation.contact_phone,
      ).toLowerCase();
      const rawPhone = (conversation.contact_phone ?? "").toLowerCase();
      const email = (contact?.email ?? "").toLowerCase();
      const preview = (conversation.last_message_preview ?? "").toLowerCase();
      return (
        name.includes(term) ||
        phone.includes(term) ||
        rawPhone.includes(term) ||
        email.includes(term) ||
        preview.includes(term)
      );
    });
  }, [rows, effectiveView, search, hotContactIds]);

  // Desktop auto-selects the most recent thread; mobile waits for a tap so the
  // list stays the entry point. Either way this is state, not navigation.
  const explicitlySelected = selectedId
    ? (rows.find((row) => row.conversation.id === selectedId) ?? null)
    : null;
  const activeRow: InboxRow | null = isMobile
    ? explicitlySelected
    : (explicitlySelected ?? rows[0] ?? null);

  // Resolve the contact behind the active thread (map hit is instant; a miss
  // falls back to a detail fetch, cached per contact for instant reflow).
  const activeContactId = activeRow?.conversation.contact_id ?? null;
  const contactFromMap =
    activeContactId != null ? contactById.get(activeContactId) : undefined;
  const {
    data: fetchedContact,
    isError: isContactError,
    refetch: refetchContact,
  } = useQuery({
    queryKey: queryKeys.contacts.detail(workspaceId ?? "", activeContactId),
    queryFn: async () => {
      if (!workspaceId || activeContactId == null) {
        throw new Error("No contact selected");
      }
      return contactsApi.get(workspaceId, activeContactId);
    },
    enabled: !!workspaceId && activeContactId != null,
  });
  const activeContact = contactFromMap ?? fetchedContact ?? null;

  // All hooks above. Narrow workspaceId before the render helpers so every
  // child component receives a definite string.
  if (!workspaceId) {
    return <PageLoadingState className="h-full" message="Loading workspace…" />;
  }

  const handleSelect = (conversation: Conversation) => {
    setSelectedId(conversation.id);
    if (!workspaceId || conversation.unread_count <= 0) return;
    // Opening a thread marks it read server-side; then refresh counts in place.
    void conversationsApi
      .get(workspaceId, conversation.id)
      .then(() =>
        queryClient.invalidateQueries({
          queryKey: queryKeys.conversations.all(workspaceId),
        }),
      )
      .catch(() => {
        // Keep the badge; reselecting the thread retries the mark-read.
      });
  };

  const persistSavedViews = (views: SavedView[]) => {
    setSavedViews(views);
    if (storageKey) safeSetItem(storageKey, JSON.stringify(views));
  };

  const handleSaveView = (name: string) => {
    const view: SavedView = {
      id: crypto.randomUUID(),
      name,
      view: effectiveView,
      search,
    };
    persistSavedViews([...savedViews, view]);
    setActiveViewId(`saved:${view.id}`);
    toast.success(messages.conversations.viewSaved);
  };

  const handleDeleteSavedView = (id: string) => {
    persistSavedViews(savedViews.filter((view) => view.id !== id));
    if (activeViewId === `saved:${id}`) setActiveViewId("all");
  };

  const handleApplySavedView = (view: SavedView) => {
    setActiveViewId(`saved:${view.id}`);
    setSearch(view.search);
  };

  const renderToolbar = (showBack: boolean) => (
    <div className="flex shrink-0 items-center justify-between border-b px-2 py-1.5 xl:hidden">
      {showBack ? (
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-8 w-8"
          aria-label="Back to conversation list"
          onClick={() => setSelectedId(null)}
        >
          <ArrowLeft aria-hidden className="h-4 w-4" />
        </Button>
      ) : (
        <span />
      )}
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-8"
        onClick={() => setDetailsOpen(true)}
      >
        Details
      </Button>
    </div>
  );

  const renderThread = () => {
    if (!activeRow) {
      return (
        <PageEmptyState
          className="h-full"
          icon={<MessageSquare className="h-8 w-8" />}
          title="Select a conversation"
          description="Pick a thread from the list to read and reply."
        />
      );
    }

    const conversation = activeRow.conversation;
    if (conversation.contact_id == null) {
      return (
        <ContactlessThread
          workspaceId={workspaceId}
          conversation={conversation}
          className="h-full"
        />
      );
    }

    if (!activeContact) {
      if (isContactError) {
        return (
          <PageErrorState
            className="h-full"
            message="We couldn't load this contact."
            onRetry={() => void refetchContact()}
          />
        );
      }
      return (
        <PageLoadingState className="h-full" message="Loading conversation…" />
      );
    }

    // Keyed per contact: switching swaps cached panes in place (reflow), and
    // a fresh key drops any half-edited draft from the previous thread.
    return (
      <ConversationFeed
        key={activeContact.id}
        contact={activeContact}
        enableAIDraft
        className="h-full"
      />
    );
  };

  const contextPanel = (
    <ConversationContextPanel
      workspaceId={workspaceId}
      contact={activeContact}
      conversation={activeRow?.conversation ?? null}
    />
  );

  const listElement = (
    <ConversationList
      rows={filteredRows}
      counts={counts}
      activeViewId={activeViewId}
      savedViews={savedViews}
      search={search}
      selectedId={activeRow?.conversation.id ?? null}
      isPending={isConversationsPending}
      isError={isConversationsError}
      onRetry={() => void refetchConversations()}
      canSaveViews={!!storageKey}
      onSelect={handleSelect}
      onViewChange={setActiveViewId}
      onSearchChange={setSearch}
      onApplySavedView={handleApplySavedView}
      onSaveView={handleSaveView}
      onDeleteSavedView={handleDeleteSavedView}
      className={isMobile ? "h-full" : "border-r"}
    />
  );

  return (
    <div className="h-full overflow-hidden">
      {isMobile ? (
        !activeRow ? (
          listElement
        ) : (
          <div className="flex h-full flex-col overflow-hidden">
            {renderToolbar(true)}
            <div className="min-h-0 flex-1 overflow-hidden">
              {renderThread()}
            </div>
          </div>
        )
      ) : (
        <div className="grid h-full grid-cols-1 overflow-hidden md:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)_340px]">
          {listElement}
          <div className="flex h-full min-w-0 flex-col overflow-hidden">
            {renderToolbar(false)}
            <div className="min-h-0 flex-1 overflow-hidden">
              {renderThread()}
            </div>
          </div>
          <div className="hidden border-l xl:block">{contextPanel}</div>
        </div>
      )}

      {/* Context as a sheet on mobile and md–xl (column shows at xl+). */}
      <Sheet open={detailsOpen} onOpenChange={setDetailsOpen}>
        <SheetContent side="right" className="w-full p-0 sm:w-[400px]">
          <SheetHeader className="sr-only">
            <SheetTitle>Conversation details</SheetTitle>
          </SheetHeader>
          {contextPanel}
        </SheetContent>
      </Sheet>
    </div>
  );
}
