import { createHash } from "node:crypto";
import { createReadStream, lstatSync, readFileSync, readdirSync, realpathSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { NativeModInstaller } from "@nexusmods/fomod-installer-native";

const require = createRequire(import.meta.url);
const dependencyPackage = require("@nexusmods/fomod-installer-native/package.json");
const trustedInventory = JSON.parse(readFileSync(new URL("./fixtures/spicy-clean-906-9719.inventory.json", import.meta.url), "utf8"));
const proofKind = "developer-fomod-resolver-proof";
const dependencyVersion = "0.13.4";
const dependencyIntegrity = "sha512-XneP+V2eHHXlp1P0HZm7aT3IZmv0u4Igav/iAgLPfZbpO6T0wOaia4joAK531TpqHtz7z2EfQXpiBpBKOwuEeg==";
const sha256Pattern = /^[0-9a-f]{64}$/;
const maxRequestBytes = 128 * 1024;
const maxArchiveBytes = 8 * 1024 * 1024;
const maxExtractedBytes = 8 * 1024 * 1024;
const maxInventoryFiles = 32;
const maxCopies = 4;
const maxCuratedPresetSteps = 32;
const maxCuratedPresetChars = 64 * 1024;
const maxCuratedArchiveBytes = 4 * 1024 * 1024 * 1024;
const maxRelativePathLength = 256;
const representativeArchiveSha256 = "762046b25107cc5e86b04dc286ca8ccc6bffbf7ad3ea163a72b8d7a2f34b4ddb";
const introductionChoice = {
  name: "Introduction",
  groups: [{
    name: "Intro",
    choices: [{ name: " Spicy Clean Hacking Screen", idx: 0 }]
  }]
};
const curatedSelections = [
  {
    preset: [
      introductionChoice,
      { name: "Options", groups: [{ name: "Options", choices: [{ name: "Clean", idx: 0 }] }] }
    ],
    copy: {
      source: "CleanScanner/archive/pc/mod/basegame_clean.archive",
      destination: "archive/pc/mod/basegame_clean.archive",
      size: 8192,
      sha256: "8bc20e279e1ba24a81ac48f7f575b788250bc4a87ed6b31f528c33372baa6ff7"
    }
  },
  {
    preset: [
      introductionChoice,
      { name: "Options", groups: [{ name: "Options", choices: [{ name: "Clean and Green", idx: 1 }] }] }
    ],
    copy: {
      source: "CleanGreenScanner/archive/pc/mod/basegame_cleangreen.archive",
      destination: "archive/pc/mod/basegame_cleangreen.archive",
      size: 8192,
      sha256: "233b7bbf8cdf3c77eef0303c69ac9ec32ef6787c7447defa3022e66151210224"
    }
  }
];
const requestKeys = [
  "archivePath",
  "archiveSha256",
  "bindingSha256",
  "expectedCopies",
  "extractionRoot",
  "preset",
  "proofKind",
  "schemaVersion",
  "sourceInventory"
];
let nativeInstallStarted = false;

function requireObject(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value;
}

function requireExactKeys(value, keys, label) {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${label} fields do not match the proof contract`);
  }
}

function requireSha256(value, label) {
  if (typeof value !== "string" || !sha256Pattern.test(value)) {
    throw new Error(`${label} must be a lowercase SHA-256 digest`);
  }
  return value;
}

function requireNonnegativeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${label} must be a nonnegative integer`);
  }
  return value;
}

function normalizeRelativePath(value, label) {
  if (typeof value !== "string" || value.length === 0 || value.length > maxRelativePathLength || value.includes("\0")) {
    throw new Error(`${label} is not a bounded relative path`);
  }
  const portable = value.replaceAll("\\", "/");
  if (portable.startsWith("/") || /^[a-zA-Z]:/.test(portable)) {
    throw new Error(`${label} must be relative`);
  }
  const parts = portable.split("/");
  if (parts.some((part) => part.length === 0 || part === "." || part === "..")) {
    throw new Error(`${label} contains an unsafe segment`);
  }
  return parts.join("/");
}

function normalizeAbsolutePath(value, label) {
  if (typeof value !== "string" || !isAbsolute(value)) {
    throw new Error(`${label} must be absolute`);
  }
  return resolve(value);
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function compareOrdinal(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function sha256Text(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

async function sha256File(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) {
    hash.update(chunk);
  }
  return hash.digest("hex");
}

function assertOrdinaryFile(path, label, maximumSize) {
  const details = lstatSync(path);
  if (!details.isFile() || details.isSymbolicLink()) {
    throw new Error(`${label} must be an ordinary file`);
  }
  if (details.size > maximumSize) {
    throw new Error(`${label} exceeds the proof size limit`);
  }
  if (realpathSync.native(path).toLowerCase() !== resolve(path).toLowerCase()) {
    throw new Error(`${label} resolves through a reparse point`);
  }
  return details;
}

function inventoryExtraction(root, maximumFiles = maxInventoryFiles, maximumBytes = maxExtractedBytes) {
  const rootDetails = lstatSync(root);
  if (!rootDetails.isDirectory() || rootDetails.isSymbolicLink()) {
    throw new Error("extractionRoot must be an ordinary directory");
  }
  if (realpathSync.native(root).toLowerCase() !== resolve(root).toLowerCase()) {
    throw new Error("extractionRoot resolves through a reparse point");
  }
  const files = [];
  let totalBytes = 0;
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const fullPath = resolve(directory, entry.name);
      const details = lstatSync(fullPath);
      if (details.isSymbolicLink() || realpathSync.native(fullPath).toLowerCase() !== fullPath.toLowerCase()) {
        throw new Error("extractionRoot contains a reparse point");
      }
      if (details.isDirectory()) {
        visit(fullPath);
      } else if (details.isFile()) {
        const portablePath = relative(root, fullPath).split(sep).join("/");
        files.push({ path: portablePath, fullPath, size: details.size });
        totalBytes += details.size;
        if (files.length > maximumFiles || totalBytes > maximumBytes) {
          throw new Error("extracted inventory exceeds the proof limits");
        }
      } else {
        throw new Error("extractionRoot contains a non-file entry");
      }
    }
  };
  visit(root);
  return files.sort((left, right) => compareOrdinal(left.path, right.path));
}

function normalizeInventory(value, maximumFiles = maxInventoryFiles) {
  if (!Array.isArray(value) || value.length === 0 || value.length > maximumFiles) {
    throw new Error("sourceInventory must contain a bounded file list");
  }
  const seen = new Set();
  return value.map((entry, index) => {
    const object = requireObject(entry, `sourceInventory[${index}]`);
    requireExactKeys(object, ["path", "sha256", "size"], `sourceInventory[${index}]`);
    const path = normalizeRelativePath(object.path, `sourceInventory[${index}].path`);
    const identity = path.toLowerCase();
    if (seen.has(identity)) {
      throw new Error("sourceInventory contains a case-insensitive path collision");
    }
    seen.add(identity);
    return {
      path,
      size: requireNonnegativeInteger(object.size, `sourceInventory[${index}].size`),
      sha256: requireSha256(object.sha256, `sourceInventory[${index}].sha256`)
    };
  }).sort((left, right) => compareOrdinal(left.path, right.path));
}

function normalizeExpectedCopies(value, maximumCopies = maxCopies) {
  if (!Array.isArray(value) || value.length === 0 || value.length > maximumCopies) {
    throw new Error("expectedCopies must contain a bounded copy list");
  }
  const destinations = [];
  return value.map((entry, index) => {
    const object = requireObject(entry, `expectedCopies[${index}]`);
    requireExactKeys(object, ["destination", "sha256", "size", "source"], `expectedCopies[${index}]`);
    const source = normalizeRelativePath(object.source, `expectedCopies[${index}].source`);
    const destination = normalizeRelativePath(object.destination, `expectedCopies[${index}].destination`);
    const destinationKey = destination.toLowerCase();
    if (destinations.some((existing) => existing === destinationKey || existing.startsWith(`${destinationKey}/`) || destinationKey.startsWith(`${existing}/`))) {
      throw new Error("expectedCopies contains a destination collision");
    }
    destinations.push(destinationKey);
    return {
      source,
      destination,
      size: requireNonnegativeInteger(object.size, `expectedCopies[${index}].size`),
      sha256: requireSha256(object.sha256, `expectedCopies[${index}].sha256`)
    };
  }).sort((left, right) => compareOrdinal(left.destination, right.destination));
}

export function validatePreset(value, fixedFixture) {
  const maximumSteps = fixedFixture ? 4 : maxCuratedPresetSteps;
  const maximumChars = fixedFixture ? 8 * 1024 : maxCuratedPresetChars;
  if (!Array.isArray(value) || value.length === 0 || value.length > maximumSteps || canonicalJson(value).length > maximumChars) {
    throw new Error("preset must be a bounded nonempty Collection choices.options array");
  }
  return value;
}

function validateCuratedSelection(archiveSha256, preset, expectedCopies) {
  if (archiveSha256 !== representativeArchiveSha256) {
    throw new Error("archiveSha256 is not the representative proof archive");
  }
  const presetIdentity = canonicalJson(preset);
  const selection = curatedSelections.find((candidate) => canonicalJson(candidate.preset) === presetIdentity);
  if (!selection) {
    throw new Error("preset is not a curated representative choice");
  }
  if (expectedCopies.length !== 1 || canonicalJson(expectedCopies[0]) !== canonicalJson(selection.copy)) {
    throw new Error("expectedCopies does not match the curated preset");
  }
}

export function calculateBinding({ archiveSha256, sourceInventory, preset, expectedCopies }) {
  return sha256Text(canonicalJson({ archiveSha256, sourceInventory, preset, expectedCopies }));
}

export async function describeInventory(extractionRoot) {
  const root = normalizeAbsolutePath(extractionRoot, "extractionRoot");
  const files = inventoryExtraction(root);
  const inventory = [];
  for (const file of files) {
    inventory.push({ path: file.path, size: file.size, sha256: await sha256File(file.fullPath) });
  }
  return inventory;
}

function unexpectedCallback(name) {
  return () => {
    throw new Error(`native FOMOD requested unsupported ${name} state`);
  };
}

function createInstaller() {
  return new NativeModInstaller(
    unexpectedCallback("plugin dependency"),
    unexpectedCallback("application version"),
    unexpectedCallback("game version"),
    unexpectedCallback("extender version"),
    unexpectedCallback("interactive dialog"),
    unexpectedCallback("interactive dialog completion"),
    unexpectedCallback("interactive dialog update")
  );
}

function normalizeEngineCopies(instructions, inventoryByPath, maximumCopies = maxCopies) {
  if (!Array.isArray(instructions) || instructions.length > maximumCopies + 1) {
    throw new Error("native FOMOD returned an unbounded instruction list");
  }
  const copies = [];
  const destinations = [];
  let enableAllPluginsMarkers = 0;
  for (const instruction of instructions) {
    const object = requireObject(instruction, "native instruction");
    if (object.type === "enableallplugins") {
      requireExactKeys(object, ["priority", "type"], "native enableallplugins marker");
      if (object.priority !== 0) {
        throw new Error("native enableallplugins marker is malformed");
      }
      enableAllPluginsMarkers += 1;
      if (enableAllPluginsMarkers > 1) {
        throw new Error("native FOMOD returned repeated enableallplugins markers");
      }
      continue;
    }
    if (object.type !== "copy") {
      throw new Error(`native FOMOD returned unsupported instruction type ${String(object.type)}`);
    }
    requireExactKeys(object, ["destination", "priority", "source", "type"], "native copy instruction");
    if (object.priority !== 0) {
      throw new Error("native FOMOD returned an unsupported copy priority");
    }
    const source = normalizeRelativePath(object.source, "native copy source");
    const destination = normalizeRelativePath(object.destination, "native copy destination");
    const sourceIdentity = source.toLowerCase();
    const sourceDetails = inventoryByPath.get(sourceIdentity);
    if (!sourceDetails) {
      throw new Error("native FOMOD selected a source outside the verified inventory");
    }
    const destinationIdentity = destination.toLowerCase();
    if (destinations.some((existing) => existing === destinationIdentity || existing.startsWith(`${destinationIdentity}/`) || destinationIdentity.startsWith(`${existing}/`))) {
      throw new Error("native FOMOD returned a destination collision");
    }
    destinations.push(destinationIdentity);
    copies.push({
      type: "copy",
      source,
      destination,
      size: sourceDetails.size,
      sourceSha256: sourceDetails.sha256
    });
  }
  if (copies.length === 0) {
    throw new Error("native FOMOD returned no copy instructions");
  }
  return copies.sort((left, right) => compareOrdinal(left.destination, right.destination));
}

function compareCopies(actual, expected) {
  if (actual.length !== expected.length) {
    throw new Error("native FOMOD copy count does not match expectedCopies");
  }
  for (let index = 0; index < actual.length; index += 1) {
    const left = actual[index];
    const right = expected[index];
    if (left.source !== right.source || left.destination !== right.destination || left.size !== right.size || left.sourceSha256 !== right.sha256) {
      throw new Error("native FOMOD copies do not match expectedCopies");
    }
  }
}

export async function resolveRequest(requestValue) {
  return resolveValidatedRequest(requestValue, true);
}

export async function resolveCuratedRequest(requestValue) {
  return resolveValidatedRequest(requestValue, false);
}

async function validateRecipe(request, preset, expectedCopies) {
  const recipePath = normalizeAbsolutePath(request.recipePath, "recipePath");
  const recipeHash = requireSha256(request.recipeSha256, "recipeSha256");
  assertOrdinaryFile(recipePath, "recipePath", 8 * 1024 * 1024);
  const bytes = readFileSync(recipePath);
  if (createHash("sha256").update(bytes).digest("hex") !== recipeHash) {
    throw new Error("curated recipe identity changed");
  }
  const recipe = JSON.parse(bytes.toString("utf8").replace(/^\uFEFF/, ""));
  if (![1, 2].includes(recipe.schema) || !Array.isArray(recipe.mods) || recipe.mods.length > 10000 ||
      !Number.isSafeInteger(request.modId) || request.modId <= 0 || !Number.isSafeInteger(request.fileId) || request.fileId <= 0) {
    throw new Error("curated recipe is unsupported");
  }
  const members = recipe.mods.filter((mod) => mod.modId === request.modId && mod.fileId === request.fileId);
  if (members.length !== 1 || members[0].archiveSha256 !== request.archiveSha256 || !members[0].selected ||
      canonicalJson(members[0].fomodPreset) !== canonicalJson(preset)) {
    throw new Error("FOMOD selection does not match the curated recipe");
  }
  const expected = expectedCopies.map((file) => ({ archivePath: file.source, modPath: file.destination, sha256: file.sha256 }));
  const files = members[0].files;
  if (!Array.isArray(files) || files.length !== expected.length) throw new Error("FOMOD file count differs from the curated recipe");
  const normalize = (entries) => entries.map((file) => ({
    archivePath: normalizeRelativePath(file.archivePath, "curated source"),
    modPath: normalizeRelativePath(file.modPath, "curated destination"),
    sha256: requireSha256(file.sha256, "curated file hash")
  })).sort((left, right) => left.modPath.localeCompare(right.modPath, "en"));
  if (canonicalJson(normalize(files)) !== canonicalJson(normalize(expected))) {
    throw new Error("FOMOD copies do not match the curated recipe");
  }
}

async function resolveValidatedRequest(requestValue, fixedFixture) {
  if (dependencyPackage.version !== dependencyVersion || dependencyPackage.license !== "GPL-3.0") {
    throw new Error("native FOMOD dependency identity does not match the proof contract");
  }
  const request = requireObject(requestValue, "request");
  const expectedKind = fixedFixture ? proofKind : "curated-collection-fomod";
  requireExactKeys(request, fixedFixture ? requestKeys : [...requestKeys, "recipePath", "recipeSha256", "modId", "fileId"], "request");
  if (request.schemaVersion !== 1 || request.proofKind !== expectedKind) {
    throw new Error("request does not target this developer proof");
  }
  const archivePath = normalizeAbsolutePath(request.archivePath, "archivePath");
  const extractionRoot = normalizeAbsolutePath(request.extractionRoot, "extractionRoot");
  const archiveSha256 = requireSha256(request.archiveSha256, "archiveSha256");
  const maximumFiles = fixedFixture ? maxInventoryFiles : 4096;
  const maximumCopies = fixedFixture ? maxCopies : 512;
  const sourceInventory = normalizeInventory(request.sourceInventory, maximumFiles);
  if (fixedFixture && canonicalJson(sourceInventory) !== canonicalJson([...trustedInventory].sort((left, right) => compareOrdinal(left.path, right.path)))) {
    throw new Error("sourceInventory does not match the pinned representative extraction");
  }
  const preset = validatePreset(request.preset, fixedFixture);
  const expectedCopies = normalizeExpectedCopies(request.expectedCopies, maximumCopies);
  if (fixedFixture) validateCuratedSelection(archiveSha256, preset, expectedCopies);
  else await validateRecipe(request, preset, expectedCopies);
  const bindingSha256 = requireSha256(request.bindingSha256, "bindingSha256");
  const calculatedBinding = calculateBinding({ archiveSha256, sourceInventory, preset, expectedCopies });
  if (bindingSha256 !== calculatedBinding) {
    throw new Error("bindingSha256 does not bind the supplied archive, inventory, preset, and expected copies");
  }
  assertOrdinaryFile(archivePath, "archivePath", fixedFixture ? maxArchiveBytes : maxCuratedArchiveBytes);
  if (await sha256File(archivePath) !== archiveSha256) {
    throw new Error("archive SHA-256 does not match archiveSha256");
  }
  const extractedFiles = inventoryExtraction(extractionRoot, maximumFiles, fixedFixture ? maxExtractedBytes : maxCuratedArchiveBytes);
  if (extractedFiles.length !== sourceInventory.length) {
    throw new Error("sourceInventory does not describe every extracted file");
  }
  const inventoryByPath = new Map();
  for (let index = 0; index < extractedFiles.length; index += 1) {
    const actual = extractedFiles[index];
    const expected = sourceInventory[index];
    if (actual.path !== expected.path || actual.size !== expected.size || await sha256File(actual.fullPath) !== expected.sha256) {
      throw new Error(`sourceInventory mismatch at ${expected.path}`);
    }
    inventoryByPath.set(expected.path.toLowerCase(), expected);
  }
  for (const copy of expectedCopies) {
    const sourceDetails = inventoryByPath.get(copy.source.toLowerCase());
    if (!sourceDetails || sourceDetails.size !== copy.size || sourceDetails.sha256 !== copy.sha256) {
      throw new Error("expectedCopies references an unverified source identity");
    }
  }
  const nativeFiles = sourceInventory.map((entry) => entry.path.replaceAll("/", "\\"));
  if (nativeInstallStarted) {
    throw new Error("native FOMOD proof permits one install per process");
  }
  nativeInstallStarted = true;
  const result = await createInstaller().install(nativeFiles, [], null, extractionRoot, preset, false, true);
  if (result === null || result.message !== "Installation successful") {
    throw new Error("native FOMOD did not complete the preset installation");
  }
  const copies = normalizeEngineCopies(result.instructions, inventoryByPath, maximumCopies);
  compareCopies(copies, expectedCopies);
  return {
    schemaVersion: 1,
    proofKind: expectedKind,
    bindingSha256,
    archiveSha256,
    dependency: {
      name: "@nexusmods/fomod-installer-native",
      version: dependencyVersion,
      integrity: dependencyIntegrity,
      license: dependencyPackage.license
    },
    copies,
    ...(!fixedFixture ? { recipeSha256: request.recipeSha256, modId: request.modId, fileId: request.fileId } : {})
  };
}

async function main() {
  if (process.argv.length !== 3) {
    throw new Error("usage: node resolve.mjs <request.json>");
  }
  const requestPath = normalizeAbsolutePath(process.argv[2], "request path");
  assertOrdinaryFile(requestPath, "request file", maxRequestBytes);
  const request = JSON.parse(readFileSync(requestPath, "utf8"));
  const result = await resolveRequest(request);
  process.stdout.write(`${JSON.stringify(result)}\n`, () => process.exit(0));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${JSON.stringify({ error: error instanceof Error ? error.message : String(error) })}\n`, () => process.exit(1));
  });
}
