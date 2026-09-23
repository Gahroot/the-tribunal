"use client";

import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  KanbanSquare,
  LayoutGrid,
  List as ListIcon,
  MoreVertical,
  Plus,
  Search,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  PageEmptyState,
  PageErrorState,
  PageLoadingState,
} from "@/components/ui/page-state";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebouncedSearch } from "@/hooks/useDebouncedSearch";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { opportunitiesApi } from "@/lib/api/opportunities";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { formatCompactCurrency, formatCurrency } from "@/lib/utils/number";
import type {
  Opportunity,
  OpportunityStatus,
  Pipeline,
  PipelineStage,
} from "@/types";

import { OpportunityCreateSheet } from "./opportunity-create-sheet";
import { OpportunityDetailSheet } from "./opportunity-detail-sheet";

const BOARD_PAGE_SIZE = 200;

/**
 * The board's single accent. Amber is reserved for money figures and won
 * states only — stage names, controls, and decoration stay neutral.
 */
const MONEY = "text-amber-700 dark:text-amber-400";

/** Shared white-card surface for deals in both views (neutral canvas behind it). */
const CARD_SURFACE =
  "rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900";

type BoardView = "board" | "list";

interface StageTotal {
  count: number;
  total: number;
  currency: string;
}

export function OpportunitiesBoard() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  const {
    data: pipelines,
    isPending: pipelinesPending,
    isError: pipelinesError,
    refetch: refetchPipelines,
  } = useQuery({
    queryKey: queryKeys.opportunities.pipelines(workspaceId ?? ""),
    queryFn: () => opportunitiesApi.listPipelines(workspaceId!),
    enabled: !!workspaceId,
  });

  const createPipeline = useMutation({
    mutationFn: () =>
      opportunitiesApi.createPipeline(workspaceId!, { name: "Sales Pipeline" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.pipelines(workspaceId!),
      });
    },
    onError: (err: unknown) =>
      toast.error(getApiErrorMessage(err, "Failed to create pipeline")),
  });

  // The promotion flow uses the earliest active pipeline; mirror that here.
  const defaultPipeline = useMemo<Pipeline | undefined>(() => {
    if (!pipelines || pipelines.length === 0) return undefined;
    return [...pipelines].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    )[0];
  }, [pipelines]);

  if (!workspaceId || pipelinesPending) {
    return <PageLoadingState message="Loading pipeline…" />;
  }

  if (pipelinesError) {
    return (
      <PageErrorState
        message="Couldn't load pipelines."
        onRetry={() => void refetchPipelines()}
      />
    );
  }

  if (!defaultPipeline) {
    return (
      <PageEmptyState
        icon={<KanbanSquare className="h-10 w-10" />}
        title="No pipeline yet"
        description="Pipelines track opportunities from first contact to closed deal."
        action={
          <Button
            onClick={() => createPipeline.mutate()}
            disabled={createPipeline.isPending}
          >
            {createPipeline.isPending ? "Creating pipeline…" : "Create pipeline"}
          </Button>
        }
      />
    );
  }

  return <PipelineBoard workspaceId={workspaceId} pipeline={defaultPipeline} />;
}

function PipelineBoard({
  workspaceId,
  pipeline,
}: {
  workspaceId: string;
  pipeline: Pipeline;
}) {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createStageId, setCreateStageId] = useState<string | undefined>(undefined);
  const [view, setView] = useState<BoardView>("board");
  // Set while a pointer drag is in flight so releasing the card doesn't also
  // fire its click handler and open the detail sheet.
  const suppressOpenRef = useRef(false);

  const sensors = useSensors(
    // Require a small drag distance so a plain click still opens the card.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );

  const stages = useMemo<PipelineStage[]>(
    () => [...pipeline.stages].sort((a, b) => a.order - b.order),
    [pipeline.stages]
  );

  const listParams = { pipeline_id: pipeline.id };
  const listKey = queryKeys.opportunities.list(workspaceId, listParams);

  const {
    data,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: listKey,
    queryFn: () =>
      opportunitiesApi.list(workspaceId, {
        ...listParams,
        page_size: BOARD_PAGE_SIZE,
      }),
    enabled: !!workspaceId,
  });

  const moveMutation = useMutation({
    mutationFn: ({
      opportunityId,
      stageId,
    }: {
      opportunityId: string;
      stageId: string;
      /** True when this mutation came from the toast's Undo action. */
      isUndo?: boolean;
    }) =>
      opportunitiesApi.update(workspaceId, opportunityId, { stage_id: stageId }),
    onMutate: async ({ opportunityId, stageId }) => {
      await queryClient.cancelQueries({ queryKey: listKey });
      const previous = queryClient.getQueryData<{ items: Opportunity[] }>(listKey);
      const stage = stages.find((s) => s.id === stageId);
      // Remember where the deal came from so success can offer a one-click undo.
      const fromStageId = previous?.items.find((o) => o.id === opportunityId)
        ?.stage_id;
      queryClient.setQueryData<typeof previous>(listKey, (current) => {
        if (!current) return current;
        return {
          ...current,
          items: current.items.map((opp) =>
            opp.id === opportunityId
              ? {
                  ...opp,
                  stage_id: stageId,
                  probability: stage?.probability ?? opp.probability,
                }
              : opp
          ),
        };
      });
      return { previous, fromStageId };
    },
    onError: (err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(listKey, context.previous);
      }
      toast.error(getApiErrorMessage(err, "Failed to move opportunity"));
    },
    onSuccess: (_data, { opportunityId, stageId, isUndo }, context) => {
      const stageName = stages.find((s) => s.id === stageId)?.name ?? "stage";
      const opportunity = context?.previous?.items.find(
        (o) => o.id === opportunityId
      );
      const fromStageId = context?.fromStageId;

      if (isUndo || !fromStageId || fromStageId === stageId) {
        toast.success(`Moved to ${stageName}`);
        return;
      }

      const fromStageName =
        stages.find((s) => s.id === fromStageId)?.name ?? "stage";
      toast(`Moved to ${stageName}`, {
        description: `${opportunity?.name ?? "Opportunity"} · from ${fromStageName}`,
        duration: 6000,
        action: {
          label: "Undo",
          onClick: () =>
            moveMutation.mutate({
              opportunityId,
              stageId: fromStageId,
              isUndo: true,
            }),
        },
      });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.all(workspaceId),
      });
    },
  });

  const search = useDebouncedSearch({ delay: 300 });
  const query = search.debouncedValue.trim().toLowerCase();

  const allOpportunities = useMemo(() => data?.items ?? [], [data]);
  const opportunities = useMemo(() => {
    if (!query) return allOpportunities;
    return allOpportunities.filter((opp) =>
      opp.name.toLowerCase().includes(query),
    );
  }, [allOpportunities, query]);
  const byStage = useMemo(() => {
    const map = new Map<string, Opportunity[]>();
    for (const stage of stages) map.set(stage.id, []);
    for (const opp of opportunities) {
      if (opp.stage_id && map.has(opp.stage_id)) {
        map.get(opp.stage_id)!.push(opp);
      }
    }
    return map;
  }, [opportunities, stages]);

  // Per-column count + money total, derived from the currently visible deals.
  const stageTotals = useMemo(() => {
    const map = new Map<string, StageTotal>();
    for (const stage of stages) {
      map.set(stage.id, { count: 0, total: 0, currency: "" });
    }
    for (const opp of opportunities) {
      const total = opp.stage_id ? map.get(opp.stage_id) : undefined;
      if (!total) continue;
      total.count += 1;
      if (opp.amount != null && Number.isFinite(opp.amount)) {
        if (!total.currency) total.currency = opp.currency;
        total.total += opp.amount;
      }
    }
    return map;
  }, [opportunities, stages]);

  // One quiet summary line for the toolbar / list footer (no metric tiles).
  const summary = useMemo(() => {
    const wonStageIds = new Set(
      stages.filter((s) => s.stage_type === "won").map((s) => s.id)
    );
    let count = 0;
    let total = 0;
    let wonTotal = 0;
    let currency = "";
    for (const opp of opportunities) {
      count += 1;
      if (opp.amount != null && Number.isFinite(opp.amount)) {
        if (!currency) currency = opp.currency;
        total += opp.amount;
        if (opp.stage_id && wonStageIds.has(opp.stage_id)) wonTotal += opp.amount;
      }
    }
    return { count, total, wonTotal, currency };
  }, [opportunities, stages]);

  const screenReaderInstructions = useMemo(
    () => ({
      draggable:
        "To move this deal with a pointer, press and hold, drag it to another column, and release. " +
        "To move it without dragging, focus the deal's actions menu button, choose a stage under Move to, then press Enter. " +
        "Press Escape to close the menu.",
    }),
    []
  );

  const announcements: Announcements = useMemo(() => {
    const opportunityName = (id: string | number) =>
      opportunities.find((o) => o.id === String(id))?.name ?? "the deal";
    const stageName = (id: string | number) =>
      stages.find((s) => s.id === String(id))?.name ?? "that column";
    return {
      onDragStart: ({ active }) => `Picked up ${opportunityName(active.id)}.`,
      onDragOver: ({ active, over }) =>
        over
          ? `${opportunityName(active.id)} is over the ${stageName(over.id)} column.`
          : `${opportunityName(active.id)} is not over a column.`,
      onDragEnd: ({ active, over }) =>
        over
          ? `Dropped ${opportunityName(active.id)} into the ${stageName(over.id)} column.`
          : `Dropped ${opportunityName(active.id)}.`,
      onDragCancel: ({ active }) =>
        `Cancelled moving ${opportunityName(active.id)}. It stayed in its previous column.`,
    };
  }, [opportunities, stages]);

  const activeOpportunity = activeId
    ? opportunities.find((o) => o.id === activeId)
    : undefined;

  function handleDragStart(event: DragStartEvent) {
    suppressOpenRef.current = true;
    setActiveId(String(event.active.id));
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null);
    window.setTimeout(() => {
      suppressOpenRef.current = false;
    }, 0);
    const { active, over } = event;
    if (!over) return;
    const opportunityId = String(active.id);
    const targetStageId = String(over.id);
    const opp = opportunities.find((o) => o.id === opportunityId);
    if (!opp || opp.stage_id === targetStageId) return;
    moveMutation.mutate({ opportunityId, stageId: targetStageId });
  }

  function handleDragCancel() {
    setActiveId(null);
    window.setTimeout(() => {
      suppressOpenRef.current = false;
    }, 0);
  }

  function openDetail(opportunityId: string) {
    if (suppressOpenRef.current) return;
    setSelectedId(opportunityId);
    setDetailOpen(true);
  }

  function openCreate(stageId?: string) {
    setCreateStageId(stageId);
    setCreateOpen(true);
  }

  function requestMove(opportunityId: string, stageId: string) {
    moveMutation.mutate({ opportunityId, stageId });
  }

  if (isPending) {
    return <PageLoadingState message="Loading opportunities…" />;
  }

  if (isError) {
    return (
      <PageErrorState
        message="Couldn't load opportunities."
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <>
      <div className="flex h-full min-h-0 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="text-sm font-medium text-muted-foreground">
              {pipeline.name}
            </span>
            <div className="relative">
              <Search
                className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                value={search.value}
                onChange={(e) => search.setValue(e.target.value)}
                placeholder="Search opportunities…"
                aria-label="Search opportunities"
                className="h-8 w-56 border-neutral-300 bg-white pl-8 text-sm dark:border-neutral-700 dark:bg-neutral-900"
              />
            </div>
            <p className="hidden text-xs text-muted-foreground lg:block">
              {summary.count} {summary.count === 1 ? "deal" : "deals"} ·{" "}
              <span className={cn("font-medium", MONEY)}>
                {formatCompactCurrency(summary.total, summary.currency || "USD")}
              </span>{" "}
              pipeline ·{" "}
              <span className={cn("font-medium", MONEY)}>
                {formatCompactCurrency(
                  summary.wonTotal,
                  summary.currency || "USD"
                )}
              </span>{" "}
              won
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div
              role="group"
              aria-label="View"
              className="inline-flex items-center gap-0.5 rounded-md border border-neutral-300 bg-white p-0.5 dark:border-neutral-700 dark:bg-neutral-900"
            >
              {(
                [
                  { id: "board", label: "Board", icon: LayoutGrid },
                  { id: "list", label: "List", icon: ListIcon },
                ] as const
              ).map((option) => {
                const Icon = option.icon;
                const selected = view === option.id;
                return (
                  <button
                    key={option.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setView(option.id)}
                    className={cn(
                      "inline-flex h-7 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      selected
                        ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                        : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
                    )}
                  >
                    <Icon className="size-3.5" aria-hidden="true" />
                    {option.label}
                  </button>
                );
              })}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => openCreate()}
              data-testid="add-opportunity"
              className="border-neutral-300 bg-white text-neutral-900 hover:bg-neutral-50 hover:text-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100 dark:hover:bg-neutral-800"
            >
              <Plus className="mr-1.5 h-4 w-4" />
              Add Opportunity
            </Button>
          </div>
        </div>

        {view === "board" ? (
          <DndContext
            sensors={sensors}
            accessibility={{
              announcements,
              screenReaderInstructions,
            }}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            <div className="flex min-h-0 flex-1 gap-4 overflow-x-auto pb-4">
              {stages.map((stage) => (
                <StageColumn
                  key={stage.id}
                  stage={stage}
                  stages={stages}
                  opportunities={byStage.get(stage.id) ?? []}
                  total={stageTotals.get(stage.id) ?? { count: 0, total: 0, currency: "" }}
                  onOpen={openDetail}
                  onAdd={() => openCreate(stage.id)}
                  onMove={requestMove}
                />
              ))}
            </div>

            <DragOverlay dropAnimation={null}>
              {activeOpportunity ? (
                <div className={cn(CARD_SURFACE, "w-64 p-3 shadow-xl")}>
                  <OpportunityCardBody opportunity={activeOpportunity} />
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
        ) : (
          <OpportunitiesList
            stages={stages}
            opportunities={opportunities}
            summary={summary}
            searching={query.length > 0}
            onOpen={openDetail}
            onMove={requestMove}
            onAdd={() => openCreate()}
          />
        )}
      </div>

      <OpportunityDetailSheet
        workspaceId={workspaceId}
        opportunityId={selectedId}
        stages={stages}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />

      <OpportunityCreateSheet
        workspaceId={workspaceId}
        pipelineId={pipeline.id}
        stages={stages}
        defaultStageId={createStageId}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
    </>
  );
}

function StageColumn({
  stage,
  stages,
  opportunities,
  total,
  onOpen,
  onAdd,
  onMove,
}: {
  stage: PipelineStage;
  stages: PipelineStage[];
  opportunities: Opportunity[];
  total: StageTotal;
  onOpen: (opportunityId: string) => void;
  onAdd: () => void;
  onMove: (opportunityId: string, stageId: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage.id });
  const isWon = stage.stage_type === "won";
  const headingId = `stage-heading-${stage.id}`;

  return (
    <section
      aria-labelledby={headingId}
      ref={setNodeRef}
      data-testid={`stage-column-${stage.id}`}
      className={cn(
        "flex w-72 shrink-0 flex-col rounded-xl bg-neutral-200/40 transition-shadow dark:bg-neutral-900/60",
        isOver && "ring-1 ring-neutral-400 dark:ring-neutral-600"
      )}
    >
      {/* Stage total lives in the header: deal count + money at a glance. */}
      <div
        className={cn(
          "flex items-center justify-between gap-2 px-2 py-1.5",
          isWon && "rounded-md bg-amber-50 dark:bg-amber-500/10"
        )}
      >
        <div className="flex min-w-0 items-baseline gap-1.5">
          <h2
            id={headingId}
            className={cn(
              "truncate text-sm font-medium",
              isWon
                ? "text-amber-800 dark:text-amber-300"
                : "text-foreground"
            )}
          >
            {stage.name}
          </h2>
          <span
            data-testid={`stage-count-${stage.id}`}
            className={cn(
              "rounded-full bg-neutral-200 px-1.5 py-0.5 text-xs font-medium tabular-nums dark:bg-neutral-800",
              isWon && "bg-amber-100 dark:bg-amber-500/20"
            )}
          >
            {total.count}
          </span>
        </div>
        <span
          data-testid={`stage-total-${stage.id}`}
          className={cn("shrink-0 text-xs font-semibold tabular-nums", MONEY)}
        >
          {formatCompactCurrency(total.total, total.currency || "USD")}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-1">
        {opportunities.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-3 py-6 text-center">
            <p className="text-xs text-muted-foreground">No opportunities</p>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-muted-foreground hover:text-foreground"
              onClick={onAdd}
              data-testid={`add-opportunity-${stage.id}`}
            >
              <Plus className="mr-1 h-3.5 w-3.5" />
              Add deal
            </Button>
          </div>
        ) : (
          opportunities.map((opportunity) => (
            <OpportunityCard
              key={opportunity.id}
              opportunity={opportunity}
              stages={stages}
              onOpen={onOpen}
              onMove={onMove}
            />
          ))
        )}
      </div>
    </section>
  );
}

function OpportunityCard({
  opportunity,
  stages,
  onOpen,
  onMove,
}: {
  opportunity: Opportunity;
  stages: PipelineStage[];
  onOpen: (opportunityId: string) => void;
  onMove: (opportunityId: string, stageId: string) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: opportunity.id,
  });

  return (
    <div
      ref={setNodeRef}
      className={cn("relative", isDragging && "opacity-40")}
      data-testid={`opportunity-card-${opportunity.id}`}
    >
      <button
        type="button"
        className={cn(
          CARD_SURFACE,
          "w-full cursor-grab p-3 pr-8 text-left transition-colors active:cursor-grabbing",
          "hover:border-neutral-300 dark:hover:border-neutral-700",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        )}
        onClick={() => onOpen(opportunity.id)}
        {...attributes}
        {...listeners}
      >
        <OpportunityCardBody opportunity={opportunity} />
      </button>

      <StageMoveMenu
        opportunity={opportunity}
        stages={stages}
        onMove={onMove}
        triggerClassName="absolute right-1 top-1"
      />
    </div>
  );
}

/**
 * Keyboard-accessible alternative to dragging: a labelled actions menu that
 * moves the deal to any other stage (WCAG 2.2 AA — keyboard operable).
 */
function StageMoveMenu({
  opportunity,
  stages,
  onMove,
  triggerClassName,
}: {
  opportunity: Opportunity;
  stages: PipelineStage[];
  onMove: (opportunityId: string, stageId: string) => void;
  triggerClassName?: string;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "rounded p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          triggerClassName
        )}
        aria-label={`Actions for ${opportunity.name}`}
        onClick={(e) => e.stopPropagation()}
      >
        <MoreVertical className="h-4 w-4" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Move to</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {stages
          .filter((s) => s.id !== opportunity.stage_id)
          .map((stage) => (
            <DropdownMenuItem
              key={stage.id}
              onClick={() => onMove(opportunity.id, stage.id)}
            >
              {stage.name}
            </DropdownMenuItem>
          ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function OpportunityCardBody({ opportunity }: { opportunity: Opportunity }) {
  return (
    <div>
      <p className="line-clamp-2 text-sm font-medium text-foreground">
        {opportunity.name}
      </p>
      <div className="mt-2 flex items-baseline justify-between gap-2">
        {opportunity.amount != null ? (
          <span
            className={cn(
              "text-sm font-semibold tabular-nums",
              MONEY
            )}
          >
            {formatCurrency(opportunity.amount, opportunity.currency)}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">No amount</span>
        )}
        <span className="text-xs tabular-nums text-muted-foreground">
          {opportunity.probability}%
        </span>
      </div>
      {opportunity.expected_close_date ? (
        <p className="mt-1 text-xs text-muted-foreground">
          Closes {formatDate(opportunity.expected_close_date)}
        </p>
      ) : null}
    </div>
  );
}

function StatusBadge({ status }: { status: OpportunityStatus }) {
  const isWon = status === "won";
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-neutral-200 text-neutral-600 dark:border-neutral-700 dark:text-neutral-400",
        isWon &&
          "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300"
      )}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}

function OpportunitiesList({
  stages,
  opportunities,
  summary,
  searching,
  onOpen,
  onMove,
  onAdd,
}: {
  stages: PipelineStage[];
  opportunities: Opportunity[];
  summary: StageTotal & { wonTotal: number };
  searching: boolean;
  onOpen: (opportunityId: string) => void;
  onMove: (opportunityId: string, stageId: string) => void;
  onAdd: () => void;
}) {
  const stageById = useMemo(
    () => new Map(stages.map((s) => [s.id, s])),
    [stages]
  );

  const sorted = useMemo(() => {
    const orderOf = (opp: Opportunity) => {
      const stage = opp.stage_id ? stageById.get(opp.stage_id) : undefined;
      return stage ? stage.order : Number.MAX_SAFE_INTEGER;
    };
    return [...opportunities].sort(
      (a, b) => orderOf(a) - orderOf(b) || a.name.localeCompare(b.name)
    );
  }, [opportunities, stageById]);

  if (opportunities.length === 0) {
    return (
      <PageEmptyState
        icon={<KanbanSquare className="h-10 w-10" />}
        title={searching ? "No matches" : "No opportunities yet"}
        description={
          searching
            ? "No opportunities match your search. Try a different term."
            : "Add your first opportunity to start tracking deals in this pipeline."
        }
        action={
          searching ? undefined : (
            <Button onClick={onAdd}>
              <Plus className="mr-1.5 h-4 w-4" />
              Add Opportunity
            </Button>
          )
        }
      />
    );
  }

  return (
    <div
      className={cn(CARD_SURFACE, "min-h-0 flex-1 overflow-auto")}
      data-testid="opportunities-list"
    >
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-none hover:bg-transparent">
            <TableHead>Opportunity</TableHead>
            <TableHead>Stage</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead className="text-right">Probability</TableHead>
            <TableHead>Close date</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="w-12">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((opportunity) => {
            const stage = opportunity.stage_id
              ? stageById.get(opportunity.stage_id)
              : undefined;
            return (
              <TableRow
                key={opportunity.id}
                data-testid={`opportunity-row-${opportunity.id}`}
                className="hover:bg-none hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
              >
                <TableCell>
                  <button
                    type="button"
                    onClick={() => onOpen(opportunity.id)}
                    className="rounded text-left font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {opportunity.name}
                  </button>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {stage?.name ?? "—"}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right font-semibold tabular-nums",
                    opportunity.amount != null
                      ? MONEY
                      : "font-normal text-muted-foreground"
                  )}
                >
                  {opportunity.amount != null
                    ? formatCurrency(
                        opportunity.amount,
                        opportunity.currency
                      )
                    : "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {opportunity.probability}%
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {opportunity.expected_close_date
                    ? formatDate(opportunity.expected_close_date)
                    : "—"}
                </TableCell>
                <TableCell>
                  <StatusBadge status={opportunity.status} />
                </TableCell>
                <TableCell className="text-right">
                  <StageMoveMenu
                    opportunity={opportunity}
                    stages={stages}
                    onMove={onMove}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
        <TableFooter className="bg-neutral-50 dark:bg-neutral-800/60">
          <tr>
            <TableCell colSpan={2} className="font-medium text-muted-foreground">
              {summary.count} {summary.count === 1 ? "opportunity" : "opportunities"}
            </TableCell>
            <TableCell
              className={cn(
                "text-right font-semibold tabular-nums",
                MONEY
              )}
            >
              {formatCompactCurrency(summary.total, summary.currency || "USD")}
            </TableCell>
            <TableCell colSpan={4} className="text-right text-muted-foreground">
              Won{" "}
              <span className={cn("font-semibold", MONEY)}>
                {formatCompactCurrency(
                  summary.wonTotal,
                  summary.currency || "USD"
                )}
              </span>
            </TableCell>
          </tr>
        </TableFooter>
      </Table>
    </div>
  );
}
