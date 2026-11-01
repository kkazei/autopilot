"use client";

import { SkipForward, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useLive } from "./live";
import { cx } from "./ui";

const BASE = "inline-flex h-7 shrink-0 items-center justify-center gap-1.5 rounded-md text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50";

/** Drops a planned or carried-forward post for good (run_outer --skip): no model calls. Asks once, inline, because a
 *  skipped post is blocked and cannot be put back. On a phone the buttons go icon-first to leave room for the topic.
 *  Clicks stop here, so inside a <summary> the button does not also open or close the row. */
export function SkipButton({ postId, className }: { postId: string; className?: string }) {
  const { act } = useLive();
  const router = useRouter();
  const [stage, setStage] = useState<"idle" | "confirm" | "busy">("idle");
  const [msg, setMsg] = useState<string | null>(null);

  const skip = async () => {
    setStage("busy");
    const r = await act({ action: "skip", post_id: postId });
    const refused = !r.ok || r.message.startsWith("refused");
    setMsg(refused ? r.message : null);
    setStage("idle");
    if (!refused) router.refresh();
  };

  return (
    <span className={cx("flex items-center gap-1.5", className)} onClick={(e) => e.preventDefault()} onKeyDown={(e) => { if (e.key === "Escape" && stage === "confirm") setStage("idle"); }}>
      {msg && <span className="t-small max-w-24 truncate text-err sm:max-w-56" title={msg}>{msg}</span>}
      {stage === "idle" ? (
        <button type="button" onClick={() => { setMsg(null); setStage("confirm"); }} aria-label="Skip this post" title="Skip this post for good"
          className={cx(BASE, "size-8 border border-line-strong bg-raised text-fg-2 hover:border-fg-3 hover:text-fg sm:h-7 sm:w-auto sm:px-2.5")}>
          <SkipForward className="size-3.5" />
          <span className="hidden sm:inline">Skip</span>
        </button>
      ) : (
        <span className="animate-rise flex items-center gap-1.5" role="group" aria-label="Skip this post for good?">
          <button type="button" onClick={skip} disabled={stage === "busy"} autoFocus
            className={cx(BASE, "bg-err-bg px-2.5 text-err hover:brightness-110")}>
            {stage === "busy" ? "Skipping…" : <><span className="sm:hidden">Skip</span><span className="hidden sm:inline">Skip for good</span></>}
          </button>
          <button type="button" onClick={() => setStage("idle")} disabled={stage === "busy"} aria-label="Cancel"
            className={cx(BASE, "size-7 text-fg-3 hover:bg-raised hover:text-fg sm:w-auto sm:px-2")}>
            <X className="size-3.5 sm:hidden" />
            <span className="hidden sm:inline">Cancel</span>
          </button>
        </span>
      )}
    </span>
  );
}
