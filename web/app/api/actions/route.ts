import { NextResponse } from "next/server";

import { backend, BackendDown } from "@/lib/backend";
import { guard } from "@/lib/guard";

export const maxDuration = 30;
export const dynamic = "force-dynamic";

type Action =
  | { action: "run"; kind: "next" | "topic" | "plan" | "measure"; dry_run?: boolean; topic?: string; angle?: string; goal?: string }
  | { action: "answer"; approval_id: number; choice: "approve" | "not_now" | "reject" }
  | { action: "requeue"; post_id: string };

const POST_ID = /^post_[a-f0-9]{8}$/;

/** The only writes the web app can make, each mapped to one backend route. Approval cannot be switched off here. */
export async function POST(req: Request) {
  const denied = await guard(req, true);
  if (denied) return denied;
  let a: Action;
  try {
    a = (await req.json()) as Action;
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  let path: string;
  let body: unknown = {};
  if (a.action === "run" && ["next", "topic", "plan", "measure"].includes(a.kind)) {
    path = "/runs";
    body = { kind: a.kind, dry_run: Boolean(a.dry_run), topic: a.topic, angle: a.angle, goal: a.goal ?? "engagement" };
  } else if (a.action === "answer" && Number.isInteger(a.approval_id) && ["approve", "not_now", "reject"].includes(a.choice)) {
    path = `/approvals/${a.approval_id}`;
    body = { choice: a.choice };
  } else if (a.action === "requeue" && POST_ID.test(a.post_id)) {
    path = `/posts/${a.post_id}/requeue`;
  } else {
    return NextResponse.json({ error: "unknown action" }, { status: 400 });
  }
  try {
    const res = await backend(path, { method: "POST", body: JSON.stringify(body) }, 25_000);
    const data = (await res.json().catch(() => ({}))) as { message?: string; detail?: unknown };
    const message = data.message ?? (typeof data.detail === "string" ? data.detail : res.ok ? "done" : `backend said ${res.status}`);
    return NextResponse.json({ ok: res.ok, message }, { status: res.ok ? 200 : res.status });
  } catch (e) {
    return NextResponse.json({ ok: false, message: e instanceof BackendDown ? "The backend is asleep or unreachable. Try again in a minute." : "error" }, { status: 503 });
  }
}
