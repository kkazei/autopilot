import { NextResponse } from "next/server";

import { backend, BackendDown } from "@/lib/backend";
import { guard } from "@/lib/guard";

// Render's free service sleeps; the first request after that takes up to about a minute while it wakes.
export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const denied = await guard(req);
  if (denied) return denied;
  try {
    const res = await backend("/health", {}, 55_000);
    return NextResponse.json({ up: res.ok });
  } catch (e) {
    return NextResponse.json({ up: false, reason: e instanceof BackendDown ? e.message : "error" });
  }
}
