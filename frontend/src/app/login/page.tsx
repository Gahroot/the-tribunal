import { RETURN_TO_PARAM, getSafeReturnTo } from "@/lib/auth/return-to";

import { LoginClient } from "./login-client";

interface LoginPageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  // Untrusted query input: only a permitted local path survives (RF-003).
  const redirectTo = getSafeReturnTo(params[RETURN_TO_PARAM]);
  return <LoginClient redirectTo={redirectTo} initialRegister={params.mode === "register"} />;
}
