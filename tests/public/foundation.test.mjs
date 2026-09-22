// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { fromJson, toJson, fromBinary, toBinary } from "@bufbuild/protobuf";
import * as foundation from "../../src/public/ts/proto/dist/gen/arcforges/foundation/v1/foundation_pb.js";
import * as content from "../../src/public/ts/proto/dist/gen/arcforges/publicapi/v1/content_pb.js";
import * as checks from "../../src/public/ts/proto/dist/shapes/gen/proto.js";
import * as values from "../../src/public/ts/proto/dist/values.js";
import { assertFoundationCoverage } from "./foundation-coverage.mjs";

const fixtureUrl = new URL("../../fixtures/public/wp03-01.json", import.meta.url);
const fixtureBytes = await readFile(fixtureUrl);
const fixture = JSON.parse(fixtureBytes.toString("utf8"));
const fixtureDigest = createHash("sha256").update(fixtureBytes).digest("hex");
const foundationNames = new Set(fixture.foundationTypes);
const selectedNames = Object.keys(fixture.samples).filter((name) => !name.startsWith("$"));
const output = [];
assert.equal(
  fixture.samples.RichText.text,
  "A\u4e2d\ud83d\ude00",
  "The registry UTF-16 oracle must survive fixture encoding",
);

function expand(value, stack = []) {
  if (Array.isArray(value)) return value.map((item) => expand(item, stack));
  if (value === null || typeof value !== "object") return value;
  if (Object.hasOwn(value, "$ref")) {
    assert.deepEqual(Object.keys(value), ["$ref"], "Fixture refs do not override their source");
    assert.ok(Object.hasOwn(fixture.samples, value.$ref), `Unknown fixture ref ${value.$ref}`);
    assert.ok(!stack.includes(value.$ref), `Cyclic fixture ref ${value.$ref}`);
    return expand(fixture.samples[value.$ref], [...stack, value.$ref]);
  }
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, expand(item, stack)]));
}

function materialize(item) {
  const result = expand(item.value ?? fixture.samples[item.sample]);
  for (const [path, value] of Object.entries(item.set ?? {})) {
    const parts = path.split(".");
    const key = parts.pop();
    let parent = result;
    for (const part of parts) {
      assert.ok(parent && Object.hasOwn(parent, part), `Unknown patch path ${path}`);
      parent = parent[part];
    }
    parent[key] = expand(value);
  }
  for (const path of item.remove ?? []) {
    const parts = path.split(".");
    const key = parts.pop();
    let parent = result;
    for (const part of parts) parent = parent[part];
    assert.ok(parent && Object.hasOwn(parent, key), `Unknown removal path ${path}`);
    delete parent[key];
  }
  return result;
}

function schemaFor(name) {
  assert.ok(selectedNames.includes(name), `Unregistered fixture target ${name}`);
  const schema = (foundationNames.has(name) ? foundation : content)[`${name}Schema`];
  assert.ok(schema, `Missing generated schema ${name}`);
  assert.equal(typeof checks[`is${name}`], "function", `Missing generated validator ${name}`);
  return schema;
}

function roundTrip(name, json, id) {
  const schema = schemaFor(name);
  const message = fromJson(schema, json);
  const binary = toBinary(schema, message);
  const decoded = fromBinary(schema, binary);
  assert.deepEqual(toJson(schema, decoded), toJson(schema, message), `${id}: semantic round trip`);
  assert.equal(checks[`is${name}`](decoded), true, `${id}: validation after round trip`);
  output.push({
    id,
    target: name,
    binaryHex: Buffer.from(binary).toString("hex"),
    json: toJson(schema, message),
  });
}

const observedRecords = new Set();
const observedIds = new Set();
const failures = [];
for (const item of fixture.cases) {
  assert.ok(!observedIds.has(item.id), `Duplicate fixture id ${item.id}`);
  observedIds.add(item.id);
  const json = materialize(item);
  const schema = schemaFor(item.target);
  let message;
  try {
    message = fromJson(schema, json);
  } catch (error) {
    if (!(error instanceof Error)) throw error;
  }
  // Malformed JSON may be rejected by the codec. A validator crash must fail the
  // suite rather than masquerade as the expected rejection of a negative case.
  const actual = message === undefined ? false : checks[`is${item.target}`](message);
  if (actual !== item.valid) {
    failures.push(`${item.id}: expected ${item.valid}, received ${actual}`);
    continue;
  }
  if (item.valid) {
    observedRecords.add(item.target);
    roundTrip(item.target, json, item.id);
  }
}
assert.deepEqual(failures, [], "Independent semantic fixture failures");
assert.deepEqual(
  [...observedRecords].sort(),
  selectedNames.sort(),
  "Every selected record has a valid round trip",
);
const inventory = JSON.parse(
  await readFile(new URL("../../eng/foundation-inventory.json", import.meta.url), "utf8"),
);
assertFoundationCoverage(inventory, output);
assert.equal(
  Object.keys(fixture.aggregateVariants).length,
  16,
  "All owner-body variants remain covered",
);
assert.equal(
  Object.keys(fixture.errorCategories).length,
  45,
  "All initial catalogue codes remain covered",
);
for (const scenario of fixture.profileScenarios) {
  assert.ok(scenario.expectedCaseIds.length > 0, `${scenario.id}: no wire evidence`);
  for (const id of scenario.expectedCaseIds)
    assert.ok(observedIds.has(id), `${scenario.id}: missing ${id}`);
  assert.match(
    scenario.evidenceBoundary,
    /owner .*pending/,
    `${scenario.id}: preserve the owner boundary`,
  );
}

for (const item of fixture.wireVectors) {
  const schema = schemaFor(item.target);
  const expected = Buffer.from(item.hex, "hex");
  const encoded = toBinary(schema, fromJson(schema, item.value));
  assert.equal(Buffer.from(encoded).toString("hex"), item.hex, item.id);
  assert.deepEqual(
    toJson(schema, fromBinary(schema, expected)),
    toJson(schema, fromJson(schema, item.value)),
    `${item.id}: independent decode`,
  );
}

// Unknown read data survives a decode/re-encode without becoming writable.
const unknown = Buffer.from("0800a00607", "hex"); // NativeContentRev.value=0; future field100=7.
const retained = values.readProjection(
  foundation.NativeContentRevSchema,
  unknown,
  checks.isNativeContentRev,
);
assert.equal(retained.knownProfile, true);
assert.equal(
  Buffer.from(
    values.preserveProjection(foundation.NativeContentRevSchema, retained.message),
  ).toString("hex"),
  unknown.toString("hex"),
);
const futureJson = expand(fixture.samples.ContentOrigin);
futureJson.profile = "arcforges.content-origin.v2";
const futureBytes = toBinary(
  foundation.ContentOriginSchema,
  fromJson(foundation.ContentOriginSchema, futureJson),
);
const futureRead = values.readProjection(
  foundation.ContentOriginSchema,
  futureBytes,
  checks.isContentOrigin,
);
assert.equal(futureRead.knownProfile, false);
assert.equal(
  Buffer.from(
    values.preserveProjection(foundation.ContentOriginSchema, futureRead.message),
  ).toString("hex"),
  Buffer.from(futureBytes).toString("hex"),
);

// Independent value-boundary oracles, including malformed language-boundary input.
const canonicalId = "00112233-4455-6677-8899-aabbccddeeff";
const documentId = values.parseId("DocumentId", canonicalId);
const documentWire = values.idToWire("DocumentId", documentId);
assert.equal(Buffer.from(documentWire.value).toString("hex"), "00112233445566778899aabbccddeeff");
documentWire.value[0] = 255;
assert.equal(values.idToWire("DocumentId", documentId).value[0], 0, "Wire output owns its bytes");
assert.equal(
  values.idFromWire(
    "DocumentId",
    fromJson(foundation.IdSchema, { value: "ABEiM0RVZneImaq7zN3u/w==" }),
  ),
  canonicalId,
);
for (const text of [
  "",
  "00000000-0000-0000-0000-000000000000",
  canonicalId.toUpperCase(),
  "00112233445566778899aabbccddeeff",
  ...["\n", "\r", "\u2028"].flatMap((suffix) => [
    canonicalId + suffix,
    "00000000-0000-0000-0000-000000000000" + suffix,
  ]),
])
  assert.throws(() => values.parseId("DocumentId", text));
assert.equal(values.parseInt64("-9223372036854775808"), -9223372036854775808n);
assert.equal(values.parseInt64("9223372036854775807"), 9223372036854775807n);
assert.equal(values.parseUInt64("18446744073709551615"), 18446744073709551615n);
for (const text of ["+1", "01", "-0", "1e3", " 1", "1\n", "1\r", "1\u2028", "9223372036854775808"])
  assert.throws(() => values.parseInt64(text));
for (const text of ["-1", "01", "18446744073709551616"])
  assert.throws(() => values.parseUInt64(text));
assert.equal(
  values.cloudRevisionToWire(values.cloudRevision(9007199254740993n)).value,
  9007199254740993n,
);
assert.throws(() => values.cloudRevision(0n));
assert.throws(() => values.cloudRevisionFromWire(fromJson(foundation.RevisionSchema, {})));
assert.equal(values.newRootPrecondition().value, 0n);
assert.equal(
  values.nativeRevisionToWire(values.nativeRevision(18446744073709551615n)).value,
  18446744073709551615n,
);
assert.deepEqual(
  values.localNotesFromWire(
    values.localNotesToWire(values.localNotesToken(0n, 18446744073709551615n)),
  ),
  { acknowledgedRevision: 0n, headLocalSequence: 18446744073709551615n },
);
assert.deepEqual(values.decimalParts(values.notesDecimal("-0.000000001")), {
  coefficient: -1n,
  scale: 9,
});
assert.equal(values.decimalFromCoefficient(1n, 9), "0.000000001");
assert.equal(values.exactDecimal("1.00"), "1.00", "Shared exact decimal preserves declared scale");
for (const text of ["1.0", "-0", "+1", "1e3", "0.0000000001", "1\n", "1\r", "1\u2028"])
  assert.throws(() => values.notesDecimal(text));
assert.equal(values.opaqueCursor("😀".repeat(1024)).length, 2048);
assert.throws(() => values.opaqueCursor("😀".repeat(1025)));
assert.throws(() => values.opaqueCursor("\ud800"));
const wideRate = values.rationalValue(9223372036854775807n, 18446744073709551615n);
assert.equal(
  values.convertTicksExact(9223372036854775807n, wideRate, wideRate),
  9223372036854775807n,
  "Wide intermediates retain exact ticks",
);
assert.equal(
  values.convertTicksExact(
    48000n,
    values.rationalValue(48000n, 1n),
    values.rationalValue(705600000n, 1n),
  ),
  705600000n,
  "One audio second converts exactly to media ticks",
);
assert.throws(
  () => values.convertTicksExact(1n, values.rationalValue(3n, 1n), values.rationalValue(1n, 1n)),
  RangeError,
);
assert.throws(
  () =>
    values.convertTicksExact(
      9223372036854775807n,
      values.rationalValue(1n, 1n),
      values.rationalValue(2n, 1n),
    ),
  RangeError,
);
assert.throws(() => values.rationalValue(1n, 0n), RangeError);
assert.throws(() => values.rationalValue(2n, 4n), TypeError);
assert.throws(
  () =>
    values.convertTicksExact(1n, { numerator: 0n, denominator: 0n }, values.rationalValue(1n, 1n)),
  RangeError,
);
assert.throws(
  () => values.convertTicksExact(1n, values.rationalValue(0n, 1n), values.rationalValue(1n, 1n)),
  RangeError,
);

if (process.argv.includes("--exchange")) {
  const directory = new URL("../../artifacts/tests/foundation/", import.meta.url);
  const incoming = JSON.parse(await readFile(new URL("csharp.json", directory), "utf8"));
  assert.equal(
    incoming.fixtureDigest,
    fixtureDigest,
    "Cross-language evidence uses current fixture bytes",
  );
  assert.equal(incoming.cases.length, output.length, "C# covers the same positive fixture set");
  const expectedById = new Map(output.map((item) => [item.id, item]));
  const seen = new Set();
  for (const item of incoming.cases) {
    assert.ok(!seen.has(item.id), `Duplicate C# exchange case ${item.id}`);
    seen.add(item.id);
    const expected = expectedById.get(item.id);
    assert.ok(expected, `Unknown C# exchange case ${item.id}`);
    assert.equal(item.target, expected.target);
    const schema = schemaFor(item.target);
    const decoded = fromBinary(schema, Buffer.from(item.binaryHex, "hex"));
    assert.deepEqual(toJson(schema, decoded), expected.json, `${item.id}: C# to TypeScript`);
    assert.equal(
      checks[`is${item.target}`](decoded),
      true,
      `${item.id}: cross-language validation`,
    );
  }
  assert.deepEqual(
    [...seen].sort(),
    [...expectedById.keys()].sort(),
    "C# exchange covers the complete expected case set",
  );
  await mkdir(directory, { recursive: true });
  await writeFile(
    new URL("typescript.json", directory),
    JSON.stringify({ fixtureDigest, cases: output }),
  );
}
console.log(
  `Validated ${fixture.cases.length} independent foundation cases, ${selectedNames.length} records, 16 owner bodies, 45 error categories and ${fixture.wireVectors.length} binary oracles.`,
);
