"use client";

import { useLive } from "./live";
import { CountUp } from "./motion";
import { Meter, Stat } from "./ui";
import { DAILY_REQUEST_LIMIT, liveRequestCount } from "@/lib/parse";

/** The requests tile, ticking up with each model call of the live run instead of waiting for the next page reload. */
export function LiveQuota({ base, baseAt }: { base: number; baseAt: string }) {
  const { live } = useLive();
  const used = liveRequestCount(base, baseAt, live?.run?.events ?? []);
  const left = DAILY_REQUEST_LIMIT - used;
  return (
    <Stat label="model requests · 24h" value={<><CountUp value={used} />/{DAILY_REQUEST_LIMIT}</>}
      sub={left > 0 ? `${left} left · a run uses up to 16` : "daily cap reached"}>
      <Meter used={used} max={DAILY_REQUEST_LIMIT} />
    </Stat>
  );
}
