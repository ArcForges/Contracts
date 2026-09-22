// SPDX-License-Identifier: Apache-2.0
// WP03.02 posture: executes the independent fixtures/public/wp03-02.json vectors in TypeScript.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  ArcErrorSchema,
  ContractSerializationError,
  contractServices,
  decodeContract,
  encodeContract,
  IdSchema,
  NotesFilterSchema,
  wireLimits,
} from "@arcforges/proto";
import {
  createPublicGrpcWebTransport,
  parsePartReceiptJson,
  serializePackageInventoryJson,
  serializePartReceiptJson,
  tryParsePackageInventoryJson,
  tryParsePartReceiptJson,
} from "@arcforges/api-client";
import {
  serializeCommitReceiptJson,
  tryParseCommitReceiptJson,
} from "../../src/internal/ts/ai-internal/dist/gen/http.js";

const fixture = JSON.parse(
  readFileSync(new URL("../../fixtures/public/wp03-02.json", import.meta.url)),
);
const targets = {
  "arcforges.foundation.v1.Id": IdSchema,
  "arcforges.foundation.v1.ArcError": ArcErrorSchema,
  "arcforges.publicapi.v1.NotesFilter": NotesFilterSchema,
};
const codecs = {
  PartReceipt: { tryParse: tryParsePartReceiptJson, serialize: serializePartReceiptJson },
  CommitReceipt: { tryParse: tryParseCommitReceiptJson, serialize: serializeCommitReceiptJson },
  PackageInventory: {
    tryParse: tryParsePackageInventoryJson,
    serialize: serializePackageInventoryJson,
  },
};

function varint(value) {
  const out = [];
  do {
    const low = value % 128;
    value = Math.floor(value / 128);
    out.push(value > 0 ? low | 0x80 : low);
  } while (value > 0);
  return out;
}

function lengthDelimited(field, payload) {
  const head = [...varint(field * 8 + 2), ...varint(payload.length)];
  const out = new Uint8Array(head.length + payload.length);
  out.set(head);
  out.set(payload, head.length);
  return out;
}

function construct(spec) {
  if (spec.kind === "hex") return Uint8Array.from(Buffer.from(spec.hex, "hex"));
  if (spec.kind === "filler") {
    const tag = varint(15999 * 8 + 2).length;
    for (let width = 1; width <= 5; width++) {
      const length = spec.totalBytes - tag - width;
      if (length >= 0 && varint(length).length === width)
        return lengthDelimited(15999, new Uint8Array(length));
    }
    throw new Error("No exact filler length");
  }
  if (spec.kind === "nested") {
    let inner = new Uint8Array(0);
    for (let level = spec.levels; level >= 1; level--) {
      inner = lengthDelimited(spec.fields[(level - 1) % spec.fields.length], inner);
    }
    return inner;
  }
  throw new Error(`Unknown construction ${spec.kind}`);
}

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

function outcome(action) {
  try {
    return { expect: "accept", value: action() };
  } catch (error) {
    assert.ok(error instanceof ContractSerializationError, String(error));
    return { expect: error.failure };
  }
}

test("fixed limits match the independent vectors", () => {
  for (const key of [
    "unaryMessage",
    "helperMessage",
    "inlinePage",
    "streamFrame",
    "largeProjection",
    "nestedMessageLevels",
  ]) {
    assert.equal(wireLimits[key], fixture.limits[key], key);
  }
});

test("bounded binary codec follows every binary vector", () => {
  for (const item of fixture.binary) {
    const schema = targets[item.construct.target];
    const bytes = construct(item.construct);
    if (item.construct.kind === "filler")
      assert.equal(bytes.length, item.construct.totalBytes, item.id);
    const result =
      item.operation === "encode"
        ? outcome(() =>
            encodeContract(schema, decodeContract(schema, bytes, "largeProjection"), item.limit),
          )
        : outcome(() => decodeContract(schema, bytes, item.limit));
    assert.equal(result.expect, item.expect, item.id);
    if (result.expect !== "accept") continue;
    const encoded =
      item.operation === "encode"
        ? result.value
        : encodeContract(schema, result.value, "largeProjection");
    assert.deepEqual(
      Buffer.from(encoded),
      Buffer.from(bytes),
      `${item.id} re-encodes every retained byte`,
    );
    if (item.reencodeHex !== undefined)
      assert.equal(Buffer.from(encoded).toString("hex"), item.reencodeHex, item.id);
  }
});

test("strict HTTP-exception JSON codecs follow every JSON vector", () => {
  for (const item of fixture.json) {
    const codec = codecs[item.schema];
    const bytes = documentBytes(item);
    const result = codec.tryParse(bytes);
    assert.equal(result.ok ? "accept" : result.failure, item.expect, item.id);
    if (!result.ok) continue;
    const written = codec.serialize(result.value);
    assert.deepEqual(
      JSON.parse(Buffer.from(written).toString("utf8")),
      item.canonical,
      `${item.id} canonical value`,
    );
    const again = codec.tryParse(written);
    assert.ok(again.ok, item.id);
    assert.deepEqual(
      Buffer.from(codec.serialize(again.value)),
      Buffer.from(written),
      `${item.id} stable output`,
    );
  }
});

test("string input applies the same byte bound and text checks", () => {
  const base = fixture.json.find((item) => item.id === "part-canonical").text;
  assert.equal(parsePartReceiptJson(base).partNumber, 1);
  assert.equal(
    tryParsePartReceiptJson(base + " ".repeat(65536 - base.length + 1)).failure,
    "tooLarge",
  );
  assert.equal(tryParsePartReceiptJson(base.replace('"e1', '"\ud800')).failure, "malformed");
  assert.throws(
    () => parsePartReceiptJson("{}"),
    (error) => error.failure === "invalid",
  );
});

test("serialization refuses values the closed schema rejects", () => {
  assert.throws(
    () =>
      serializePartReceiptJson({ partNumber: 1.5, size: "1", sha256: "a".repeat(64), etag: "x" }),
    (error) => error.failure === "invalid",
  );
});

test("generated service catalogue lists exactly the authored services", () => {
  assert.deepEqual(
    contractServices.map((service) => service.typeName),
    fixture.services.typescript["@arcforges/proto"],
  );
  for (const service of contractServices) {
    assert.deepEqual(
      service.methods.map((method) => `/${service.typeName}/${method.name}`),
      fixture.services.methods[service.typeName],
    );
  }
});

test("public transport is binary gRPC-Web and refuses codec overrides", () => {
  assert.ok(createPublicGrpcWebTransport({ baseUrl: "https://example.invalid" }));
  for (const override of [
    { useBinaryFormat: false },
    { useBinaryFormat: true },
    { jsonOptions: {} },
    { binaryOptions: {} },
  ]) {
    assert.throws(
      () => createPublicGrpcWebTransport({ baseUrl: "https://example.invalid", ...override }),
      TypeError,
    );
  }
});
