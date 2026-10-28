import type { Metadata } from "next";

import { Landing } from "@/components/landing";
import { MotionRoot } from "@/components/motion";

// Public: no session, no database reads. The example run is a built-in snapshot (lib/sample-run.ts).
export const metadata: Metadata = {
  title: "Autopilot · A week of posts, on autopilot",
  description: "AI agents that plan, write and critique a week of social posts, publish only after you approve, and learn from engagement.",
  robots: { index: true, follow: true },
};

export default function Home() {
  return (
    <MotionRoot>
      <Landing />
    </MotionRoot>
  );
}
