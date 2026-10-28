"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useLive } from "./live";
import { buttonClass } from "./ui";

/** Puts an escalated post back in the queue (run_outer --requeue): no model calls. */
export function RequeueButton({ postId }: { postId: string }) {
  const { act } = useLive();
  const router = useRouter();
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex items-center gap-3">
      <button className={buttonClass("secondary", "w-fit")} disabled={busy} onClick={async () => {
        setBusy(true);
        const r = await act({ action: "requeue", post_id: postId });
        setMsg(r.message);
        setBusy(false);
        if (r.ok) router.refresh();
      }}>{busy ? "Requeueing…" : "Put back in the queue"}</button>
      {msg && <span className="t-small whitespace-pre-line text-fg-2">{msg}</span>}
    </div>
  );
}
