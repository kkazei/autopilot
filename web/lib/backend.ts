// The Python backend on Render. Only server code calls it, so the secret never reaches the browser.
export class BackendDown extends Error {}

export async function backend(path: string, init: RequestInit = {}, timeoutMs = 15_000): Promise<Response> {
  const base = process.env.AUTOPILOT_BACKEND_URL?.replace(/\/+$/, "");
  const secret = process.env.AUTOPILOT_BACKEND_SECRET;
  if (!base || !secret) throw new BackendDown("AUTOPILOT_BACKEND_URL or AUTOPILOT_BACKEND_SECRET is not set");
  try {
    return await fetch(`${base}${path}`, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
      headers: { "content-type": "application/json", "X-Autopilot-Secret": secret, ...init.headers },
    });
  } catch (e) {
    throw new BackendDown(e instanceof Error ? e.name : "unreachable");
  }
}
