import { NextResponse } from "next/server";

import { ownerLogin } from "./auth";

/** For API routes: the owner's session, and for writes a same-origin request (no cross-site form posts). */
export async function guard(req: Request, write = false): Promise<NextResponse | null> {
  if (!(await ownerLogin())) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (write) {
    const origin = req.headers.get("origin");
    const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
    if (!origin || !host || new URL(origin).host !== host) return NextResponse.json({ error: "bad origin" }, { status: 403 });
  }
  return null;
}
