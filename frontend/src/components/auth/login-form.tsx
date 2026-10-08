"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { register } from "@/lib/api/auth";
import { cn } from "@/lib/utils";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { useAuth } from "@/providers/auth-provider";

const loginSchema = z.object({
  email: z.email({ error: "Please enter a valid email address" }),
  password: z.string().min(1, { error: "Password is required" }),
});

const registerSchema = loginSchema.extend({
  password: z.string().min(8, { error: "Password must be at least 8 characters" }),
});

type LoginFormValues = z.infer<typeof loginSchema>;

interface LoginFormProps {
  className?: string;
  /** Local path to return to after sign-in; re-validated by the auth provider. */
  redirectTo?: string | null;
  isRegister?: boolean;
  onModeChange?: (isRegister: boolean) => void;
}

export function LoginForm({
  className,
  redirectTo = null,
  isRegister = false,
  onModeChange,
}: LoginFormProps) {
  const { login } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(isRegister ? registerSchema : loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  async function onSubmit(data: LoginFormValues) {
    setIsLoading(true);
    setError(null);

    let accountCreated = false;
    try {
      if (isRegister) {
        await register(data);
        accountCreated = true;
      }
      // Registration does not issue cookies. Use the existing cookie login and
      // provider return-path validation; membership still requires accepting.
      await login(data, { redirectTo });
    } catch (err) {
      if (accountCreated) {
        onModeChange?.(false);
        setError("Your account was created, but sign-in failed. Sign in below to try again.");
      } else {
        setError(getApiErrorMessage(
          err,
          isRegister ? "Couldn't create your account. Please try again." : "Invalid email or password",
        ));
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className={cn("grid gap-6", className)}>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" aria-busy={isLoading}>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input
                    type="email"
                    placeholder="name@example.com"
                    autoCapitalize="none"
                    autoComplete="email"
                    autoCorrect="off"
                    disabled={isLoading}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    placeholder="Enter your password"
                    autoComplete={isRegister ? "new-password" : "current-password"}
                    disabled={isLoading}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          {error && (
            <div role="alert" className="text-destructive text-sm text-center">{error}</div>
          )}
          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isLoading
              ? (isRegister ? "Creating account…" : "Signing in…")
              : (isRegister ? "Create Account" : "Sign In")}
          </Button>
        </form>
      </Form>
      {onModeChange && (
        <Button type="button" variant="link" disabled={isLoading} onClick={() => {
          setError(null);
          form.clearErrors();
          onModeChange(!isRegister);
        }}>
          {isRegister ? "Already have an account? Sign in" : "New here? Create an account"}
        </Button>
      )}
    </div>
  );
}
