// T2: reject hand-authored network requests to backend endpoints.
import { readdir, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "../src");
const bad = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const file = join(dir, entry.name);
    if (entry.isDirectory()) { if (entry.name !== "generated") await walk(file); continue; }
    if (!/\.(tsx?|jsx?)$/.test(entry.name)) continue;
    const text = await readFile(file, "utf8");
    // openapi-fetch performs its own fetch internally; app source must not.
    if (/\b(?:globalThis\.|window\.)?fetch\s*\\(/.test(text)) bad.push(file);
  }
}
await walk(root);
if (bad.length) {
  process.stderr.write("T2_MANUAL_FETCH_FORBIDDEN: " + bad.sort().join(", ") + "\n");
  process.exitCode = 2;
} else {
  process.stdout.write("T2_NO_MANUAL_FETCH_PASS\n");
}
