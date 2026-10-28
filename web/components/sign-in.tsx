"use client";

import { signIn, signOut } from "next-auth/react";

import { buttonClass } from "./ui";

export function SignIn() {
  return (
    <button className={buttonClass("primary", "w-full")} onClick={() => signIn("github", { callbackUrl: "/" })}>
      Sign in with GitHub
    </button>
  );
}

export function SignOut() {
  return (
    <button className="t-small text-fg-3 hover:text-fg" onClick={() => signOut({ callbackUrl: "/login" })}>
      sign out
    </button>
  );
}
