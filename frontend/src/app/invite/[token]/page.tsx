"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Loader2, Users, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { use, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageLoadingState } from "@/components/ui/page-state";
import { invitationsApi } from "@/lib/api/invitations";
import { buildLoginHref, invitePath } from "@/lib/auth/return-to";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { useAuth } from "@/providers/auth-provider";
import { useWorkspace } from "@/providers/workspace-provider";

interface PageProps {
  params: Promise<{ token: string }>;
}

function getHttpStatus(err: unknown): number | null {
  if (typeof err !== "object" || err === null) return null;
  const status = (err as { response?: { status?: unknown } }).response?.status;
  return typeof status === "number" ? status : null;
}

function StatusCard({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full">
            {icon}
          </div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        {children && (
          <CardFooter className="flex flex-col gap-2">{children}</CardFooter>
        )}
      </Card>
    </div>
  );
}

export default function InviteAcceptPage({ params }: PageProps) {
  const { token } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, isLoading: isAuthLoading, isAuthenticated, logout } = useAuth();
  const { setCurrentWorkspace } = useWorkspace();
  const [joinedMessage, setJoinedMessage] = useState<string | null>(null);
  const returnPath = invitePath(token);

  // Fetch invitation details (public endpoint). Errors render inline recovery
  // instead of escalating to the app error boundary.
  const {
    data: invitation,
    isPending: isInvitationLoading,
    error,
    refetch,
    isFetching: isInvitationFetching,
  } = useQuery({
    queryKey: queryKeys.invitations.byToken(token),
    queryFn: () => invitationsApi.getByToken(token),
    retry: false,
    throwOnError: false,
  });

  const acceptMutation = useMutation({
    mutationFn: () => invitationsApi.accept(token),
    throwOnError: false,
    onSuccess: async (data) => {
      const message = data.message || "Invitation accepted";
      setJoinedMessage(message);
      // Refresh membership first so the joined workspace is in the list, then
      // select it through the workspace provider's contract.
      await queryClient.invalidateQueries({ queryKey: queryKeys.workspaces.all() });
      if (data.workspace_id) {
        setCurrentWorkspace(data.workspace_id);
      } else {
        void queryClient.invalidateQueries({ queryKey: queryKeys.auth.user() });
      }
      toast.success(message);
      router.replace("/");
    },
    onError: (err) => {
      const status = getHttpStatus(err);
      if (status === 400 || status === 404) {
        // The link expired, was used, or was cancelled since it loaded —
        // refetch so the page shows that state and its recovery.
        void queryClient.invalidateQueries({
          queryKey: queryKeys.invitations.byToken(token),
        });
      }
    },
  });

  // Sign out of the current session and come back here after signing in.
  const switchAccount = () => logout({ redirectTo: returnPath });
  const goToSignIn = () => router.push(buildLoginHref(returnPath));
  const goHome = () => router.push(isAuthenticated ? "/" : "/login");
  const homeLabel = isAuthenticated ? "Go to Dashboard" : "Sign In";

  if (joinedMessage) {
    return (
      <StatusCard
        icon={<CheckCircle2 className="h-6 w-6 text-success" />}
        title="You're in!"
        description={
          <>
            {joinedMessage}.{" "}
            {invitation ? `Opening ${invitation.workspace_name}…` : "Opening your workspace…"}
          </>
        }
      />
    );
  }

  if (isAuthLoading || isInvitationLoading) {
    return <PageLoadingState className="min-h-screen" />;
  }

  if (error || !invitation) {
    if (getHttpStatus(error) === 404) {
      return (
        <StatusCard
          icon={<XCircle className="h-6 w-6 text-destructive" />}
          title="Invalid Invitation"
          description="This invitation link isn't valid. Check that you copied the whole link, or ask the workspace administrator to send a new invitation."
        >
          <Button variant="outline" className="w-full" onClick={goHome}>
            {homeLabel}
          </Button>
        </StatusCard>
      );
    }
    return (
      <StatusCard
        icon={<XCircle className="h-6 w-6 text-destructive" />}
        title="Couldn't Load Invitation"
        description="Something went wrong while loading this invitation. Check your connection and try again."
      >
        <Button
          className="w-full"
          onClick={() => void refetch()}
          disabled={isInvitationFetching}
        >
          {isInvitationFetching && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Try Again
        </Button>
      </StatusCard>
    );
  }

  if (invitation.is_expired) {
    return (
      <StatusCard
        icon={<Clock className="h-6 w-6 text-warning" />}
        title="Invitation Expired"
        description="This invitation has expired. Please contact the workspace administrator to request a new invitation."
      >
        <Button variant="outline" className="w-full" onClick={goHome}>
          {homeLabel}
        </Button>
      </StatusCard>
    );
  }

  if (!invitation.is_valid) {
    return (
      <StatusCard
        icon={<XCircle className="h-6 w-6 text-destructive" />}
        title="Invitation Already Used"
        description={`This invitation to ${invitation.workspace_name} has already been accepted or was cancelled. If you accepted it, sign in to open the workspace; otherwise ask the administrator for a new invitation.`}
      >
        <Button variant="outline" className="w-full" onClick={goHome}>
          {homeLabel}
        </Button>
      </StatusCard>
    );
  }

  const isWrongAccount =
    isAuthenticated &&
    !!user &&
    user.email.toLowerCase() !== invitation.email.toLowerCase();
  const acceptError = acceptMutation.error;
  const acceptErrorStatus = getHttpStatus(acceptError);

  let acceptErrorMessage: string | null = null;
  if (acceptError) {
    if (acceptErrorStatus === 401) {
      acceptErrorMessage = "Your session has expired. Sign in again to accept this invitation.";
    } else if (acceptErrorStatus === 403) {
      acceptErrorMessage = `This invitation was sent to ${invitation.email}. Sign in with that account to accept it.`;
    } else {
      acceptErrorMessage = `We couldn't accept the invitation: ${getApiErrorMessage(
        acceptError,
        "please try again."
      )}`;
    }
  }
  const needsReauth =
    isWrongAccount || acceptErrorStatus === 401 || acceptErrorStatus === 403;

  // Valid invitation - show details
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full">
            <Users className="h-6 w-6 text-muted-foreground" />
          </div>
          <CardTitle>You&apos;re Invited!</CardTitle>
          <CardDescription>
            {invitation.invited_by_name
              ? `${invitation.invited_by_name} has invited you to join`
              : "You've been invited to join"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border bg-muted/50 p-4 text-center">
            <h3 className="text-lg font-semibold">{invitation.workspace_name}</h3>
            <div className="mt-2 flex items-center justify-center gap-2">
              <Badge variant="secondary" className="capitalize">
                {invitation.role}
              </Badge>
            </div>
          </div>

          <div className="text-center text-sm text-muted-foreground">
            <p>
              You&apos;ll join as{" "}
              {invitation.role === "admin" ? "an administrator" : "a team member"}.
            </p>
          </div>

          {!isAuthenticated && (
            <div className="rounded-lg border bg-background p-3 text-center text-sm">
              <p className="text-foreground">
                Sign in or create an account with {invitation.email} to accept this invitation.
              </p>
            </div>
          )}

          {isWrongAccount && !acceptErrorMessage && (
            <div className="rounded-lg border bg-background p-3 text-center text-sm">
              <p className="text-foreground">
                This invitation was sent to {invitation.email}. You&apos;re
                currently signed in as {user?.email}.
              </p>
            </div>
          )}

          {acceptErrorMessage && (
            <div
              role="alert"
              className="rounded-lg border border-destructive/50 bg-background p-3 text-center text-sm text-destructive"
            >
              {acceptErrorMessage}
            </div>
          )}
        </CardContent>
        <CardFooter className="flex flex-col gap-2">
          {!isAuthenticated ? (
            <>
              <Button className="w-full" onClick={goToSignIn}>
                Sign in to Accept
              </Button>
              <Button variant="outline" className="w-full" onClick={() => router.push(`${buildLoginHref(returnPath)}&mode=register`)}>
                Create an Account to Accept
              </Button>
            </>
          ) : needsReauth ? (
            <Button className="w-full" onClick={switchAccount}>
              Sign in as {invitation.email}
            </Button>
          ) : (
            <Button
              className="w-full"
              onClick={() => acceptMutation.mutate()}
              disabled={acceptMutation.isPending}
            >
              {acceptMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              {acceptMutation.isPending
                ? "Accepting..."
                : acceptError
                  ? "Try Again"
                  : "Accept Invitation"}
            </Button>
          )}
          <Button variant="ghost" className="w-full" onClick={goHome}>
            {isAuthenticated ? "Maybe Later" : "Go Back"}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
