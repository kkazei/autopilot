// Makes AUTH_PASSWORD_HASH for the password sign-in. Run it in your own terminal (it asks twice, without echo):
//   cd web && node scripts/hash-password.mjs
// Paste the printed value into Vercel (and web/.env.local for local dev). The password itself is stored nowhere.
import { randomBytes, scrypt } from "node:crypto";

function ask(prompt) {
  return new Promise((resolve) => {
    const { stdin, stdout } = process;
    if (!stdin.isTTY) {
      console.error("Run this in an interactive terminal; it reads the password without echo.");
      process.exit(2);
    }
    stdout.write(prompt);
    stdin.setRawMode(true);
    stdin.resume();
    stdin.setEncoding("utf8");
    let value = "";
    const onData = (ch) => {
      if (ch === "\r" || ch === "\n") {
        stdin.setRawMode(false);
        stdin.pause();
        stdin.off("data", onData);
        stdout.write("\n");
        resolve(value);
      } else if (ch === "\u0003") {
        process.exit(130);
      } else if (ch === "\u007f" || ch === "\b") {
        value = value.slice(0, -1);
      } else {
        value += ch;
      }
    };
    stdin.on("data", onData);
  });
}

const first = await ask("New password: ");
if (first.length < 12) {
  console.error("Use at least 12 characters.");
  process.exit(2);
}
if ((await ask("Again: ")) !== first) {
  console.error("The two entries differ.");
  process.exit(2);
}
const salt = randomBytes(16);
scrypt(first.normalize("NFKC"), salt, 32, { N: 16384, r: 8, p: 1, maxmem: 64 * 1024 * 1024 }, (err, key) => {
  if (err) throw err;
  console.log(`\nAUTH_PASSWORD_HASH=${["scrypt", 16384, 8, 1, salt.toString("base64url"), key.toString("base64url")].join(".")}`);
});
