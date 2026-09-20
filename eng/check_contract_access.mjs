// SPDX-License-Identifier: Apache-2.0
/** WP01.01 closed current contract assignment and compiled dependency audit. */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { fromBinary } from "@bufbuild/protobuf";
import { FileDescriptorSetSchema } from "@bufbuild/protobuf/wkt";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const POLICY = "eng/policy/contract-access.json";
const ACCESS = new Set(["public", "internal"]);
const SOURCE = /\.(cs|java|kt|ts)$/;

function requireThat(value, message) {
  if (!value) throw new Error(message);
}

export function safePath(value) {
  requireThat(
    typeof value === "string" &&
      value &&
      !value.includes("\\") &&
      !value.includes(":") &&
      !value.startsWith("/") &&
      value.split("/").every((p) => p && p !== "." && p !== ".."),
    "unsafe path",
  );
  return value;
}

function bytes(root, relative) {
  safePath(relative);
  const target = path.join(root, relative);
  requireThat(
    realpathSync(target).startsWith(realpathSync(root) + path.sep),
    "source escapes root",
  );
  let current = target;
  while (current !== root) {
    requireThat(!lstatSync(current).isSymbolicLink(), "linked source");
    current = path.dirname(current);
  }
  return readFileSync(target, "utf8").replaceAll("\r\n", "\n");
}

export function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function git(root, ...args) {
  return execFileSync("git", ["-C", root, ...args], { encoding: "utf8" }).trim();
}

export function inventory(root) {
  const files = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    .split("\0")
    .filter(Boolean);
  requireThat(new Set(files).size === files.length, "duplicate Git path");
  for (const line of git(root, "ls-files", "--stage").split("\n")) {
    requireThat(
      !line.startsWith("120000 ") && !line.startsWith("160000 "),
      "linked source/submodule",
    );
  }
  return files;
}

export function protoc(root = ROOT) {
  const assets = JSON.parse(
    readFileSync(path.join(root, "eng/Codegen/obj/project.assets.json"), "utf8"),
  );
  const name = Object.keys(assets.libraries).find((k) => k.toLowerCase().startsWith("grpc.tools/"));
  requireThat(name, "restore pinned Grpc.Tools first");
  const platform = { win32: "windows_x64", linux: "linux_x64", darwin: "macosx_x64" }[
    process.platform
  ];
  requireThat(platform && process.arch === "x64", "unsupported producer architecture");
  const suffix = process.platform === "win32" ? ".exe" : "";
  for (const folder of Object.keys(assets.packageFolders)) {
    const executable = path.join(folder, name.toLowerCase(), "tools", platform, "protoc" + suffix);
    if (existsSync(executable)) return executable;
  }
  throw new Error("pinned protoc missing");
}

export function compile(root, schemas, executable = protoc()) {
  const directory = mkdtempSync(path.join(tmpdir(), "arcforges-access-"));
  try {
    const output = path.join(directory, "contracts.binpb");
    const includes = ["public/proto", "internal/proto"].filter((p) =>
      existsSync(path.join(root, p)),
    );
    execFileSync(
      executable,
      [
        ...includes.map((p) => "--proto_path=" + path.join(root, p)),
        "--include_imports",
        "--descriptor_set_out=" + output,
        ...schemas.map((s) => path.join(root, safePath(s.path))),
      ],
      { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    );
    return fromBinary(FileDescriptorSetSchema, readFileSync(output));
  } finally {
    requireThat(
      path.dirname(directory) === path.resolve(tmpdir()),
      "temporary directory escaped its owner",
    );
    rmSync(directory, { recursive: true, force: true });
  }
}

export function descriptorGraph(descriptor, schemas) {
  const files = new Map();
  for (const row of schemas) {
    const prefix = row.access + "/proto/";
    requireThat(
      ACCESS.has(row.access) && row.path.startsWith(prefix),
      "schema access/path mismatch",
    );
    const name = safePath(row.path.slice(prefix.length));
    requireThat(!files.has(name), "colliding proto virtual path");
    files.set(name, row);
  }
  requireThat(
    new Set(descriptor.file.map((f) => f.name)).size === descriptor.file.length,
    "duplicate descriptor file",
  );
  requireThat(
    descriptor.file.length === files.size && descriptor.file.every((f) => files.has(f.name)),
    "unassigned descriptor file",
  );
  const nodes = new Map();
  const edges = new Map();
  const imports = new Map();
  function add(name, kind, file, references = []) {
    requireThat(name && !nodes.has(name), "duplicate contract definition");
    nodes.set(name, {
      name,
      kind,
      file: files.get(file.name).path,
      access: files.get(file.name).access,
    });
    edges.set(
      name,
      references.filter(Boolean).map((r) => r.replace(/^\./, "")),
    );
  }
  function message(value, prefix, file) {
    const name = prefix + value.name;
    add(
      name,
      "message",
      file,
      [...value.field, ...value.extension].flatMap((f) => [f.typeName, f.extendee]),
    );
    requireThat(value.extension.length === 0, "unassigned extension declaration");
    for (const child of value.nestedType) message(child, name + ".", file);
    for (const item of value.enumType) add(name + "." + item.name, "enum", file);
  }
  for (const file of descriptor.file) {
    const prefix = file.package ? file.package + "." : "";
    imports.set(file.name, file.dependency);
    for (const value of file.messageType) message(value, prefix, file);
    for (const value of file.enumType) add(prefix + value.name, "enum", file);
    for (const value of file.service)
      add(
        prefix + value.name,
        "service",
        file,
        value.method.flatMap((m) => [m.inputType, m.outputType]),
      );
    // Extension-bearing schemas need a reviewed assignment profile before admission.
    requireThat(
      file.extension.length === 0 && file.messageType.every((m) => m.extension.length === 0),
      "unassigned extension declaration",
    );
  }
  function closure(graph, access) {
    for (const source of graph.keys()) {
      const seen = new Set();
      const pending = [...graph.get(source)];
      while (pending.length) {
        const target = pending.pop();
        requireThat(graph.has(target), "unresolved contract dependency: " + target);
        requireThat(
          access(source) !== "public" || access(target) === "public",
          "public-to-internal dependency: " + source + " -> " + target,
        );
        if (!seen.has(target)) {
          seen.add(target);
          pending.push(...graph.get(target));
        }
      }
    }
  }
  closure(imports, (name) => files.get(name).access);
  closure(edges, (name) => nodes.get(name).access);
  return [...nodes.values()].sort((a, b) => a.name.localeCompare(b.name, "en"));
}

export function checkAssignments(actual, declared) {
  requireThat(
    new Set(declared.map((r) => r.name)).size === declared.length,
    "duplicate type assignment",
  );
  const ordered = (rows) => [...rows].sort((a, b) => a.name.localeCompare(b.name, "en"));
  assert.deepEqual(ordered(actual), ordered(declared), "incomplete or changed type assignment");
}

export function declaredTypes(text) {
  const code = text.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, "");
  return [
    ...code.matchAll(
      /(?:^|\n)\s*(?:(?:public|private|internal|protected|static|final|sealed|partial|abstract|export|readonly|data|value|open)\s+)*(?:class|interface|struct|enum|record|object|type)\s+([A-Za-z_]\w*)/g,
    ),
  ].map((m) => m[1]);
}

function fields(row, names) {
  assert.deepEqual(Object.keys(row).sort(), names.split(" ").sort(), "invalid policy fields");
}

export function checkSources(root, files, policy) {
  fields(
    policy,
    "schemaVersion licence reviewedOn design sourceCommit schemas types packages distribution buildInputs",
  );
  fields(policy.design, "commit path sha256");
  requireThat(
    /^[0-9a-f]{40}$/.test(policy.sourceCommit) &&
      /^[0-9a-f]{40}$/.test(policy.design.commit) &&
      /^[0-9a-f]{64}$/.test(policy.design.sha256),
    "invalid source identity",
  );
  for (const row of policy.schemas) fields(row, "path access sha256");
  for (const row of policy.distribution) fields(row, "path package access types sha256 kind");
  for (const row of policy.packages) fields(row, "id sourceRoot access");
  for (const row of policy.buildInputs) fields(row, "path sha256");
  for (const row of policy.types) fields(row, "name kind file access");
  requireThat(
    policy.schemaVersion === 1 && policy.licence === "Apache-2.0",
    "invalid access policy",
  );
  requireThat(
    policy.schemas.length > 0 && policy.distribution.length > 0,
    "empty access inventory",
  );
  const actualSchemas = files.filter((p) => p.endsWith(".proto") && /^(public|internal)\//.test(p));
  const actualSources = files.filter((p) => p.startsWith("src/") && SOURCE.test(p));
  for (const [rows, actual] of [
    [policy.schemas, actualSchemas],
    [policy.distribution, actualSources],
  ]) {
    requireThat(
      new Set(rows.map((r) => r.path)).size === rows.length,
      "duplicate source assignment",
    );
    assert.deepEqual(
      rows.map((r) => r.path).sort(),
      actual.sort(),
      "unassigned distribution/schema source",
    );
    for (const row of rows) {
      requireThat(ACCESS.has(row.access), "unknown access boundary");
      requireThat(digest(bytes(root, row.path)) === row.sha256, "source hash drift: " + row.path);
      if (rows === policy.distribution) {
        requireThat(["generated", "authored"].includes(row.kind), "invalid source kind");
        assert.deepEqual(
          declaredTypes(bytes(root, row.path)),
          row.types,
          "incomplete source type assignment",
        );
        const owner = policy.packages.find((p) => p.id === row.package);
        requireThat(
          owner && owner.access === row.access && row.path.startsWith(owner.sourceRoot + "/"),
          "wrong distribution package",
        );
        requireThat(
          Array.isArray(row.types) && row.types.every((t) => typeof t === "string" && t),
          "missing declared types",
        );
      }
    }
  }
  requireThat(
    new Set(policy.packages.map((p) => p.id)).size === policy.packages.length,
    "duplicate package owner",
  );
  for (const row of policy.packages) {
    safePath(row.sourceRoot);
    requireThat(
      ACCESS.has(row.access) && row.sourceRoot.startsWith("src/" + row.access + "/"),
      "wrong package access",
    );
    requireThat(
      policy.distribution.some((p) => p.package === row.id),
      "empty package assignment",
    );
  }
  const rootInputs = new Set([
    "Directory.Build.props",
    "Directory.Build.targets",
    "Directory.Packages.props",
    "NuGet.config",
    "build.gradle.kts",
    "settings.gradle.kts",
    "gradle/libs.versions.toml",
    "gradle.properties",
    "package.json",
    "package-lock.json",
  ]);
  const buildInputs = files.filter(
    (p) =>
      rootInputs.has(p) ||
      (p.startsWith("src/") &&
        (/\.(csproj|gradle\.kts)$/.test(p) ||
          /(?:^|\/)(packages\.lock\.json|gradle\.lockfile|tsconfig\.json|package\.json)$/.test(p))),
  );
  assert.deepEqual(
    policy.buildInputs.map((p) => p.path).sort(),
    buildInputs.sort(),
    "unassigned package graph input",
  );
  for (const row of policy.buildInputs)
    requireThat(
      digest(bytes(root, row.path)) === row.sha256,
      "package graph input drift: " + row.path,
    );
}

export function audit(root = ROOT) {
  const policy = JSON.parse(bytes(root, POLICY));
  const before = [git(root, "rev-parse", "HEAD"), git(root, "status", "--porcelain")];
  const files = inventory(root);
  checkSources(root, files, policy);
  const types = descriptorGraph(compile(root, policy.schemas), policy.schemas);
  checkAssignments(types, policy.types);
  assert.deepEqual(
    [git(root, "rev-parse", "HEAD"), git(root, "status", "--porcelain")],
    before,
    "source changed during audit",
  );
  return {
    substep: "WP01.01",
    result: "passed",
    commit: before[0],
    dirty: Boolean(before[1]),
    schemaFiles: policy.schemas.length,
    contractTypes: types.length,
    distributionFiles: policy.distribution.length,
    declaredSourceTypes: policy.distribution.reduce((n, r) => n + r.types.length, 0),
    packages: policy.packages.length,
    publicToInternalReclassifications: [],
    internalToPublicReclassifications: [],
    policySha256: digest(bytes(root, POLICY)),
    design: policy.design,
    limitations:
      "Current contract access and compiled dependency proof; full production schemas remain WP03, provider/device operation is separate evidence.",
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const output = path.join(ROOT, "artifacts/evidence/contract-access.json");
  let report;
  try {
    report = audit();
  } catch (error) {
    report = { substep: "WP01.01", result: "failed", error: error.message };
    process.exitCode = 1;
  }
  mkdirSync(path.dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
}
