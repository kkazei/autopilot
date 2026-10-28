import { getServerSession, type NextAuthOptions } from "next-auth";
import GitHub from "next-auth/providers/github";
import { redirect } from "next/navigation";

// One owner. The GitHub login is checked at sign-in and again on every request, so a session minted before the
// allowlist changed stops working at once.
const allowed = () => (process.env.AUTH_ALLOWED_LOGIN ?? "").trim().toLowerCase();

export const authOptions: NextAuthOptions = {
  providers: [GitHub({ clientId: process.env.AUTH_GITHUB_ID ?? "", clientSecret: process.env.AUTH_GITHUB_SECRET ?? "" })],
  session: { strategy: "jwt", maxAge: 7 * 24 * 60 * 60 },
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    async signIn({ profile }) {
      const login = (profile as { login?: string } | undefined)?.login?.toLowerCase();
      return Boolean(allowed()) && login === allowed();
    },
    async jwt({ token, profile }) {
      if (profile) token.login = (profile as { login?: string }).login;
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
