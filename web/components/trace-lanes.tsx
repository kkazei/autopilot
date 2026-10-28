"use client";

import { useRouter } from "next/navigation";

import RunLanes from "./kokonutui/run-lanes";
import type { TraceEvent } from "@/lib/parse";

/** The run timeline on a trace page; clicking a bar opens that event in the detail panel. */
export function TraceLanes({ runId, events, selected, live }: { runId: string; events: TraceEvent[]; selected?: number; live?: boolean }) {
  const router = useRouter();
  return <RunLanes events={events} live={live} selected={selected} onSelect={(i) => router.push(`/runs/${runId}?e=${i}`, { scroll: false })} />;
}
