import { readFileSync, lstatSync, realpathSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import { resolveCuratedRequest } from "./resolve.mjs";

async function main() {
  if (process.argv.length !== 3 || !isAbsolute(process.argv[2])) throw new Error("usage: node resolve_collection.mjs <absolute-request.json>");
  const path = resolve(process.argv[2]);
  const file = lstatSync(path);
  if (!file.isFile() || file.isSymbolicLink() || file.size > 1024 * 1024 || realpathSync.native(path).toLowerCase() !== path.toLowerCase()) {
    throw new Error("curated FOMOD request must be a bounded physical file");
  }
  const result = await resolveCuratedRequest(JSON.parse(readFileSync(path, "utf8")));
  process.stdout.write(`${JSON.stringify(result)}\n`, () => process.exit(0));
}

main().catch((error) => {
  process.stderr.write(`${JSON.stringify({ error: error instanceof Error ? error.message : String(error) })}\n`, () => process.exit(1));
});
