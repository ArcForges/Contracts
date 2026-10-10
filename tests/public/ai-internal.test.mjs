// SPDX-License-Identifier: Apache-2.0
// @arcforges/ai-internal is the one retained internal thin-adapter package (P2-021 Decision 4; CON.40).
// These assertions were extracted unchanged from structure.test.mjs, serialization.test.mjs,
// extension-policy.test.mjs and con-10-chat-task-agent.test.mjs. The business SDK cases of those files
// moved to C# (eng/policy/con-40-test-map.json).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import * as ai from "../../src/internal/ts/ai-internal/dist/gen/http.js";

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));

// ------------------------------------------------------------------ structure.test.mjs (wp03-00)

test("wp03-00 CommitReceipt shape fixtures are checked by the generated validator", () => {
  let count = 0;
  for (const visibility of ["public", "internal"]) {
    for (const item of read(`../../fixtures/${visibility}/wp03-00.json`).cases) {
      if (item.target !== "CommitReceipt") continue;
      assert.equal(ai.isCommitReceipt(item.value), item.valid, item.id);
      count++;
    }
  }
  assert.ok(count > 0, "CommitReceipt fixtures are present");
});

// ------------------------------------------------------------------ serialization.test.mjs (wp03-02)

function documentBytes(item) {
  if (item.hex !== undefined) return Uint8Array.from(Buffer.from(item.hex, "hex"));
  if (item.construct !== undefined) {
    const base = Buffer.from(item.construct.base, "utf8");
    return Uint8Array.from(
      Buffer.concat([base, Buffer.alloc(item.construct.totalBytes - base.length, 0x20)]),
    );
  }
  return Uint8Array.from(Buffer.from(item.text, "utf8"));
}

test("strict CommitReceipt JSON codec follows every JSON vector", () => {
  const vectors = read("../../fixtures/public/wp03-02.json").json.filter(
    (item) => item.schema === "CommitReceipt",
  );
  assert.ok(vectors.length > 0, "CommitReceipt JSON vectors are present");
  for (const item of vectors) {
    const bytes = documentBytes(item);
    const result = ai.tryParseCommitReceiptJson(bytes);
    assert.equal(result.ok ? "accept" : result.failure, item.expect, item.id);
    if (!result.ok) continue;
    const written = ai.serializeCommitReceiptJson(result.value);
    assert.deepEqual(
      JSON.parse(Buffer.from(written).toString("utf8")),
      item.canonical,
      `${item.id} canonical value`,
    );
    const again = ai.tryParseCommitReceiptJson(written);
    assert.ok(again.ok, item.id);
    assert.deepEqual(
      Buffer.from(ai.serializeCommitReceiptJson(again.value)),
      Buffer.from(written),
      `${item.id} stable output`,
    );
  }
});

// ------------------------------------------------------------------ extension-policy.test.mjs (con-12)

test("ConfigurationDocument independent vectors exercise the generated codec", () => {
  const privateFixture = read("../../fixtures/internal/con-12-configuration.json");
  assert.ok(Array.isArray(privateFixture.codecCases));
  assert.ok(privateFixture.codecCases.length > 0);
  assert.ok(privateFixture.codecCases.every((row) => row.schema === "ConfigurationDocument"));
  for (const row of privateFixture.codecCases) {
    const result = ai.tryParseConfigurationDocumentJson(
      new TextEncoder().encode(JSON.stringify(row.value)),
    );
    assert.equal(result.ok, row.valid, `${row.id}: independent acceptance differs`);
    if (!row.valid) continue;
    const encoded = ai.serializeConfigurationDocumentJson(result.value);
    const second = ai.tryParseConfigurationDocumentJson(encoded);
    assert.equal(second.ok, true, `${row.id}: generated serialization refused itself`);
    assert.deepEqual(second.value, row.value, `${row.id}: typed roundtrip changed the document`);
    assert.deepEqual(
      ai.serializeConfigurationDocumentJson(second.value),
      encoded,
      `${row.id}: serialization is not stable`,
    );
  }
});

// ------------------------------------------------------------------ con-10-chat-task-agent.test.mjs

const internalFixture = read("../../fixtures/internal/con-10-ai-internal.json");
const aiSchema = read("../../internal/ai-http/v1/schema.json");
const aiDefinitions = aiSchema.$defs;
const resolve = (node) => (node.$ref ? aiDefinitions[node.$ref.slice("#/$defs/".length)] : node);

function branchFor(node, property) {
  const alternatives = node.oneOf.map((reference) => resolve(reference));
  return alternatives.find((alternative) => alternative.properties?.[property]) ?? alternatives[0];
}

function defaultString(node) {
  if (node.enum) return node.enum[0];
  if (typeof node.const === "string") return node.const;
  const candidates = [
    "10000000-0000-4000-8000-000000000001",
    "2026-09-28T00:00:00Z",
    "0",
    "1",
    "fixture",
    "x",
    "A",
    "AA==",
    "a".repeat(64),
  ];
  if (node.pattern) {
    const pattern = new RegExp(node.pattern);
    const match = candidates.find(
      (candidate) => pattern.test(candidate) && candidate !== node.not?.const,
    );
    if (match !== undefined) return match;
    const fallback = "x".repeat(Math.max(1, node.minLength ?? 1));
    if (pattern.test(fallback) && fallback !== node.not?.const) return fallback;
    throw new Error(`No deterministic fixture string matches ${node.pattern}`);
  }
  return "x".repeat(Math.max(1, node.minLength ?? 1));
}

function defaultValue(original, propertyHint, depth = 0) {
  assert.ok(depth < 40, "schema fixture builder exceeded recursion bound");
  const node = resolve(original);
  if (node.oneOf) return defaultValue(branchFor(node, propertyHint), undefined, depth + 1);
  if (node.type === "object") {
    const out = {};
    for (const property of node.required ?? [])
      out[property] = defaultValue(node.properties[property], undefined, depth + 1);
    return out;
  }
  if (node.type === "array")
    return Array.from({ length: node.minItems ?? 0 }, () =>
      defaultValue(node.items, propertyHint, depth + 1),
    );
  if (node.type === "string") return defaultString(node);
  if (node.type === "integer") return node.minimum ?? 0;
  if (node.type === "number") return node.minimum ?? 0.125;
  if (node.type === "boolean") return false;
  throw new Error(`Unsupported fixture schema node: ${JSON.stringify(node)}`);
}

function setPath(current, original, segments, replacement) {
  const node = resolve(original);
  if (node.oneOf) {
    const property = segments[0] === "[]" ? undefined : segments[0];
    const branch = branchFor(node, property);
    const keys = Object.keys(branch.properties ?? {});
    const required = branch.required ?? [];
    if (
      !current ||
      Object.keys(current).some((key) => !keys.includes(key)) ||
      required.some((key) => !Object.hasOwn(current, key))
    )
      current = defaultValue(branch);
    return setPath(current, branch, segments, replacement);
  }
  if (segments.length === 0) return replacement;
  const [segment, ...rest] = segments;
  if (segment === "[]") {
    assert.equal(node.type, "array");
    if (current.length === 0) current.push(defaultValue(node.items, rest[0]));
    current[0] = setPath(current[0], node.items, rest, replacement);
    return current;
  }
  assert.equal(node.type, "object", `cannot navigate ${segment} through ${node.type}`);
  const child = node.properties[segment];
  assert.ok(child, `unknown fixture path property ${segment}`);
  if (rest.length === 0) current[segment] = replacement;
  else {
    if (!Object.hasOwn(current, segment)) current[segment] = defaultValue(child, rest[0]);
    current[segment] = setPath(current[segment], child, rest, replacement);
  }
  return current;
}

function valuePath(path) {
  return path.replace(/\[\]/g, ".[]").split(".").filter(Boolean);
}

function fixtureValue(vector) {
  if (!vector.valuePattern) return vector.value;
  return vector.valuePattern.repeat.repeat(vector.valuePattern.count) + (vector.suffix ?? "");
}

function aiInputAtPath(vector, value) {
  const segments = valuePath(vector.path);
  const input = defaultValue(aiDefinitions[vector.schema], segments[0]);
  return setPath(input, aiDefinitions[vector.schema], segments, value);
}

test("14 CF port roots validate, round-trip every union branch, and reject forged or oversized input", () => {
  assert.equal(internalFixture.ports.length, 14);
  for (const port of internalFixture.ports) {
    for (const name of [port.request, port.response]) {
      assert.equal(typeof ai[`is${name}`], "function", `${name} validator is generated`);
      assert.equal(typeof ai[`tryParse${name}Json`], "function", `${name} parser is generated`);
      assert.equal(
        typeof ai[`serialize${name}Json`],
        "function",
        `${name} serializer is generated`,
      );
    }
  }
  for (const vector of internalFixture.positiveVectors) {
    if (vector.input) {
      assert.equal(ai[`is${vector.schema}`](vector.input), true, vector.id);
      if (vector.assertRoundTrip) {
        const parsed = ai[`tryParse${vector.schema}Json`](
          ai[`serialize${vector.schema}Json`](vector.input),
        );
        assert.deepEqual(parsed, { ok: true, value: vector.input }, vector.id);
      }
    } else {
      const input = aiInputAtPath(vector, fixtureValue(vector));
      assert.equal(ai[`is${vector.schema}`](input), true, vector.id);
    }
  }
  for (const vector of internalFixture.negativeVectors) {
    if (vector.path) {
      const input = aiInputAtPath(vector, vector.input);
      assert.equal(ai[`is${vector.schema}`](input), false, vector.id);
    } else if (vector.input) assert.equal(ai[`is${vector.schema}`](vector.input), false, vector.id);
  }

  const overflowVector = internalFixture.negativeVectors.find(
    (vector) => vector.id === "structured-value-rejects-overflowing-number-lexeme",
  );
  const overflowInput = aiInputAtPath(overflowVector, 0.125);
  const overflowJson = JSON.stringify(overflowInput).replace('"number":0.125', '"number":1e999');
  assert.notEqual(
    overflowJson,
    JSON.stringify(overflowInput),
    "overflow fixture injects the exact raw number lexeme",
  );
  assert.equal(ai.tryParseAiModelOutcomeRequestJson(overflowJson).ok, false, overflowVector.id);

  const cursorVector = internalFixture.positiveVectors.find(
    (vector) => vector.id === "cursor-4096-ascii-bytes",
  );
  const boundary = aiInputAtPath(cursorVector, fixtureValue(cursorVector));
  assert.equal(ai.isAiReconcileRequest(boundary), true);
  const tooLong = aiInputAtPath(
    { ...cursorVector, valuePattern: { repeat: "a", count: 4097 } },
    "a".repeat(4097),
  );
  assert.equal(ai.isAiReconcileRequest(tooLong), false);

  const malformedSurrogate = internalFixture.negativeVectors.find(
    (vector) => vector.id === "cursor-rejects-unpaired-surrogate",
  );
  assert.equal(ai.tryParseAiReconcileRequestJson(malformedSurrogate.rawJson).failure, "malformed");
  const malformedUtf8 = internalFixture.negativeVectors.find(
    (vector) => vector.id === "cursor-rejects-invalid-utf8",
  );
  assert.equal(
    ai.tryParseAiReconcileRequestJson(Buffer.from(malformedUtf8.rawUtf8Hex, "hex")).failure,
    "malformed",
  );
});
