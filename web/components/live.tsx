"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import type { Live } from "@/app/api/live/route";

type ActResult = { ok: boolean; message: string };
type LiveState = {
  live: Live | null;
  dbOk: boolean;
  waking: boolean;
  refresh: () => void;
  act: (body: Record<string, unknown>) => Promise<ActResult>;
};

const Ctx = createContext<LiveState | null>(null);
export const useLive = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLive outside LiveProvider");
  return v;
};

// Fast while something is happening, slow otherwise, paused in a hidden tab: every poll wakes Neon and Render.
const FAST_MS = 3_000;
const SLOW_MS = 20_000;
const WAKE_RETRY_MS = 60_000;

export function LiveProvider({ children }: { children: ReactNode }) {
  const [live, setLive] = useState<Live | null>(null);
  const [dbOk, setDbOk] = useState(true);
  const [waking, setWaking] = useState(false);
  const lastWake = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const wake = useCallback(async () => {
    if (Date.now() - lastWake.current < WAKE_RETRY_MS) return;
    lastWake.current = Date.now();
    setWaking(true);
    try {
      await fetch("/api/health", { cache: "no-store" });
    } finally {
      setWaking(false);
    }
  }, []);

  const poll = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    let next = SLOW_MS;
    try {
      const res = await fetch("/api/live", { cache: "no-store" });
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      setDbOk(res.ok);
      if (res.ok) {
        const data = (await res.json()) as Live;
        setLive(data);
        const busy = data.status?.running || data.status?.approval || (data.run && !data.run.finished);
        next = busy ? FAST_MS : SLOW_MS;
        if (data.backend === "down") {
          next = FAST_MS * 2;
          void wake().then(() => poll());
        }
      }
    } catch {
      setDbOk(false);
    }
    if (!document.hidden) timer.current = setTimeout(poll, next);
  }, [wake]);

  useEffect(() => {
    void poll();
    const onVisible = () => {
      if (!document.hidden) void poll();
      else if (timer.current) clearTimeout(timer.current);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      if (timer.current) clearTimeout(timer.current);
    };
  }, [poll]);

  const act = useCallback(async (body: Record<string, unknown>): Promise<ActResult> => {
    try {
      const res = await fetch("/api/actions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      const data = (await res.json().catch(() => ({}))) as Partial<ActResult>;
      return { ok: res.ok, message: data.message ?? (res.ok ? "done" : `failed (${res.status})`) };
    } catch {
      return { ok: false, message: "Network error. Try again." };
    } finally {
      void poll();
    }
  }, [poll]);

  return <Ctx.Provider value={{ live, dbOk, waking, refresh: poll, act }}>{children}</Ctx.Provider>;
}
