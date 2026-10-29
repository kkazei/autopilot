"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { StatusIsland, type IslandTask } from "./kokonutui/status-island";
import { useLive } from "./live";
import { describeEvents, stepLabel } from "@/lib/parse";

/** A pill on every page while a run is going: what it is doing now, a way to its trace, and the approval when one
 * is waiting. It reports the result for a few seconds after the run ends, then leaves. */
export function RunIsland() {
  const { live } = useLive();
  const router = useRouter();
  const path = usePathname();
  const [finished, setFinished] = useState<IslandTask | null>(null);
  const wasRunning = useRef(false);
  const status = live?.status;
  const run = live?.run;
  const running = Boolean(status?.running);

  useEffect(() => {
    if (wasRunning.current && !running && status) {
      const code = status.exit_code;
      const story = run ? describeEvents(run.events) : null;
      setFinished({
        id: `done-${run?.run_id}`, label: story?.title ?? (code === 0 ? "Run finished" : "Run ended"),
        detail: code === null ? "crashed: see the trace" : story?.detail ?? `exit ${code}`, status: story?.tone === "error" || (code !== 0 && code !== null && !story) ? "error" : "done",
        action: run ? { label: "Trace", onClick: () => router.push(`/runs/${run.run_id}`) } : undefined,
      });
    }
    wasRunning.current = running;
  }, [running, status, run, router]);

  const tasks: IslandTask[] = [];
  if (finished && !running) tasks.push(finished);
  if (running && status) {
    const last = run?.events.at(-1);
    if (status.approval) {
      tasks.push({ id: `approval-${status.approval.id}`, label: "Draft needs you", detail: status.approval.dry_run ? "dry run" : "live post", status: "running",
        action: path === "/control" ? undefined : { label: "Review", onClick: () => router.push("/control") } });
    } else {
      tasks.push({ id: `run-${run?.run_id ?? "starting"}`, label: status.what, detail: last ? stepLabel(last) : "starting…", status: "running",
        action: run ? { label: "Trace", onClick: () => router.push(`/runs/${run.run_id}`) } : undefined });
    }
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-30 flex justify-center px-4 md:bottom-6">
      <div className="pointer-events-auto">
        <StatusIsland tasks={tasks} onDismiss={() => setFinished(null)} dismissAfter={5000} />
      </div>
    </div>
  );
}
