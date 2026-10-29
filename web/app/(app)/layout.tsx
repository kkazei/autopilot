import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { LiveProvider } from "@/components/live";
import { MotionRoot } from "@/components/motion";
import { RunIsland } from "@/components/run-island";
import { MobileHeader, Sidebar, TabBar } from "@/components/nav";
import { TimeZoneProvider } from "@/components/time";
import { requireOwner } from "@/lib/auth";
import { NAV_COOKIE } from "@/lib/nav";
import { brandName } from "@/lib/db";
import { TZ_COOKIE, validTimeZone } from "@/lib/time";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const login = await requireOwner();
  const brand = await brandName().catch(() => "Autopilot");
  const jar = await cookies();
  const tz = validTimeZone(jar.get(TZ_COOKIE)?.value);
  return (
    <TimeZoneProvider initial={tz}>
    <MotionRoot>
    <LiveProvider>
    <div className="flex min-h-dvh">
      <Sidebar login={login} brand={brand} collapsed={jar.get(NAV_COOKIE)?.value === "1"} />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileHeader login={login} />
        <main className="flex flex-1 flex-col gap-6 px-4 pt-3 pb-32 md:p-8 md:pl-5">{children}</main>
      </div>
      <TabBar />
      <RunIsland />
    </div>
    </LiveProvider>
    </MotionRoot>
    </TimeZoneProvider>
  );
}
