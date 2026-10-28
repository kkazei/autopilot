"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cx, Icon, type IconName } from "./ui";

const ITEMS: [string, string, IconName][] = [["/", "Control", "dashboard"], ["/plan", "Plan", "calendar"], ["/runs", "Traces", "activity"], ["/learnings", "Learnings", "bulb"]];
const isActive = (path: string, href: string) => (href === "/" ? path === "/" : path.startsWith(href));

export function SideNav() {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-1">
      {ITEMS.map(([href, label, icon]) => {
        const on = isActive(path, href);
        return (
          <Link key={href} href={href} aria-current={on ? "page" : undefined}
            className={cx("flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium", on ? "bg-raised text-fg" : "text-fg-2 hover:text-fg")}>
            <Icon name={icon} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function TabBar() {
  const path = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-10 flex justify-between border-t border-line bg-surface px-6 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:hidden">
      {ITEMS.map(([href, label, icon]) => {
        const on = isActive(path, href);
        return (
          <Link key={href} href={href} aria-current={on ? "page" : undefined}
            className={cx("flex flex-col items-center gap-1 t-small", on ? "text-fg" : "text-fg-3")}>
            <Icon name={icon} size={20} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
