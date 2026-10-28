"use client";

import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { AnimatePresence, motion, useAnimationControls } from "motion/react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

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

function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

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
      router.replace("/");
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
                  void signIn("github", { callbackUrl: "/" });
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
