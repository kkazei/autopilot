import { redirect } from "next/navigation";

import { SignIn } from "@/components/sign-in";
import { ownerLogin } from "@/lib/auth";

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  if (await ownerLogin()) redirect("/");
  const { error } = await searchParams;
  return (
    <main className="grid min-h-dvh place-items-center p-4">
      <div className="flex w-full max-w-sm flex-col gap-6 rounded-lg border border-line bg-surface p-6">
        <div className="flex flex-col gap-1">
          <span className="t-title">autopilot</span>
          <span className="t-small text-fg-3">Private control panel</span>
        </div>
        {error && (
          <p className="t-small rounded-md bg-err-bg px-3 py-2 text-err">
            {error === "AccessDenied" ? "This GitHub account is not allowed." : "Sign-in failed. Try again."}
          </p>
        )}
        <SignIn />
      </div>
    </main>
  );
}
