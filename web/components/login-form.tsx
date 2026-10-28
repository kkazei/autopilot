"use client";

import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { AnimatePresence, motion, useAnimationControls } from "motion/react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { GitHubMark } from "./github-mark";
import DotField from "./kokonutui/dot-field";
import { LogoMark } from "./logo";
import { EASE_OUT } from "./motion";
import { buttonClass, cx } from "./ui";

const MESSAGES: Record<string, string> = {
  CredentialsSignin: "Wrong username or password.",
  Locked: "Too many attempts. Try again in 15 minutes, or continue with GitHub.",
  AccessDenied: "This GitHub account isn't allowed here.",
  Unavailable: "Sign-in is unavailable right now. Try again in a minute, or continue with GitHub.",
};
const message = (code: string | null | undefined) => (code ? MESSAGES[code] ?? "Sign-in failed. Try again." : null);

export function LoginForm({ password, github, initialError }: { password: boolean; github: boolean; initialError?: string }) {
  const router = useRouter();
  const shake = useAnimationControls();
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState<"password" | "github" | null>(null);
  const [error, setError] = useState<string | null>(message(initialError));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy("password");
    setError(null);
    const res = await signIn("password", { username, password: secret, redirect: false });
    if (res?.ok && !res.error) {
      router.replace("/control");
      router.refresh();
      return;
    }
    setBusy(null);
    setSecret("");
    setError(message(res?.error ?? "CredentialsSignin"));
    void shake.start({ x: [0, -8, 7, -5, 3, 0], transition: { duration: 0.4 } });
  };

  const field = "w-full rounded-md border border-line bg-inset px-3 py-2.5 text-sm text-fg placeholder:text-fg-3 transition-colors focus:border-line-strong focus:outline-hidden";
  const item = { hidden: { opacity: 0, y: 8 }, shown: { opacity: 1, y: 0, transition: { duration: 0.35, ease: EASE_OUT } } };

  return (
    <DotField className="min-h-dvh px-4 py-10" spacing={18}>
      <motion.main initial="hidden" animate="shown" variants={{ shown: { transition: { staggerChildren: 0.06, delayChildren: 0.15 } } }}
        className="relative z-10 w-full max-w-sm">
        <motion.div animate={shake}
          className="flex flex-col gap-6 rounded-xl border border-line bg-surface/85 p-6 text-fg shadow-[0_24px_80px_-24px_rgb(0_0_0/0.5)] backdrop-blur-md sm:p-7">
          <motion.div variants={item} className="flex flex-col items-center gap-3 text-center">
            <LogoMark size={52} draw />
            <div className="flex flex-col gap-1">
              <h1 className="t-title-lg">autopilot</h1>
              <p className="t-small text-fg-2">Marketing agents on autopilot. You approve every post.</p>
            </div>
          </motion.div>

          <AnimatePresence mode="popLayout">
            {error && (
              <motion.p key={error} role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="t-small rounded-md border border-err/30 bg-err-bg px-3 py-2 text-err">
                {error}
              </motion.p>
            )}
          </AnimatePresence>

          {password && (
            <motion.form variants={item} onSubmit={submit} className="flex flex-col gap-3" noValidate>
              <label className="flex flex-col gap-1.5">
                <span className="t-label text-fg-3">username</span>
                <input className={field} value={username} onChange={(e) => setUsername(e.target.value)} name="username"
                  autoComplete="username" autoCapitalize="none" spellCheck={false} required autoFocus />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="t-label text-fg-3">password</span>
                <span className="relative">
                  <input className={cx(field, "pr-10")} value={secret} onChange={(e) => setSecret(e.target.value)} name="password"
                    type={show ? "text" : "password"} autoComplete="current-password" required />
                  <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}
                    className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-fg-3 hover:text-fg">
                    {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </span>
              </label>
              <button type="submit" className={buttonClass("primary", "mt-1 h-10 w-full")} disabled={busy !== null || !username || !secret}>
                {busy === "password" ? <><LoaderCircle className="size-4 animate-spin" /> Signing in…</> : "Sign in"}
              </button>
            </motion.form>
          )}

          {password && github && (
            <motion.div variants={item} className="t-label flex items-center gap-3 text-fg-3" aria-hidden>
              <span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" />
            </motion.div>
          )}

          {github && (
            <motion.div variants={item}>
              <button type="button" className={buttonClass(password ? "secondary" : "primary", "h-10 w-full")} disabled={busy !== null}
                onClick={() => {
                  setBusy("github");
                  void signIn("github", { callbackUrl: "/control" });
                }}>
                {busy === "github" ? <LoaderCircle className="size-4 animate-spin" /> : <GitHubMark />} Continue with GitHub
              </button>
            </motion.div>
          )}

          {!password && !github && <p className="t-small text-center text-fg-3">Sign-in is not configured yet.</p>}
        </motion.div>
        <motion.p variants={item} className="t-mono-sm mt-4 text-center text-fg-3">private · owner only</motion.p>
      </motion.main>
    </DotField>
  );
}
