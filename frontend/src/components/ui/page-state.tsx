import * as React from "react"
import { AlertCircle, Inbox, Loader2 } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

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
  title: string
  description?: string
  icon?: React.ReactNode
  action?: React.ReactNode
}

export function PageEmptyState({
  title,
  description,
  icon,
  action,
  ...props
}: PageEmptyStateProps) {
  return (
    <PageStateWrapper {...props}>
      <div className="text-muted-foreground">
        {icon ?? <Inbox className="size-8" />}
      </div>
      <div className="space-y-1">
        <h3 className="text-base font-medium">{title}</h3>
        {description ? (
          <p className="text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action}
    </PageStateWrapper>
  )
}
