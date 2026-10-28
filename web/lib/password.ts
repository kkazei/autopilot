import { randomBytes, scrypt as scryptCb, timingSafeEqual, type ScryptOptions } from "node:crypto";

// The owner's password is stored only as an scrypt hash in AUTH_PASSWORD_HASH (Node's built-in crypto, no new
// dependency). Format: scrypt.N.r.p.salt.key, base64url parts joined by dots, so no "$" for .env expansion to eat.

const N = 16384, R = 8, P = 1, KEYLEN = 32;
const MAXMEM = 64 * 1024 * 1024;

const scrypt = (pw: string, salt: Buffer, keylen: number, opts: ScryptOptions) =>
  new Promise<Buffer>((resolve, reject) => scryptCb(pw, salt, keylen, opts, (err, key) => (err ? reject(err) : resolve(key))));

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const key = await scrypt(password.normalize("NFKC"), salt, KEYLEN, { N, r: R, p: P, maxmem: MAXMEM });
  return ["scrypt", N, R, P, salt.toString("base64url"), key.toString("base64url")].join(".");
}

const DUMMY_SALT = Buffer.alloc(16, 7);

/** Always does one full scrypt, even for a malformed or missing hash, so the response time says nothing. */
export async function verifyPassword(password: string, stored: string | undefined): Promise<boolean> {
  const parts = (stored ?? "").split(".");
  const ok = parts.length === 6 && parts[0] === "scrypt";
  const [n, r, p] = ok ? parts.slice(1, 4).map(Number) : [N, R, P];
  const sane = ok && [n, r, p].every((x) => Number.isInteger(x) && x > 0) && n <= 1 << 20;
  const salt = sane ? Buffer.from(parts[4], "base64url") : DUMMY_SALT;
  const expected = sane ? Buffer.from(parts[5], "base64url") : Buffer.alloc(KEYLEN);
  const key = await scrypt(password.normalize("NFKC"), salt, expected.length || KEYLEN, sane ? { N: n, r, p, maxmem: MAXMEM } : { N, r: R, p: P, maxmem: MAXMEM });
  return sane && expected.length > 0 && timingSafeEqual(key, expected);
}
