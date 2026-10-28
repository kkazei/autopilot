import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** KokonutUI's class helper: later classes win over earlier ones. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
