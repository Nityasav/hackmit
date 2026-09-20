// The api reads contracts/fixtures/ and the web app imports the same bundles at
// build time. Vercel builds with web/ as the root directory, so anything above
// it is not in the build context — the import has to resolve inside web/.
//
// contracts/fixtures/ stays canonical. This copies it in before a build, and the
// copies are committed so the Vercel build has them. When contracts/ is absent
// (which is the case on Vercel), the committed copies are already correct and
// this is a no-op rather than an error.
import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "contracts", "fixtures");
const target = join(here, "..", "src", "fixtures");

if (!existsSync(source)) {
  console.log("sync-fixtures: no contracts/fixtures here, using the committed copies");
  process.exit(0);
}

mkdirSync(target, { recursive: true });

let copied = 0;
for (const file of readdirSync(source)) {
  if (!file.endsWith(".json")) continue;
  copyFileSync(join(source, file), join(target, file));
  copied += 1;
}

console.log(`sync-fixtures: ${copied} fixture${copied === 1 ? "" : "s"} copied from contracts/`);
