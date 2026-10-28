"use client";

import { signOut } from "next-auth/react";

export function SignOut() {
  return (
    <button className="t-small text-fg-3 hover:text-fg" onClick={() => signOut({ callbackUrl: "/login" })}>
      sign out
    </button>
  );
}
