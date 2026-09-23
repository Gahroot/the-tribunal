import { AlertCircle, Inbox, Loader2 } from "lucide-react"
import Link from "next/link"
import * as React from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type PageStateWrapperProps = React.HTMLAttributes<HTMLDivElement>

function PageStateWrapper({ className, ...props }: PageStateWrapperProps) {
  return (
    <div
      data-slot="page-state"
      className={cn(
        "flex min-h-[240px] w-full flex-col items-center justify-center gap-3 p-8 text-center",
        className,
      )}
      {...props}
    />
  )
}

export interface PageLoadingStateProps extends PageStateWrapperProps {
  message?: string
}

export function PageLoadingState({ message, ...props }: PageLoadingStateProps) {
  return (
    <PageStateWrapper {...props}>
      <Loader2 className="size-8 animate-spin text-muted-foreground" />
      {message ? (
        <p className="text-sm text-muted-foreground">{message}</p>
      ) : null}
    </PageStateWrapper>
  )
}

export interface PageErrorStateProps extends PageStateWrapperProps {
  message?: string
  onRetry?: () => void
  retryLabel?: string
}

export function PageErrorState({
  message = "Something went wrong.",
  onRetry,
  retryLabel = "Try again",
  ...props
}: PageErrorStateProps) {
  return (
    <PageStateWrapper {...props}>
      <AlertCircle className="size-8 text-destructive" />
      <p className="text-sm text-muted-foreground">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </PageStateWrapper>
  )
}

export interface PageEmptyStateProps extends PageStateWrapperProps {
  /** Short heading: name the state (e.g. "No campaigns yet", "All clear"). */
  title: string
  /**
   * One line explaining what lives here once items exist.
   * Required so every empty state says what belongs on the screen.
   */
  description: string
  /** Decorative icon; omitted defaults to the inbox glyph. */
  icon?: React.ReactNode
  /**
   * Custom action node. Wins over `actionLabel`/`actionHref` when provided
   * (e.g. dialog triggers, "Clear filters").
   */
  action?: React.ReactNode
  /**
   * Label for the single primary CTA (e.g. "Create campaign"). Pair with
   * `actionHref` so the button deep-links to the create flow.
   */
  actionLabel?: string
  /** Route the primary CTA deep-links to (e.g. "/campaigns/new"). */
  actionHref?: string
}

export function PageEmptyState({
  title,
  description,
  icon,
  action,
  actionLabel,
  actionHref,
  ...props
}: PageEmptyStateProps) {
  const cta =
    action ??
    (actionLabel && actionHref ? (
      <Button asChild>
        <Link href={actionHref}>{actionLabel}</Link>
      </Button>
    ) : undefined)

  return (
    <PageStateWrapper {...props}>
      <div className="text-muted-foreground">
        {icon ?? <Inbox className="size-8" />}
      </div>
      <div className="space-y-1">
        <h3 className="text-base font-medium">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {cta}
    </PageStateWrapper>
  )
}
