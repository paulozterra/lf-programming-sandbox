// T2: deterministic source-ordered OpenAPI → generated TS; no business cases.
import { readdir, readFile, mkdir, writeFile, unlink } from "node:fs/promises";
import { resolve, basename, join } from "node:path";
import { spawnSync } from "node:child_process";

const base = resolve(import.meta.dirname, "../..");
const source = join(base, "contracts");
const output = join(base, "frontend/src/lib/api/generated");
const check = process.argv.includes("--check");
const files = (await readdir(source)).filter((name) => name.endsWith(".openapi.yaml")).sort();
await mkdir(output, { recursive: true });
const generated = new Set();
let failures = [];

for (const file of files) {
  const moduleName = file.slice(0, -".openapi.yaml".length);
  if (!/^[a-z0-9][a-z0-9-]*$/.test(moduleName)) throw Error("T2_CONTRACT_FILENAME_INVALID");
  const dest = join(output, moduleName + ".d.ts");
  const command = join(base, "frontend/node_modules/.bin/openapi-typescript");
  const result = spawnSync(command, [join(source, file)], { cwd: base, encoding: "utf8" });
  if (result.status !== 0) throw Error("T2_GENERATOR_FAILED: " + (result.stderr || result.stdout));
  // openapi-typescript emits its declaration to stdout in a stable format.
  const content = result.stdout;
  if (!content.includes("export interface paths")) throw Error("T2_GENERATED_TYPES_INVALID");
  generated.add(basename(dest));
  if (check) {
    let previous;
    try { previous = await readFile(dest, "utf8"); } catch { previous = null; }
    if (previous !== content) failures.push(dest);
  } else {
    await writeFile(dest, content);
  }
}
for (const name of await readdir(output)) {
  if (name.endsWith(".d.ts") && !generated.has(name)) {
    if (check) failures.push(join(output, name));
    else await unlink(join(output, name));
  }
}
if (failures.length) {
  process.stderr.write("T2_GENERATED_CLIENT_STALE: " + failures.sort().join(", ") + "\n");
  process.exitCode = 2;
} else {
  process.stdout.write("T2_API_CLIENT_" + (check ? "CHECK_PASS" : "GENERATED") + ": " + files.length + "\n");
}
