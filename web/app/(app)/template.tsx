"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

import { EASE_OUT } from "@/components/motion";

/** Runs on every navigation inside the app (a template re-mounts where a layout would persist): the page rises in. */
export default function PageTransition({ children }: { children: ReactNode }) {
  return (
    <motion.div className="flex flex-1 flex-col gap-6" initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 0.32, ease: EASE_OUT }}>
      {children}
    </motion.div>
  );
}
