// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  ROOT,
  baseCommit,
  checkAssignments,
  checkPackageBoundaries,
  checkPackageInputs,
  checkRetiredHistory,
  checkRetiredOperations,
  maskXmlComments,
  checkSources,
  compile,
  declaredTypes,
  descriptorGraph,
  HTTP_SCHEMA_SOURCE,
  inventory,
  retiredIdentities,
  safePath,
} from "../../eng/check_contract_access.mjs";

function temporary(t) {
  const root = mkdtempSync(path.join(tmpdir(), "arcforges-access-test-"));
  t.after(() => {
    assert.equal(path.dirname(root), path.resolve(tmpdir()));
    rmSync(root, { recursive: true, force: true });
  });
  return root;
}

function fixture(t, rows) {
  const root = temporary(t);
  const schemas = rows.map(([access, name, body]) => {
    const relative = access + "/proto/" + name;
    mkdirSync(path.dirname(path.join(root, relative)), { recursive: true });
    writeFileSync(path.join(root, relative), 'syntax = "proto3"; package sample;\n' + body);
    return { path: relative, access };
  });
  return { descriptor: compile(root, schemas), schemas };
}

const publicMessage = "message Public { string text = 1; }";
const internalMessage = "message Private { string secret = 1; }";

test("real public messages, nested enum and RPC have complete assignments", (t) => {
  const { descriptor, schemas } = fixture(t, [
    [
      "public",
      "api.proto",
      "message Public { message Child { string value = 1; } enum Kind { ZERO = 0; } Child child = 1; Kind kind = 2; } service Api { rpc Read(Public) returns (Public.Child); }",
    ],
  ]);
  const actual = descriptorGraph(descriptor, schemas);
  assert.deepEqual(
    actual.map((r) => r.name),
    ["sample.Api", "sample.Public", "sample.Public.Child", "sample.Public.Kind"],
  );
  checkAssignments(actual, actual);
  assert.throws(
    () =>
      checkAssignments(
        actual,
        actual.filter((r) => !r.name.endsWith("Child")),
      ),
    /assignment/,
  );
  assert.throws(() => checkAssignments(actual, [...actual, actual[0]]), /duplicate/);
});

test("direct public-to-internal type and import fails", (t) => {
  const { descriptor, schemas } = fixture(t, [
    ["internal", "private.proto", internalMessage],
    ["public", "api.proto", 'import "private.proto"; message Public { Private value = 1; }'],
  ]);
  assert.throws(() => descriptorGraph(descriptor, schemas), /public-to-internal/);
});

test("transitive public wrapper cannot launder an internal type", (t) => {
  const { descriptor, schemas } = fixture(t, [
    ["internal", "private.proto", internalMessage],
    ["public", "bridge.proto", 'import "private.proto"; message Bridge { Private value = 1; }'],
    ["public", "api.proto", 'import "bridge.proto"; message Public { Bridge value = 1; }'],
  ]);
  assert.throws(() => descriptorGraph(descriptor, schemas), /public-to-internal/);
});

test("even an unused private import is forbidden", (t) => {
  const { descriptor, schemas } = fixture(t, [
    ["internal", "private.proto", internalMessage],
    ["public", "api.proto", 'import "private.proto"; ' + publicMessage],
  ]);
  assert.throws(() => descriptorGraph(descriptor, schemas), /public-to-internal/);
});

test("internal services may reuse public types", (t) => {
  const { descriptor, schemas } = fixture(t, [
    ["public", "public.proto", publicMessage],
    [
      "internal",
      "private.proto",
      'import "public.proto"; message Private { Public input = 1; } service PrivateApi { rpc Read(Public) returns (Private); }',
    ],
  ]);
  const actual = descriptorGraph(descriptor, schemas);
  assert.equal(actual.find((x) => x.name === "sample.Public").access, "public");
  assert.equal(actual.find((x) => x.name === "sample.PrivateApi").access, "internal");
});

test("missing file, unresolved type and duplicate virtual path fail closed", (t) => {
  const { descriptor, schemas } = fixture(t, [["public", "public.proto", publicMessage]]);
  assert.throws(() => descriptorGraph(descriptor, []), /unassigned/);
  assert.throws(
    () =>
      descriptorGraph(descriptor, [
        ...schemas,
        { path: "internal/proto/public.proto", access: "internal" },
      ]),
    /colliding/,
  );
  descriptor.file[0].messageType[0].field[0].typeName = ".sample.Unassigned";
  assert.throws(() => descriptorGraph(descriptor, schemas), /unresolved/);
});

test("descriptor type graph rejects internal RPC output independently of imports", (t) => {
  const { descriptor, schemas } = fixture(t, [
    [
      "public",
      "public.proto",
      publicMessage + " service Api { rpc Read(Public) returns (Public); }",
    ],
    ["internal", "private.proto", internalMessage],
  ]);
  descriptor.file.find((f) => f.name === "public.proto").service[0].method[0].outputType =
    ".sample.Private";
  assert.throws(() => descriptorGraph(descriptor, schemas), /public-to-internal/);
});

test("reviewed current source inventory rejects omissions, reassignment and hashes", () => {
  const policy = JSON.parse(
    readFileSync(path.join(ROOT, "eng/policy/contract-access.json"), "utf8"),
  );
  const files = inventory(ROOT);
  checkSources(ROOT, files, policy, { base: policy });
  for (const mutate of [
    (p) => p.distribution.pop(),
    (p) => p.distribution.shift(),
    (p) => p.schemas.pop(),
    (p) => p.distribution[0].types.pop(),
    (p) =>
      (p.distribution[0].access = p.distribution[0].access === "public" ? "internal" : "public"),
    (p) => (p.distribution[0].sha256 = "0".repeat(64)),
    (p) => (p.distribution[0].package = "Unknown.Package"),
    (p) => p.packages.pop(),
    (p) => (p.buildInputs[0].sha256 = "0".repeat(64)),
  ]) {
    const changed = structuredClone(policy);
    mutate(changed);
    assert.throws(() => checkSources(ROOT, files, changed, { base: policy }));
  }
  assert.throws(() => checkSources(ROOT, [...files, "src/internal/New.cs"], policy), /unassigned/);
});

test("type inventory excludes comments, string text and parameter types", () => {
  assert.deepEqual(
    declaredTypes(
      "public readonly record struct DocumentId {}\npublic sealed record class Receipt {}\npublic record Bare(string Value);",
    ),
    ["DocumentId", "Receipt", "Bare"],
  );
  assert.deepEqual(
    declaredTypes(
      '/* class Fake {} */\npublic sealed class Real {\n public override bool Equals(object other) { return false; }\n private const string Text = "class Fake {}";\n private sealed class Nested<T> {}\n}',
    ),
    ["Real", "Nested"],
  );
  assert.deepEqual(
    declaredTypes(
      "export type Message = {};\npublic object Kotlin {\n public class Dsl private constructor() {}\n}",
    ),
    ["Message", "Kotlin", "Dsl"],
  );
});

test("unsafe inventory paths are never read", () => {
  for (const input of ["../outside", "/absolute", "C:/absolute", "a\\b", "a/../b", "a//b"])
    assert.throws(() => safePath(input), /unsafe/);
});

test("package routing rejects private dependencies and extension Android output", () => {
  const row = {
    id: "public",
    kind: "npm",
    access: "public",
    sourceRoot: "src/public/ts/example",
    dependencies: [],
    proto: [],
    jsonSchemas: [],
  };
  const internal = {
    ...row,
    id: "private",
    access: "internal",
    sourceRoot: "src/internal/ts/example",
  };
  checkPackageBoundaries(ROOT, { schemaVersion: 1, packages: [row, internal] });
  assert.throws(
    () =>
      checkPackageBoundaries(ROOT, {
        schemaVersion: 1,
        packages: [{ ...row, dependencies: ["private"] }, internal],
      }),
    /public-to-internal/,
  );
  assert.throws(
    () =>
      checkPackageBoundaries(ROOT, {
        schemaVersion: 1,
        packages: [{ ...row, proto: ["internal/proto/arcforges/operator/v1/operator.proto"] }],
      }),
    /public-to-internal/,
  );
  assert.throws(
    () =>
      checkPackageBoundaries(ROOT, {
        schemaVersion: 1,
        packages: [
          {
            ...row,
            kind: "maven",
            proto: ["public/proto/arcforges/extensions/v1/extensions.proto"],
          },
        ],
      }),
    /extension IPC/,
  );
});

test("public HTTP schema cannot reference an internal schema", (t) => {
  const root = temporary(t);
  mkdirSync(path.join(root, "public/http"), { recursive: true });
  writeFileSync(
    path.join(root, "public/http/schema.json"),
    JSON.stringify({ $ref: "../../internal/private.json" }),
  );
  const row = {
    id: "public",
    kind: "npm",
    access: "public",
    sourceRoot: "src/public/ts/example",
    dependencies: [],
    proto: [],
    jsonSchemas: ["public/http/schema.json"],
  };
  assert.throws(
    () => checkPackageBoundaries(root, { schemaVersion: 1, packages: [row] }),
    /public-to-internal JSON/,
  );
});

test("actual project and npm dependencies cannot bypass reviewed package edges", (t) => {
  const root = temporary(t);
  const project = {
    id: "ArcForges.Public",
    kind: "nuget",
    sourceRoot: "src/public/dotnet/ArcForges.Public",
    dependencies: [],
  };
  const internal = {
    ...project,
    id: "ArcForges.Private",
    sourceRoot: "src/internal/dotnet/ArcForges.Private",
  };
  for (const row of [project, internal]) {
    mkdirSync(path.join(root, row.sourceRoot), { recursive: true });
    writeFileSync(path.join(root, row.sourceRoot, row.id + ".csproj"), "<Project />");
  }
  checkPackageInputs(root, { packages: [project, internal] });
  writeFileSync(
    path.join(root, project.sourceRoot, project.id + ".csproj"),
    '<Project><ProjectReference Include="../../../internal/dotnet/ArcForges.Private/ArcForges.Private.csproj" /></Project>',
  );
  assert.throws(
    () => checkPackageInputs(root, { packages: [project, internal] }),
    /dependency graph/,
  );
  writeFileSync(
    path.join(root, project.sourceRoot, project.id + ".csproj"),
    '<Project><PackageReference Include="ArcForges.Unregistered" /></Project>',
  );
  assert.throws(() => checkPackageInputs(root, { packages: [project, internal] }), /bypasses/);
  writeFileSync(
    path.join(root, project.sourceRoot, project.id + ".csproj"),
    '<Project><Compile Include="../../../internal/dotnet/ArcForges.Private/Operator.cs" /></Project>',
  );
  assert.throws(
    () => checkPackageInputs(root, { packages: [project, internal] }),
    /escapes package owner/,
  );
  const npm = {
    id: "@arcforges/public",
    kind: "npm",
    sourceRoot: "src/public/ts/public",
    dependencies: [],
  };
  mkdirSync(path.join(root, npm.sourceRoot), { recursive: true });
  writeFileSync(
    path.join(root, npm.sourceRoot, "package.json"),
    JSON.stringify({
      name: npm.id,
      license: "Apache-2.0",
      dependencies: { "@arcforges/operator-client": "1.0.0" },
    }),
  );
  assert.throws(() => checkPackageInputs(root, { packages: [npm] }), /dependency graph/);
});

test("XML comments cannot concatenate dependency tokens or create new comment delimiters", () => {
  const boundary = "<!<!-- comment -->--";
  const masked = maskXmlComments(boundary);
  assert.equal(masked.length, boundary.length);
  assert.equal(masked.includes("<!--"), false);
  assert.equal(
    maskXmlComments("Project<!-- ignored -->Reference").includes("ProjectReference"),
    false,
  );
  assert.equal(
    maskXmlComments('<!-- <PackageReference Include="ArcForges.Private" /> -->').trim(),
    "",
  );
  assert.throws(() => maskXmlComments("<Project><!-- unterminated"), /malformed XML comment/);
  assert.throws(() => maskXmlComments("<Project>-->"), /malformed XML comment/);
});

test("closed HTTP schema source roots admit exactly the registered roots", () => {
  for (const accepted of [
    "public/http/v1/schema.json",
    "internal/ai-http/v1/schema.json",
    "internal/ai-http/v1/configuration.schema.json",
    "internal/cf-http/v1/schema.json",
    "internal/storage-http/v1/schema.json",
  ])
    assert.ok(HTTP_SCHEMA_SOURCE.test(accepted), accepted);
  for (const refused of [
    "internal/other-http/v1/schema.json",
    "internal/cf-http-extra/v1/schema.json",
    "internal/storage-http.json",
    "internal/cf-http/schema.txt",
    "public/cf-http/v1/schema.json",
    "src/internal/cf-http/v1/schema.json",
    "fixtures/internal/con-15-cf-internal.json",
    "internal/proto/arcforges/cf/v1/stream.proto",
  ])
    assert.ok(!HTTP_SCHEMA_SOURCE.test(refused), refused);
});

test("the real manifest assigns both private HTTP schemas to the two existing internal packages", () => {
  const manifest = JSON.parse(readFileSync(path.join(ROOT, "eng/contract-packages.json"), "utf8"));
  const owners = (schema) =>
    manifest.packages.filter((row) => row.jsonSchemas.includes(schema)).map((row) => row.id);
  for (const schema of [
    "internal/cf-http/v1/schema.json",
    "internal/storage-http/v1/schema.json",
  ]) {
    assert.deepEqual(owners(schema).sort(), [
      "@arcforges/ai-internal",
      "ArcForges.Contracts.CloudInternal",
    ]);
    assert.ok(
      readFileSync(path.join(ROOT, schema), "utf8").includes("SPDX-License-Identifier: Apache-2.0"),
    );
  }
  checkPackageBoundaries(ROOT, manifest);
});

test("an internal HTTP schema may reference only an existing internal source and never a remote or public owner", (t) => {
  const root = temporary(t);
  mkdirSync(path.join(root, "internal/ai-http/v1"), { recursive: true });
  mkdirSync(path.join(root, "internal/cf-http/v1"), { recursive: true });
  writeFileSync(path.join(root, "internal/ai-http/v1/schema.json"), "{}");
  const row = {
    id: "@arcforges/private",
    kind: "npm",
    access: "internal",
    sourceRoot: "src/internal/ts/private",
    dependencies: [],
    proto: [],
    jsonSchemas: ["internal/cf-http/v1/schema.json"],
  };
  const write = (reference) =>
    writeFileSync(
      path.join(root, "internal/cf-http/v1/schema.json"),
      JSON.stringify({ $ref: reference }),
    );
  write("../../ai-http/v1/schema.json#/$defs/ByteRange");
  checkPackageBoundaries(root, { schemaVersion: 1, packages: [row] });
  write("https://attacker.example/schema.json#/$defs/ByteRange");
  assert.throws(
    () => checkPackageBoundaries(root, { schemaVersion: 1, packages: [row] }),
    /remote JSON schema reference/,
  );
  write("../../ai-http/v1/missing.json#/$defs/ByteRange");
  assert.throws(
    () => checkPackageBoundaries(root, { schemaVersion: 1, packages: [row] }),
    /missing JSON reference/,
  );
  write("../../../outside.json");
  assert.throws(() => checkPackageBoundaries(root, { schemaVersion: 1, packages: [row] }));
  write("../../ai-http/v1/schema.json#/$defs/ByteRange");
  assert.throws(
    () =>
      checkPackageBoundaries(root, {
        schemaVersion: 1,
        packages: [{ ...row, access: "public", sourceRoot: "src/public/ts/private" }],
      }),
    /public-to-internal schema ownership/,
  );
});

// CON.40 (S47(4)): every historical access row of a retired identity is kept and marked retired; a new row
// for a retired identity and the removal or change of a historical row are refused.
const RETIRED = [
  "@arcforges/proto",
  "@arcforges/api-client",
  "@arcforges/contract-fixtures",
  "@arcforges/operator-client",
  "io.github.arcforges:contracts-proto",
  "io.github.arcforges:contracts-connect-client",
  "io.github.arcforges:contract-fixtures",
];

function realPolicy() {
  return JSON.parse(readFileSync(path.join(ROOT, "eng/policy/contract-access.json"), "utf8"));
}

test("the seven retired identities keep every access row, marked retired, and ai-internal stays active", () => {
  const retired = retiredIdentities(ROOT);
  assert.deepEqual([...retired.keys()].sort(), [...RETIRED].sort());
  assert.ok([...retired.values()].every((task) => task === "CON.40"));
  const policy = realPolicy();
  for (const row of policy.packages)
    assert.equal(row.retired, RETIRED.includes(row.id) ? "CON.40" : undefined, row.id);
  for (const id of RETIRED)
    assert.ok(
      policy.distribution.some((row) => row.package === id),
      "rows kept for " + id,
    );
  const files = inventory(ROOT);
  for (const row of policy.distribution.filter((r) => RETIRED.includes(r.package)))
    assert.ok(!files.includes(row.path), row.path);
  assert.ok(
    policy.distribution.some((row) => row.package === "@arcforges/ai-internal") &&
      !retired.has("@arcforges/ai-internal"),
  );
});

test("a new access row for a retired identity is refused, and so is removing or changing a historical one", () => {
  const base = realPolicy();
  const retired = retiredIdentities(ROOT);
  checkRetiredHistory(base, base, retired);
  const index = base.distribution.findIndex((row) => row.package === "@arcforges/proto");
  const added = structuredClone(base);
  added.distribution.push({
    ...base.distribution[index],
    path: "src/public/ts/proto/src/new.ts",
  });
  assert.throws(() => checkRetiredHistory(added, base, retired), /new access row for a retired/);
  const removed = structuredClone(base);
  removed.distribution.splice(index, 1);
  assert.throws(() => checkRetiredHistory(removed, base, retired), /removed or changed/);
  const changed = structuredClone(base);
  changed.distribution[index].types = [];
  assert.throws(() => checkRetiredHistory(changed, base, retired), /removed or changed/);
  const owner = structuredClone(base);
  owner.packages = owner.packages.filter((row) => row.id !== "@arcforges/proto");
  assert.throws(() => checkRetiredHistory(owner, base, retired), /owner of a retired identity/);
  const historical = structuredClone(base);
  historical.packages = historical.packages.filter((row) => row.id !== "@arcforges/proto");
  assert.throws(() => checkRetiredHistory(base, historical, retired), /new access owner/);
  // The base before the marking had no retired field: adding the marker is not a change of the row.
  const unmarked = structuredClone(base);
  for (const row of unmarked.packages) delete row.retired;
  delete unmarked.retiredOperations;
  checkRetiredHistory(base, unmarked, retired);
  // Rows of active identities follow their sources and may come and go.
  const active = structuredClone(base);
  active.distribution = active.distribution.filter(
    (row) => row.package !== "ArcForges.Contracts.LocalRpc.Chat",
  );
  checkRetiredHistory(active, base, retired);
});

test("retired marking must match the package inventory and retired sources must stay gone", () => {
  const policy = realPolicy();
  const files = inventory(ROOT);
  const unmarked = structuredClone(policy);
  delete unmarked.packages.find((row) => row.id === "@arcforges/proto").retired;
  assert.throws(() => checkSources(ROOT, files, unmarked), /retired access marking differs/);
  const marked = structuredClone(policy);
  marked.packages.find((row) => row.id === "@arcforges/ai-internal").retired = "CON.40";
  assert.throws(() => checkSources(ROOT, files, marked), /retired access marking differs/);
  const restored = policy.distribution.find((row) => row.package === "@arcforges/proto").path;
  assert.throws(
    () => checkSources(ROOT, [...files, restored], policy),
    /retired package keeps producer sources/,
  );
  const escaped = structuredClone(policy);
  escaped.distribution.find((row) => row.package === "@arcforges/proto").path =
    "src/public/ts/other.ts";
  assert.throws(() => checkSources(ROOT, files, escaped), /invalid retired access row/);
});

test("checkPackageInputs refuses a retired identity whose producer sources reappear", (t) => {
  const root = temporary(t);
  const row = {
    id: "@arcforges/retired",
    kind: "npm",
    access: "public",
    sourceRoot: "src/public/ts/retired",
    dependencies: [],
    retired: { task: "CON.40", reason: "fixture" },
  };
  checkPackageInputs(root, { packages: [row] });
  mkdirSync(path.join(root, row.sourceRoot), { recursive: true });
  assert.throws(
    () => checkPackageInputs(root, { packages: [row] }),
    /retired package keeps producer sources/,
  );
});

test("the five ContentSandbox PDF RPCs are marked retired and stay declared", (t) => {
  const policy = realPolicy();
  assert.deepEqual(
    policy.retiredOperations.map((row) => row.method),
    ["OpenPdf", "GetPdfPage", "ExtractPdfText", "RenderPdfTile", "ClosePdf"],
  );
  for (const row of policy.retiredOperations) {
    assert.equal(row.service, "arcforges.local.sandbox.v1.ContentSandboxService");
    assert.equal(row.decision, "P2-022");
    assert.equal(row.task, "CON.40");
  }
  const files = inventory(ROOT);
  for (const mutate of [
    (p) => p.retiredOperations.push(structuredClone(p.retiredOperations[0])),
    (p) => (p.retiredOperations[0].service = "arcforges.local.sandbox.v1.Unknown"),
    (p) => (p.retiredOperations[0].decision = "pending"),
    (p) => delete p.retiredOperations,
  ]) {
    const changed = structuredClone(policy);
    mutate(changed);
    assert.throws(() => checkSources(ROOT, files, changed));
  }
  const dropped = structuredClone(policy);
  dropped.retiredOperations.pop();
  assert.throws(
    () => checkRetiredHistory(dropped, policy, retiredIdentities(ROOT)),
    /retired operation marking removed/,
  );
  const { descriptor } = fixture(t, [
    [
      "internal",
      "sandbox.proto",
      "message M { string v = 1; } service ContentSandboxService { rpc OpenPdf(M) returns (M); }",
    ],
  ]);
  checkRetiredOperations(descriptor, [
    { service: "sample.ContentSandboxService", method: "OpenPdf" },
  ]);
  assert.throws(
    () =>
      checkRetiredOperations(descriptor, [
        { service: "sample.ContentSandboxService", method: "ClosePdf" },
      ]),
    /retired operation is not declared/,
  );
});

test("the history base is the reviewed pull-request or merge-group base, else the pushed parent", (t) => {
  const head = execFileSync("git", ["-C", ROOT, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const root = temporary(t);
  const event = path.join(root, "event.json");
  const cases = [
    ["pull_request", { pull_request: { base: { sha: head } } }, "refs/pull/1/merge"],
    ["merge_group", { merge_group: { base_sha: head } }, "refs/heads/gh-readonly-queue/main"],
    ["push", { before: head }, "refs/heads/main"],
    ["push", { before: "0".repeat(40) }, "refs/heads/main"],
    ["push", { before: "0".repeat(40) }, "refs/tags/v1.0.0"],
  ];
  for (const [name, value, ref] of cases) {
    writeFileSync(event, JSON.stringify(value));
    assert.equal(
      baseCommit(ROOT, { GITHUB_EVENT_NAME: name, GITHUB_EVENT_PATH: event, GITHUB_REF: ref }),
      head,
    );
  }
  writeFileSync(event, JSON.stringify({ pull_request: { base: { sha: "f".repeat(40) } } }));
  assert.throws(() =>
    baseCommit(ROOT, { GITHUB_EVENT_NAME: "pull_request", GITHUB_EVENT_PATH: event }),
  );
});
