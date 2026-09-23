"use client";

import { BookmarkPlus, MessageSquare, Search, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  PageEmptyState,
  PageErrorState,
} from "@/components/ui/page-state";
import { Skeleton } from "@/components/ui/skeleton";
import { contactStatusDotColors } from "@/lib/status-colors";
import { cn } from "@/lib/utils";
import { formatRelative } from "@/lib/utils/date";
import { getContactInitials } from "@/lib/utils/initials";
import { formatPhoneNumber } from "@/lib/utils/phone";
import type { Contact, Conversation } from "@/types";

/** Built-in views: every thread, threads waiting on me, hot leads. */
export type BuiltInView = "all" | "waiting" | "hot";

/** A user-named filter (Missive-style saved view), persisted per workspace. */
export interface SavedView {
  id: string;
  name: string;
  view: BuiltInView;
  search: string;
}

/** One list row: a conversation joined with its contact when known. */
export interface InboxRow {
  conversation: Conversation;
  contact?: Contact;
}

const BUILT_IN_VIEWS: { id: BuiltInView; label: string }[] = [
  { id: "all", label: "All" },
  { id: "waiting", label: "Waiting on me" },
  { id: "hot", label: "Hot leads" },
];

interface ConversationListProps {
  rows: InboxRow[];
  counts: { all: number; waiting: number; hot: number };
  activeViewId: string;
  savedViews: SavedView[];
  search: string;
  selectedId: string | null;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
  canSaveViews: boolean;
  onSelect: (conversation: Conversation) => void;
  onViewChange: (viewId: string) => void;
  onSearchChange: (search: string) => void;
  onApplySavedView: (view: SavedView) => void;
  onSaveView: (name: string) => void;
  onDeleteSavedView: (id: string) => void;
  className?: string;
}

/**
 * Column 1 of the inbox: filterable conversation list with built-in views
 * ("Waiting on me", "Hot leads"), search, and named saved views.
 */
export function ConversationList({
  rows,
  counts,
  activeViewId,
  savedViews,
  search,
  selectedId,
  isPending,
  isError,
  onRetry,
  canSaveViews,
  onSelect,
  onViewChange,
  onSearchChange,
  onApplySavedView,
  onSaveView,
  onDeleteSavedView,
  className,
}: ConversationListProps) {
  const [isNaming, setIsNaming] = useState(false);
  const [viewName, setViewName] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Move focus into the name field when it appears — programmatic focus on
  // reveal is the accessible equivalent of autoFocus (which jsx-a11y rejects).
  useEffect(() => {
    if (isNaming) nameInputRef.current?.focus();
  }, [isNaming]);

  const hasActiveFilter = activeViewId !== "all" || search.trim().length > 0;
  const canSave = canSaveViews && hasActiveFilter;

  const cancelNaming = () => {
    setIsNaming(false);
    setViewName("");
  };

  const handleSaveSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = viewName.trim();
    if (!name) return;
    onSaveView(name);
    cancelNaming();
  };

  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-col overflow-hidden bg-background",
        className,
      )}
    >
      <div className="flex shrink-0 items-center justify-between border-b px-3 py-2.5">
        <h1 className="text-sm font-semibold">Conversations</h1>
        <span className="text-xs tabular-nums text-muted-foreground">
          {counts.all} total
        </span>
      </div>

      <div className="shrink-0 space-y-2 border-b p-3">
        <div className="relative">
          <Search
            aria-hidden
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search name, number, message…"
            aria-label="Search conversations"
            className="h-9 pl-8 pr-8"
          />
          {search ? (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2"
              aria-label="Clear search"
              onClick={() => onSearchChange("")}
            >
              <X aria-hidden className="h-3.5 w-3.5" />
            </Button>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {BUILT_IN_VIEWS.map((view) => {
            const isActive = activeViewId === view.id;
            const count = counts[view.id];
            return (
              <button
                key={view.id}
                type="button"
                aria-pressed={isActive}
                onClick={() => onViewChange(view.id)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isActive
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-muted/40 text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {view.label}
                <span className="tabular-nums opacity-80">{count}</span>
              </button>
            );
          })}
        </div>

        {savedViews.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Saved
            </span>
            {savedViews.map((view) => {
              const isActive = activeViewId === `saved:${view.id}`;
              return (
                <span
                  key={view.id}
                  className={cn(
                    "inline-flex items-center overflow-hidden rounded-full border",
                    isActive ? "border-primary bg-primary/10" : "border-border",
                  )}
                >
                  <button
                    type="button"
                    aria-pressed={isActive}
                    onClick={() => onApplySavedView(view)}
                    className={cn(
                      "px-2.5 py-1 text-xs font-medium transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                      isActive
                        ? "text-primary"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {view.name}
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete saved view ${view.name}`}
                    onClick={() => onDeleteSavedView(view.id)}
                    className={cn(
                      "ml-0.5 rounded-full p-0.5 text-muted-foreground transition-colors hover:text-destructive",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    )}
                  >
                    <X aria-hidden className="h-3 w-3" />
                  </button>
                </span>
              );
            })}
          </div>
        ) : null}

        {canSave ? (
          isNaming ? (
            <form
              onSubmit={handleSaveSubmit}
              className="flex items-center gap-1.5"
            >
              <Input
                ref={nameInputRef}
                value={viewName}
                onChange={(event) => setViewName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") cancelNaming();
                }}
                placeholder="View name"
                aria-label="Saved view name"
                className="h-8 flex-1"
                maxLength={40}
              />
              <Button
                type="submit"
                size="sm"
                className="h-8"
                disabled={!viewName.trim()}
              >
                Save
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8"
                onClick={cancelNaming}
              >
                Cancel
              </Button>
            </form>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8"
              onClick={() => setIsNaming(true)}
            >
              <BookmarkPlus aria-hidden className="mr-1.5 h-3.5 w-3.5" />
              Save view
            </Button>
          )
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isPending ? (
          <div className="space-y-3 p-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="flex items-center gap-3">
                <Skeleton className="h-9 w-9 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-1/2" />
                  <Skeleton className="h-3 w-3/4" />
                </div>
              </div>
            ))}
          </div>
        ) : isError ? (
          <PageErrorState
            message="We couldn't load conversations."
            onRetry={onRetry}
            retryLabel="Try again"
          />
        ) : rows.length === 0 ? (
          <PageEmptyState
            icon={<MessageSquare className="h-8 w-8" />}
            title={
              hasActiveFilter
                ? "No matching conversations"
                : "No conversations yet"
            }
            description={
              hasActiveFilter
                ? "No threads match this view or search."
                : "Inbound and outbound threads will appear here."
            }
            action={
              hasActiveFilter ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    onViewChange("all");
                    onSearchChange("");
                  }}
                >
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="divide-y">
            {rows.map(({ conversation, contact }) => {
              const isSelected = selectedId === conversation.id;
              const displayName = contact
                ? [contact.first_name, contact.last_name]
                    .filter(Boolean)
                    .join(" ")
                : "";
              const title =
                displayName ||
                formatPhoneNumber(conversation.contact_phone) ||
                conversation.contact_phone ||
                "Unknown";
              const unread = conversation.unread_count;
              const stamp = conversation.last_message_at ?? conversation.created_at;
              const score = contact?.lead_score;

              return (
                <li key={conversation.id}>
                  <button
                    type="button"
                    aria-current={isSelected ? "true" : undefined}
                    onClick={() => onSelect(conversation)}
                    className={cn(
                      "flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                      isSelected ? "bg-primary/10" : "hover:bg-accent/50",
                    )}
                  >
                    <span className="relative shrink-0">
                      <Avatar className="h-9 w-9">
                        {contact ? (
                          <AvatarImage
                            src={contact.avatar_url}
                            alt={displayName || "Contact"}
                            size={72}
                          />
                        ) : null}
                        <AvatarFallback
                          className={cn(
                            "text-xs font-medium",
                            contact
                              ? "bg-primary/10 text-primary"
                              : "bg-muted text-muted-foreground",
                          )}
                        >
                          {contact ? (
                            getContactInitials(contact)
                          ) : (
                            <MessageSquare aria-hidden className="h-4 w-4" />
                          )}
                        </AvatarFallback>
                      </Avatar>
                      {contact ? (
                        <span
                          aria-hidden
                          className={cn(
                            "absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-background",
                            contactStatusDotColors[contact.status],
                          )}
                        />
                      ) : null}
                    </span>

                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span
                          className={cn(
                            "min-w-0 truncate text-sm",
                            unread > 0 ? "font-semibold" : "font-medium",
                          )}
                        >
                          {title}
                        </span>
                        <time
                          className="shrink-0 text-[11px] font-normal text-muted-foreground"
                          dateTime={stamp}
                        >
                          {formatRelative(stamp)}
                        </time>
                      </span>
                      <span className="mt-0.5 flex items-center justify-between gap-2">
                        <span className="min-w-0 truncate text-xs text-muted-foreground">
                          {conversation.last_message_preview ||
                            "No messages yet"}
                        </span>
                        <span className="flex shrink-0 items-center gap-1">
                          {score != null && score > 0 ? (
                            <span
                              className={cn(
                                "rounded px-1 py-0.5 text-[10px] font-bold",
                                score >= 80
                                  ? "bg-success/10 text-success"
                                  : score >= 40
                                    ? "bg-warning/10 text-warning"
                                    : "bg-muted text-muted-foreground",
                              )}
                              title={`Lead score: ${score}`}
                            >
                              <span className="sr-only">Lead score </span>
                              {score}
                            </span>
                          ) : null}
                          {unread > 0 ? (
                            <Badge className="h-4 min-w-4 px-1 text-[10px] tabular-nums">
                              {unread > 99 ? "99+" : unread}
                            </Badge>
                          ) : null}
                        </span>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
