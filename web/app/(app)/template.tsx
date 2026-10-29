"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

import { EASE_OUT } from "@/components/motion";

/** Runs on every navigation inside the app (a template re-mounts where a layout would persist): the page rises in, short enough not to add to the wait. */
export default function PageTransition({ children }: { children: ReactNode }) {
  return (
    <motion.div className="flex flex-1 flex-col gap-6" initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: EASE_OUT }}>
      {children}
    </motion.div>
  );
}
