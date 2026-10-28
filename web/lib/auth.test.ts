import assert from "node:assert/strict";
import { test } from "node:test";

import { afterFailure, lockState, RULES } from "./lockout.ts";
import { hashPassword, verifyPassword } from "./password.ts";

test("a hash verifies its own password and nothing else", async () => {
  const stored = await hashPassword("correct horse battery staple");
  assert.match(stored, /^scrypt\.16384\.8\.1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
  assert.ok(!stored.includes("$"), "no $ for .env expansion to eat");
  assert.equal(await verifyPassword("correct horse battery staple", stored), true);
  assert.equal(await verifyPassword("correct horse battery stapler", stored), false);
  assert.notEqual(await hashPassword("same"), await hashPassword("same"), "salted");
});

test("missing or malformed hashes never verify (and still do the work)", async () => {
  for (const bad of [undefined, "", "plaintext", "scrypt.1.2", "scrypt.x.8.1.AAAA.BBBB", "bcrypt.16384.8.1.AAAA.BBBB"]) {
    assert.equal(await verifyPassword("anything", bad), false, String(bad));
  }
});

test("five failures in 15 minutes lock the username; the window then expires", () => {
  const t0 = new Date("2026-10-28T14:00:00Z");
  let row = null as ReturnType<typeof afterFailure> | null;
  for (let i = 0; i < 4; i++) row = afterFailure(row, t0, RULES.user);
  assert.equal(lockState(row, t0, RULES.user).locked, false);
  row = afterFailure(row, t0, RULES.user);
  const locked = lockState(row, new Date("2026-10-28T14:10:00Z"), RULES.user);
  assert.equal(locked.locked, true);
  assert.equal(locked.retryAt?.toISOString(), "2026-10-28T14:15:00.000Z");
  assert.equal(lockState(row, new Date("2026-10-28T14:15:00Z"), RULES.user).locked, false);
  assert.deepEqual(afterFailure(row, new Date("2026-10-28T14:20:00Z"), RULES.user).failures, 1, "a fresh window after expiry");
});
