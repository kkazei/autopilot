import { getServerSession, type NextAuthOptions } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import GitHub from "next-auth/providers/github";
import { redirect } from "next/navigation";

import { clearFailures, failures, recordFailure } from "./auth-store";
import { lockState, RULES } from "./lockout";
import { verifyPassword } from "./password";

// One owner. GitHub sign-in is checked against the allowlisted login; password sign-in against AUTH_PASSWORD_HASH,
// with the same login as the username. Both are checked again on every request, so a session minted before the
// allowlist changed stops working at once.
const allowed = () => (process.env.AUTH_ALLOWED_LOGIN ?? "").trim().toLowerCase();

export const passwordEnabled = () => Boolean(process.env.AUTH_PASSWORD_HASH && allowed());
export const githubEnabled = () => Boolean(process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET);

/** Thrown to the sign-in form as `error=Locked` or `error=Unavailable`; never a raw internal message. */
export const LOCKED = "Locked";
export const UNAVAILABLE = "Unavailable";

async function authorizePassword(username: string, password: string, ip: string) {
  const user = username.trim().toLowerCase();
  const keys = { user: `user:${user || "-"}`, ip: `ip:${ip}` };
  const now = new Date();
  const [u, i] = await Promise.all([failures(keys.user), failures(keys.ip)]);
  if (lockState(u, now, RULES.user).locked || lockState(i, now, RULES.ip).locked) throw new Error(LOCKED);
  // verifyPassword always does the full scrypt, so a wrong username takes as long as a wrong password.
  const passwordOk = await verifyPassword(password, process.env.AUTH_PASSWORD_HASH);
  if (passwordEnabled() && passwordOk && user === allowed()) {
    await Promise.all([clearFailures(keys.user), clearFailures(keys.ip)]);
    return { id: allowed(), name: allowed() };
  }
  await Promise.all([recordFailure(keys.user, RULES.user, now), recordFailure(keys.ip, RULES.ip, now)]);
  return null;
}

export const authOptions: NextAuthOptions = {
  providers: [
    GitHub({ clientId: process.env.AUTH_GITHUB_ID ?? "", clientSecret: process.env.AUTH_GITHUB_SECRET ?? "" }),
    Credentials({
      id: "password",
      name: "Password",
      credentials: { username: { label: "Username", type: "text" }, password: { label: "Password", type: "password" } },
      async authorize(credentials, req) {
        if (!passwordEnabled() || !credentials?.username || !credentials.password) return null;
        const forwarded = req?.headers?.["x-forwarded-for"];
        const ip = (Array.isArray(forwarded) ? forwarded[0] : forwarded)?.split(",")[0]?.trim() || "unknown";
        try {
          return await authorizePassword(credentials.username, credentials.password, ip);
        } catch (e) {
          if (e instanceof Error && e.message === LOCKED) throw e;
          console.error("password sign-in failed:", e instanceof Error ? e.name : "error"); // never the message: it can carry SQL
          throw new Error(UNAVAILABLE);
        }
      },
    }),
  ],
  session: { strategy: "jwt", maxAge: 7 * 24 * 60 * 60 },
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    async signIn({ account, profile, user }) {
      if (account?.provider === "password") return Boolean(user) && passwordEnabled();
      const login = (profile as { login?: string } | undefined)?.login?.toLowerCase();
      return Boolean(allowed()) && login === allowed();
    },
    async jwt({ token, account, profile }) {
      if (account?.provider === "password") token.login = allowed();
      else if (profile) token.login = (profile as { login?: string }).login;
      return token;
    },
    async session({ session, token }) {
      session.login = token.login;
      return session;
    },
  },
};

export async function ownerLogin(): Promise<string | null> {
  const session = await getServerSession(authOptions);
  const login = session?.login?.toLowerCase();
  return login && allowed() && login === allowed() ? login : null;
}

/** For pages: anyone but the owner goes to /login. */
export async function requireOwner(): Promise<string> {
  const login = await ownerLogin();
  if (!login) redirect("/login");
  return login;
}
