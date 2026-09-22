// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  ROOT,
  checkAssignments,
  checkPackageBoundaries,
  checkPackageInputs,
  maskXmlComments,
  checkSources,
  compile,
  declaredTypes,
  descriptorGraph,
  inventory,
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
  checkSources(ROOT, files, policy);
  for (const mutate of [
    (p) => p.distribution.pop(),
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
    assert.throws(() => checkSources(ROOT, files, changed));
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
