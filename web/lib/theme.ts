export type ThemeChoice = "system" | "light" | "dark";
export const THEME_COOKIE = "theme";

/** Runs in <head> before first paint, so a chosen theme never flashes the system one. Pages stay static: no cookie read on the server. */
export const THEME_SCRIPT = `try{var m=document.cookie.match(/(?:^|; )${THEME_COOKIE}=(light|dark)/);if(m)document.documentElement.dataset.theme=m[1]}catch(e){}`;
