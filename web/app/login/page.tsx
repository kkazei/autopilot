import { redirect } from "next/navigation";

import { LoginForm } from "@/components/login-form";
import { githubEnabled, ownerLogin, passwordEnabled } from "@/lib/auth";

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  if (await ownerLogin()) redirect("/control");
  const { error } = await searchParams;
  return <LoginForm password={passwordEnabled()} github={githubEnabled()} initialError={error} />;
}
