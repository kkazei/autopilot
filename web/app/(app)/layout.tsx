import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { LiveProvider } from "@/components/live";
import { MotionRoot } from "@/components/motion";
import { RunIsland } from "@/components/run-island";
import { SideNav, TabBar } from "@/components/nav";
import { SignOut } from "@/components/sign-in";
import { SystemLights } from "@/components/system-lights";
import { TimeZoneProvider } from "@/components/time";
import { requireOwner } from "@/lib/auth";
import { brandName } from "@/lib/db";
import { TZ_COOKIE, validTimeZone } from "@/lib/time";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const login = await requireOwner();
  const brand = await brandName().catch(() => "Autopilot");
  const tz = validTimeZone((await cookies()).get(TZ_COOKIE)?.value);
  return (
    <TimeZoneProvider initial={tz}>
    <MotionRoot>
    <LiveProvider>
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line bg-surface px-4 py-5 md:flex">
        <div className="flex flex-col gap-1 px-3 pb-5">
          <span className="t-title">autopilot</span>
          <span className="t-small text-fg-3">{brand}</span>
        </div>
        <SideNav />
        <div className="mt-auto flex flex-col gap-2 px-3">
          <span className="t-label text-fg-3">system</span>
          <SystemLights />
          <div className="flex items-center pt-3">
            <span className="t-small text-fg-2">{login}</span>
            <span className="ml-auto"><SignOut /></span>
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-line bg-surface px-4 py-3 md:hidden">
          <span className="t-title">autopilot</span>
          <span className="ml-auto"><SystemLights compact /></span>
        </header>
        <main className="flex flex-1 flex-col gap-6 px-4 py-5 pb-28 md:p-8">{children}</main>
      </div>
      <TabBar />
      <RunIsland />
    </div>
    </LiveProvider>
    </MotionRoot>
    </TimeZoneProvider>
  );
}
