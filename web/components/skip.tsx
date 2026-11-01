"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useLive } from "./live";
import { cx } from "./ui";

const LINK = "t-mono-sm rounded px-1.5 py-0.5 transition-colors disabled:opacity-50";

/** Drops a planned or carried-forward post for good (run_outer --skip): no model calls. Asks once, inline,
 *  because a skipped post is blocked and cannot be put back. */
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
    <span className={cx("flex shrink-0 items-center gap-1", className)}>
      {msg && <span className="t-small max-w-24 truncate text-fg-3 sm:max-w-56" title={msg}>{msg}</span>}
      {stage === "idle" && (
        <button type="button" onClick={() => { setMsg(null); setStage("confirm"); }} aria-label={`Skip ${postId}`}
          className={cx(LINK, "text-fg-3 hover:bg-fg/[0.06] hover:text-fg")}>skip</button>
      )}
      {stage !== "idle" && (
        <>
          <span className="t-small hidden whitespace-nowrap text-fg-2 sm:inline">Skip for good?</span>
          <button type="button" onClick={skip} disabled={stage === "busy"} className={cx(LINK, "text-err hover:bg-err-bg")}>
            {stage === "busy" ? "skipping…" : <><span className="sm:hidden">skip it</span><span className="hidden sm:inline">yes</span></>}
          </button>
          <button type="button" onClick={() => setStage("idle")} disabled={stage === "busy"} className={cx(LINK, "text-fg-3 hover:bg-fg/[0.06] hover:text-fg")}>no</button>
        </>
      )}
    </span>
  );
}
