"use client";

import { useState } from "react";

import { LoginForm } from "@/components/auth/login-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageLoadingState } from "@/components/ui/page-state";
import { useAuth } from "@/providers/auth-provider";

interface LoginClientProps {
  /** Already-validated local path to return to after sign-in. */
  redirectTo?: string | null;
  initialRegister?: boolean;
}

export function LoginClient({ redirectTo = null, initialRegister = false }: LoginClientProps) {
  const [isRegister, setIsRegister] = useState(initialRegister);
  const { isLoading } = useAuth();
  const isInvitation = redirectTo?.startsWith("/invite/") ?? false;

  if (isLoading) {
    return <PageLoadingState className="min-h-screen" />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">{isRegister ? "Create an account" : "Welcome back"}</CardTitle>
          <CardDescription>
            {isInvitation
              ? `${isRegister ? "Create an account" : "Sign in"} to accept your workspace invitation`
              : isRegister ? "Create your account to get started" : "Sign in to your account to continue"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm redirectTo={redirectTo} isRegister={isRegister} onModeChange={setIsRegister} />
        </CardContent>
      </Card>
    </div>
  );
}
